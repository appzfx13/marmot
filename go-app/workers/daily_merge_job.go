package workers

import (
	"context"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	parquetgo "github.com/parquet-go/parquet-go"
	"go-app/config"
	"go-app/models"
	"go-app/parquet"
	"go-app/services"
	"go-app/ws"
)

// DailyMergeJob handles post-market (16:00 IST) 1S option download and single-file Parquet consolidation.
type DailyMergeJob struct {
	dbService    *services.DBService
	cfg          *config.Config
	redisService *services.RedisService
	hub          *ws.Hub
}

// NewDailyMergeJob creates a new instance of DailyMergeJob
func NewDailyMergeJob(dbService *services.DBService, cfg *config.Config, redisService *services.RedisService, hub *ws.Hub) *DailyMergeJob {
	return &DailyMergeJob{
		dbService:    dbService,
		cfg:          cfg,
		redisService: redisService,
		hub:          hub,
	}
}

// Run executes the post-market 1S merge pipeline for a specific date and index list.
func (j *DailyMergeJob) Run(ctx context.Context, dateStr string, indices []string, strikeCount int) {
	ist, _ := time.LoadLocation("Asia/Kolkata")
	if dateStr == "" {
		dateStr = time.Now().In(ist).Format("2006-01-02")
	}
	if strikeCount <= 0 {
		strikeCount = 15
	}
	if len(indices) == 0 {
		indices = []string{"NIFTY", "BANKNIFTY"}
	}

	log.Printf("🚀 [DailyMergeJob] Starting 4:00 PM Post-Market 1S Consolidation for Date: %s | Indices: %v | Strikes: ±%d",
		dateStr, indices, strikeCount)

	if j.redisService != nil && j.redisService.Client != nil {
		j.redisService.Client.Set(ctx, fmt.Sprintf("marmot:merge:%s:status", dateStr), "running", 24*time.Hour)
	}

	// Step 1: Consolidate live 1S Spot part files into spot_1s.parquet
	spotFile, err := parquet.ConsolidateDailySpot("/app/backup", dateStr)
	if err != nil {
		log.Printf("⚠️ [DailyMergeJob] ConsolidateDailySpot notice: %v", err)
		spotFile = filepath.Join("/app/backup", "ticks", dateStr, "spot_1s.parquet")
	}

	// Step 2: Load Spot records from spot_1s.parquet
	var spotRecords []models.MarketCandleRecord
	if spotRows, readErr := parquetgo.ReadFile[parquet.Spot1SRecord](spotFile); readErr == nil {
		for _, r := range spotRows {
			spotRecords = append(spotRecords, models.MarketCandleRecord{
				Timestamp:      r.Timestamp,
				Datetime:       r.Datetime,
				IndexName:      r.IndexName,
				InstrumentType: "INDEX",
				TradingSymbol:  fmt.Sprintf("NSE:%s50-INDEX", r.IndexName),
				Strike:         "SPOT",
				OptionType:     "INDEX",
				Open:           r.Open,
				High:           r.High,
				Low:            r.Low,
				Close:          r.Close,
				Volume:         0,
				OI:             0,
				Bid:            r.Close,
				Ask:            r.Close,
				SpotPrice:      r.Close,
			})
		}
		log.Printf("📊 [DailyMergeJob] Loaded %d 1-second spot records from %s", len(spotRecords), spotFile)
	} else {
		log.Printf("⚠️ [DailyMergeJob] Could not read spot records from %s: %v", spotFile, readErr)
	}

	// Step 3: Fetch broker credentials
	appID, token, isActive, _, credErr := j.dbService.GetBrokerCredentials(ctx)
	if credErr != nil || !isActive || token == "" {
		log.Printf("⚠️ [DailyMergeJob] Broker credentials unavailable (err: %v, active: %v). Skipping option download.", credErr, isActive)
		if j.redisService != nil && j.redisService.Client != nil {
			j.redisService.Client.Set(ctx, fmt.Sprintf("marmot:merge:%s:status", dateStr), "error: broker credentials unavailable", 24*time.Hour)
		}
		return
	}

	allCombinedRecords := make([]models.MarketCandleRecord, 0, len(spotRecords)+100000)
	allCombinedRecords = append(allCombinedRecords, spotRecords...)

	targetDayDir := filepath.Join("/app/backup", "ticks", dateStr)
	_ = os.MkdirAll(targetDayDir, 0755)
	stagingDir := filepath.Join(targetDayDir, "staging")
	_ = os.MkdirAll(stagingDir, 0755)

	// Step 4: Download 1S Option data for each index and compute BSM Greeks
	for _, idx := range indices {
		idx = strings.TrimSpace(strings.ToUpper(idx))
		spotMap, _ := parquet.LoadSpotLookup("/app/backup", dateStr, idx)

		taskPayload := models.CommandPayload{
			TaskID:  fmt.Sprintf("daily_%s_%s", dateStr, idx),
			Command: "START",
			Params: models.TaskParams{
				IndexName:        idx,
				StartDate:        dateStr,
				EndDate:          dateStr,
				StrikeCount:      strikeCount,
				Use30Days1s:      true,
				FyersAppID:       appID,
				FyersAccessToken: token,
				UserID:           "1",
			},
		}

		bj := NewBackupJob(j.dbService, j.cfg, taskPayload, j.hub)
		optionChunks := bj.runOptionsDownload(ctx, taskPayload.TaskID, stagingDir, idx, dateStr, dateStr, strikeCount, 50, appID, token, spotMap, true, false)

		for _, chunkFile := range optionChunks {
			rows, readChunkErr := parquetgo.ReadFile[models.MarketCandleRecord](chunkFile)
			if readChunkErr == nil {
				allCombinedRecords = append(allCombinedRecords, rows...)
			}
		}
	}

	// Step 5: Sort all records chronologically
	sort.Slice(allCombinedRecords, func(i, j int) bool {
		if allCombinedRecords[i].Timestamp == allCombinedRecords[j].Timestamp {
			return allCombinedRecords[i].TradingSymbol < allCombinedRecords[j].TradingSymbol
		}
		return allCombinedRecords[i].Timestamp < allCombinedRecords[j].Timestamp
	})

	// Step 6: Write final consolidated dataset_1s.parquet
	finalDatasetPath := filepath.Join(targetDayDir, "dataset_1s.parquet")
	finalFile, err := os.OpenFile(finalDatasetPath, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, 0644)
	if err != nil {
		log.Printf("❌ [DailyMergeJob] Failed to create dataset_1s.parquet: %v", err)
		return
	}
	defer finalFile.Close()

	writer := parquetgo.NewGenericWriter[models.MarketCandleRecord](finalFile, parquetgo.Compression(&parquetgo.Snappy))
	if _, err := writer.Write(allCombinedRecords); err != nil {
		log.Printf("❌ [DailyMergeJob] Write to dataset_1s.parquet error: %v", err)
		return
	}
	if err := writer.Close(); err != nil {
		log.Printf("❌ [DailyMergeJob] Close dataset_1s.parquet error: %v", err)
		return
	}

	fi, _ := os.Stat(finalDatasetPath)
	var sizeMB float64
	if fi != nil {
		sizeMB = float64(fi.Size()) / (1024 * 1024)
	}

	log.Printf("🎉 [DailyMergeJob] Successfully created 1-second dataset (%d records, %.2f MB) at: %s",
		len(allCombinedRecords), sizeMB, finalDatasetPath)

	if j.redisService != nil && j.redisService.Client != nil {
		j.redisService.Client.Set(ctx, fmt.Sprintf("marmot:merge:%s:status", dateStr), "completed", 24*time.Hour)
	}
}
