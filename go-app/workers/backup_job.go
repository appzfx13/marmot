package workers

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"go-app/config"
	"go-app/models"
	"go-app/services"
	"go-app/ws"
)


// BackupJob handles downloading, Hive date-partitioning, and account-separated storage logic
type BackupJob struct {
	dbService *services.DBService
	config    *config.Config
	payload   models.CommandPayload
	hub       *ws.Hub
	startTime time.Time
}

// NewBackupJob creates a new instance of BackupJob
func NewBackupJob(dbService *services.DBService, cfg *config.Config, payload models.CommandPayload, hub *ws.Hub) *BackupJob {
	return &BackupJob{
		dbService: dbService,
		config:    cfg,
		payload:   payload,
		hub:       hub,
		startTime: time.Now(),
	}
}

// Run executes the unified backup pipeline:
// Step 1: Downloads Index Spot candles via /v2/charts/intraday into /app/data/users/{uid}/{index}_index/
// Step 2: Downloads Option Strikes (ATM±strikeCount CE & PE) via /v2/charts/rollingoption into /app/data/users/{uid}/{index}_options/
func (j *BackupJob) Run(ctx context.Context) {
	taskID := j.payload.TaskID
	params := j.payload.Params

	indexName := params.IndexName
	securityID := params.SecurityID
	exchangeSegment := params.ExchangeSegment
	startDate := params.StartDate
	endDate := params.EndDate
	expiryDate := params.ExpiryDate
	strikeCount := params.StrikeCount
	userID := params.UserID
	if userID == "" {
		userID = "1"
	}
	if strikeCount <= 0 {
		strikeCount = 5
	}
	if securityID == "" {
		securityID = getIndexSecurityID(indexName)
	}

	log.Printf("🚀 [Task #%s] Starting Unified Backup (Spot Index + ATM±%d Option Strikes) for User #%s | %s → %s",
		taskID, strikeCount, userID, startDate, endDate)

	existingProgress, err := j.dbService.GetTaskProgress(ctx, taskID)
	if err != nil {
		existingProgress = 0
	}

	startProgress := 5
	if existingProgress > 5 && existingProgress < 100 && j.payload.Command != "START" {
		startProgress = existingProgress
	}

	if err := j.dbService.UpdateTaskProgress(ctx, taskID, "running", startProgress); err != nil {
		log.Printf("⚠️ [Task #%s] Failed to set initial DB status: %v\n", taskID, err)
		return
	}
	j.broadcastProgress(ctx, taskID, startProgress, "running", 0.0, "")

	backupTaskDir := fmt.Sprintf("/app/backup/%s/%s", userID, taskID)

	// ── STEP 1: Download Index Spot Data ─────────────────────────────────────
	log.Printf("📥 [Task #%s] [Step 1/2] Downloading Index Spot candles (%s)...", taskID, indexName)
	indexDir := j.downloadIndexSpot(ctx, taskID, userID, indexName, securityID, exchangeSegment, startDate, endDate, startProgress)

	select {
	case <-ctx.Done():
		log.Printf("🛑 [Task #%s] Backup task cancelled after Step 1.", taskID)
		return
	default:
	}

	optsDir := ""
	if strings.EqualFold(indexName, "INDIAVIX") || strikeCount <= 0 {
		log.Printf("ℹ️ [Task #%s] Skipping Option Strikes Download for %s (Index Spot only).", taskID, indexName)
	} else {
		// ── STEP 2: Download Expired Options Strikes (ATM±N CE & PE) ─────────────
		log.Printf("📥 [Task #%s] [Step 2/2] Downloading Option Strikes (ATM±%d CE & PE)...", taskID, strikeCount)
		optsDir = j.runOptionsDownload(ctx, taskID, userID, indexName, exchangeSegment, expiryDate, startDate, endDate, strikeCount, 45)
	}

	finalOutputDir := backupTaskDir
	if !dirExists(finalOutputDir) {
		finalOutputDir = optsDir
		if finalOutputDir == "" {
			finalOutputDir = indexDir
		}
	}

	// Calculate total directory storage size
	var totalSizeBytes int64 = 0
	_ = filepath.Walk(backupTaskDir, func(path string, info os.FileInfo, err error) error {
		if err == nil && !info.IsDir() {
			totalSizeBytes += info.Size()
		}
		return nil
	})

	fileSizeMB := float64(totalSizeBytes) / (1024 * 1024)

	if err := j.dbService.MarkTaskComplete(ctx, taskID, finalOutputDir, fileSizeMB); err != nil {
		log.Printf("❌ [Task #%s] Failed to mark completion: %v\n", taskID, err)
		j.broadcastProgress(ctx, taskID, 0, "error", fileSizeMB, finalOutputDir)
		return
	}

	log.Printf("✅ [Task #%s] Unified Backup Complete! Saved to %s (%.2f MB)\n", taskID, finalOutputDir, fileSizeMB)
	j.broadcastProgress(ctx, taskID, 100, "completed", fileSizeMB, finalOutputDir)
}

// helper dirExists checks if directory exists
func dirExists(path string) bool {
	info, err := os.Stat(path)
	if err != nil {
		return false
	}
	return info.IsDir()
}

// downloadIndexSpot downloads 1-minute OHLCV candles for the Index spot instrument (/v2/charts/intraday)
func (j *BackupJob) downloadIndexSpot(
	ctx context.Context,
	taskID, userID, indexName, securityID, exchangeSegment, startDate, endDate string,
	startProgress int,
) string {
	baseOutputDir := fmt.Sprintf("/app/backup/%s/%s/%s_index", userID, taskID, strings.ToLower(indexName))
	_ = os.MkdirAll(baseOutputDir, 0755)

	client := &http.Client{Timeout: 30 * time.Second}
	baseURL := "https://api.dhan.co/v2/charts/intraday"

	start, err := time.Parse("2006-01-02", startDate)
	if err != nil {
		log.Printf("⚠️ [Task #%s] Invalid start date: %v", taskID, err)
		return baseOutputDir
	}
	end, err := time.Parse("2006-01-02", endDate)
	if err != nil {
		log.Printf("⚠️ [Task #%s] Invalid end date: %v", taskID, err)
		return baseOutputDir
	}

	chunkDays := 30
	totalDays := int(end.Sub(start).Hours()/24) + 1
	if totalDays <= 0 {
		totalDays = 1
	}
	if chunkDays > totalDays {
		chunkDays = totalDays
	}
	totalChunks := (totalDays + chunkDays - 1) / chunkDays
	if totalChunks <= 0 {
		totalChunks = 1
	}

	completedChunks := 0
	chunkStart := start

	for chunkStart.Before(end) || chunkStart.Equal(end) {
		select {
		case <-ctx.Done():
			log.Printf("⏸️ [Task #%s] Index download interrupted.", taskID)
			return baseOutputDir
		default:
		}

		chunkEnd := chunkStart.AddDate(0, 0, chunkDays-1)
		if chunkEnd.After(end) {
			chunkEnd = end
		}

		reqPayload := map[string]interface{}{
			"securityId":      securityID,
			"exchangeSegment": "IDX_I",
			"instrument":      "INDEX",
			"interval":        "1",
			"oi":              false,
			"fromDate":        chunkStart.Format("2006-01-02") + " 09:15:00",
			"toDate":          chunkEnd.Format("2006-01-02") + " 15:30:00",
		}

		jsonBody, _ := json.Marshal(reqPayload)

		var bodyBytes []byte
		var respStatusCode int

		for attempt := 0; attempt < 3; attempt++ {
			req, err := http.NewRequestWithContext(ctx, "POST", baseURL, bytes.NewBuffer(jsonBody))
			if err != nil {
				break
			}
			req.Header.Set("Content-Type", "application/json")
			req.Header.Add("access-token", j.config.DhanAccessToken)
			req.Header.Add("client-id", j.config.DhanClientID)

			resp, err := client.Do(req)
			if err != nil {
				log.Printf("⚠️ [Task #%s] Index API error: %v", taskID, err)
				time.Sleep(300 * time.Millisecond)
				continue
			}
			bodyBytes, _ = io.ReadAll(resp.Body)
			respStatusCode = resp.StatusCode
			resp.Body.Close()

			if respStatusCode == http.StatusTooManyRequests {
				log.Printf("⚠️ [Task #%s] Index API HTTP 429 Rate Limit. Retrying in 1.5s (Attempt %d/3)...", taskID, attempt+1)
				time.Sleep(1500 * time.Millisecond)
				continue
			}
			break
		}

		time.Sleep(100 * time.Millisecond)

		if respStatusCode == http.StatusOK {
			candles := parseHistoricalResponse(bodyBytes, indexName)
			if len(candles) > 0 {
				candlesByDate := make(map[string][]map[string]interface{})
				for _, candle := range candles {
					dateStr, _ := candle["date"].(string)
					if dateStr != "" {
						candlesByDate[dateStr] = append(candlesByDate[dateStr], candle)
					}
				}

				for dateStr, dayCandles := range candlesByDate {
					t, parseErr := time.Parse("2006-01-02", dateStr)
					if parseErr != nil {
						continue
					}
					partitionDir := filepath.Join(baseOutputDir, fmt.Sprintf("year=%s", t.Format("2006")), fmt.Sprintf("month=%s", t.Format("01")))
					_ = os.MkdirAll(partitionDir, 0755)

					dayFilePath := filepath.Join(partitionDir, fmt.Sprintf("%s.parquet", dateStr))
					dayFile, openErr := os.OpenFile(dayFilePath, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
					if openErr == nil {
						var buf bytes.Buffer
						for _, candle := range dayCandles {
							line, _ := json.Marshal(candle)
							buf.Write(line)
							buf.WriteByte('\n')
						}
						_, _ = dayFile.Write(buf.Bytes())
						dayFile.Close()
					}
				}
				log.Printf("📊 [Task #%s] Index Spot: Fetched %d candles for %s to %s\n", taskID, len(candles), chunkStart.Format("2006-01-02"), chunkEnd.Format("2006-01-02"))
			}
		} else {
			log.Printf("⚠️ [Task #%s] Index API HTTP %d: %s", taskID, respStatusCode, string(bodyBytes))
		}

		completedChunks++
		progress := startProgress + int((float64(completedChunks)/float64(totalChunks))*40)
		_ = j.dbService.UpdateTaskProgress(ctx, taskID, "running", progress)
		j.broadcastProgress(ctx, taskID, progress, "running", 0.0, baseOutputDir)

		chunkStart = chunkEnd.AddDate(0, 0, 1)
		time.Sleep(200 * time.Millisecond)
	}

	return baseOutputDir
}


// runOptionsDownload fetches historical options data via DhanHQ v2 Expired Options Rolling API (/v2/charts/rollingoption)
// Uses concurrent worker pool for high-throughput parallel data ingestion.
func (j *BackupJob) runOptionsDownload(
	ctx context.Context,
	taskID, userID, indexName, exchangeSegment, expiryDate, startDate, endDate string,
	strikeCount, startProgress int,
) string {
	log.Printf("🚀 [Task #%s] Starting Parallel Options Rolling Data Download for %s (Strikes count=%d)", taskID, indexName, strikeCount)

	securityID := getIndexSecurityID(indexName)
	relativeStrikes := generateRelativeStrikes(strikeCount)
	optionTypes := []string{"CALL", "PUT"}
	totalContracts := len(relativeStrikes) * len(optionTypes)

	tr := &http.Transport{
		MaxIdleConns:        100,
		MaxIdleConnsPerHost: 20,
		IdleConnTimeout:     90 * time.Second,
	}
	client := &http.Client{
		Transport: tr,
		Timeout:   30 * time.Second,
	}

	baseURL := "https://api.dhan.co/v2/charts/rollingoption"
	baseOutputDir := fmt.Sprintf("/app/backup/%s/%s/%s_options", userID, taskID, strings.ToLower(indexName))

	type strikeItem struct {
		drvOptType string
		strikeName string
	}

	tasks := make(chan strikeItem, totalContracts)
	for _, drvOptType := range optionTypes {
		for _, strikeName := range relativeStrikes {
			tasks <- strikeItem{drvOptType: drvOptType, strikeName: strikeName}
		}
	}
	close(tasks)

	workerCount := 2
	var wg sync.WaitGroup
	var completedCount int32

	for i := 0; i < workerCount; i++ {
		if i > 0 {
			time.Sleep(250 * time.Millisecond)
		}
		wg.Add(1)
		go func() {
			defer wg.Done()
			for item := range tasks {
				select {
				case <-ctx.Done():
					return
				default:
				}

				contractDir := fmt.Sprintf("%s/%s/%s", baseOutputDir, item.drvOptType, item.strikeName)
				_ = os.MkdirAll(contractDir, 0755)

				j.downloadRollingOptionCandles(
					ctx, taskID, securityID, "NSE_FNO", "OPTIDX",
					item.strikeName, item.drvOptType, startDate, endDate, contractDir, client, baseURL,
				)

				done := atomic.AddInt32(&completedCount, 1)
				progress := startProgress + int(float64(done)/float64(totalContracts)*float64(95-startProgress))
				_ = j.dbService.UpdateTaskProgress(ctx, taskID, "running", progress)
				j.broadcastProgress(ctx, taskID, progress, "running", 0.0, contractDir)
				time.Sleep(200 * time.Millisecond)
			}
		}()
	}

	wg.Wait()
	return baseOutputDir
}

// downloadRollingOptionCandles handles 30-day chunked calls to /v2/charts/rollingoption
func (j *BackupJob) downloadRollingOptionCandles(
	ctx context.Context,
	taskID, securityID, exchangeSegment, instrument, strikeName, drvOptionType, startDate, endDate, outputDir string,
	client *http.Client, baseURL string,
) {
	start, err := time.Parse("2006-01-02", startDate)
	if err != nil {
		log.Printf("⚠️ [Task #%s] Invalid start date %s: %v", taskID, startDate, err)
		return
	}
	end, err := time.Parse("2006-01-02", endDate)
	if err != nil {
		log.Printf("⚠️ [Task #%s] Invalid end date %s: %v", taskID, endDate, err)
		return
	}

	ist, _ := time.LoadLocation("Asia/Kolkata")
	chunkDays := 30 // Max 30 days per call as per DhanHQ documentation

	for chunkStart := start; !chunkStart.After(end); chunkStart = chunkStart.AddDate(0, 0, chunkDays) {
		select {
		case <-ctx.Done():
			return
		default:
		}

		chunkEnd := chunkStart.AddDate(0, 0, chunkDays-1)
		if chunkEnd.After(end) {
			chunkEnd = end
		}

		reqPayload := map[string]interface{}{
			"exchangeSegment": exchangeSegment,
			"interval":        "1",
			"securityId":      securityID,
			"instrument":      instrument,
			"expiryFlag":      "WEEK",
			"expiryCode":      1,
			"strike":          strikeName,
			"drvOptionType":   drvOptionType,
			"requiredData": []string{
				"open", "high", "low", "close", "volume", "oi", "iv", "spot", "strike",
			},
			"fromDate": chunkStart.Format("2006-01-02"),
			"toDate":   chunkEnd.Format("2006-01-02"),
		}

		jsonBody, _ := json.Marshal(reqPayload)

		var bodyBytes []byte
		var respStatusCode int

		for attempt := 0; attempt < 3; attempt++ {
			req, err := http.NewRequestWithContext(ctx, "POST", baseURL, bytes.NewBuffer(jsonBody))
			if err != nil {
				break
			}
			req.Header.Set("Content-Type", "application/json")
			req.Header.Set("Accept", "application/json")
			req.Header.Add("access-token", j.config.DhanAccessToken)
			req.Header.Add("client-id", j.config.DhanClientID)

			resp, err := client.Do(req)
			if err != nil {
				log.Printf("⚠️ [Task #%s] Rolling option API error for strike %s: %v", taskID, strikeName, err)
				time.Sleep(300 * time.Millisecond)
				continue
			}
			bodyBytes, _ = io.ReadAll(resp.Body)
			respStatusCode = resp.StatusCode
			resp.Body.Close()

			if respStatusCode == http.StatusTooManyRequests {
				log.Printf("⚠️ [Task #%s] HTTP 429 Rate Limit for %s %s. Retrying in 2s (Attempt %d/3)...", taskID, drvOptionType, strikeName, attempt+1)
				time.Sleep(2 * time.Second)
				continue
			}
			break
		}

		if respStatusCode != http.StatusOK {
			log.Printf("⚠️ [Task #%s] HTTP %d for rolling option %s %s: %s", taskID, respStatusCode, drvOptionType, strikeName, string(bodyBytes))
			continue
		}

		candles := parseRollingOptionResponse(bodyBytes, drvOptionType)
		if len(candles) == 0 {
			continue
		}

		candlesByDate := make(map[string][]map[string]interface{})
		for _, candle := range candles {
			if dateStr, _ := candle["date"].(string); dateStr != "" {
				candlesByDate[dateStr] = append(candlesByDate[dateStr], candle)
			}
		}

		for dateStr, dayCandles := range candlesByDate {
			t, parseErr := time.ParseInLocation("2006-01-02", dateStr, ist)
			if parseErr != nil {
				continue
			}
			partDir := filepath.Join(outputDir, fmt.Sprintf("year=%s", t.Format("2006")), fmt.Sprintf("month=%s", t.Format("01")))
			_ = os.MkdirAll(partDir, 0755)

			dayFile, openErr := os.OpenFile(filepath.Join(partDir, dateStr+".parquet"), os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
			if openErr != nil {
				continue
			}
			var buf bytes.Buffer
			for _, candle := range dayCandles {
				line, _ := json.Marshal(candle)
				buf.Write(line)
				buf.WriteByte('\n')
			}
			_, _ = dayFile.Write(buf.Bytes())
			dayFile.Close()
		}
		time.Sleep(250 * time.Millisecond)
	}
}


// generateRelativeStrikes creates ATM, ATM+1..N, ATM-1..N strike strings
// Capped at maximum 10 as per official DhanHQ v2 Expired Options API specification (ATM+10 / ATM-10 max)
func generateRelativeStrikes(count int) []string {
	if count <= 0 {
		count = 5
	}
	if count > 10 {
		count = 10
	}
	strikes := []string{"ATM"}
	for i := 1; i <= count; i++ {
		strikes = append(strikes, fmt.Sprintf("ATM+%d", i))
		strikes = append(strikes, fmt.Sprintf("ATM-%d", i))
	}
	return strikes
}

// getIndexSecurityID maps index name to Dhan security ID
func getIndexSecurityID(indexName string) string {
	switch strings.ToUpper(indexName) {
	case "BANKNIFTY":
		return "25"
	case "FINNIFTY":
		return "27"
	case "MIDCPNIFTY":
		return "26"
	case "INDIAVIX", "INDIA VIX":
		return "17"
	default: // NIFTY
		return "13"
	}
}

// parseRollingOptionResponse extracts records from /charts/rollingoption payload
func parseRollingOptionResponse(body []byte, drvOptionType string) []map[string]interface{} {
	var resp map[string]json.RawMessage
	if err := json.Unmarshal(body, &resp); err != nil {
		return nil
	}

	var dataObj map[string]json.RawMessage
	if dataBytes, ok := resp["data"]; ok {
		_ = json.Unmarshal(dataBytes, &dataObj)
	} else {
		dataObj = resp
	}

	key := "ce"
	if strings.ToUpper(drvOptionType) == "PUT" {
		key = "pe"
	}

	optDataBytes, ok := dataObj[key]
	if !ok || string(optDataBytes) == "null" {
		return nil
	}

	var raw map[string]json.RawMessage
	if err := json.Unmarshal(optDataBytes, &raw); err != nil {
		return nil
	}

	opens := parseFloatArray(raw["open"])
	highs := parseFloatArray(raw["high"])
	lows := parseFloatArray(raw["low"])
	closes := parseFloatArray(raw["close"])
	volumes := parseIntArray(raw["volume"])
	ois := parseIntArray(raw["oi"])
	ivs := parseFloatArray(raw["iv"])
	spots := parseFloatArray(raw["spot"])
	strikes := parseFloatArray(raw["strike"])
	timestamps := parseTimestampArray(raw["timestamp"])

	ist, _ := time.LoadLocation("Asia/Kolkata")
	count := len(opens)
	candles := make([]map[string]interface{}, 0, count)

	for i := 0; i < count; i++ {
		var tsEpoch int64 = 0
		if i < len(timestamps) {
			tsEpoch = timestamps[i]
		}
		candleTime := time.Unix(tsEpoch, 0).In(ist)

		candle := map[string]interface{}{
			"timestamp":     tsEpoch,
			"datetime":      candleTime.Format("2006-01-02 15:04:05"),
			"date":          candleTime.Format("2006-01-02"),
			"open":          floatAt(opens, i),
			"high":          floatAt(highs, i),
			"low":           floatAt(lows, i),
			"close":         floatAt(closes, i),
			"volume":        intAt(volumes, i),
			"open_interest": intAt(ois, i),
			"iv":            floatAt(ivs, i),
			"spot":          floatAt(spots, i),
			"strike":        floatAt(strikes, i),
		}
		candles = append(candles, candle)
	}
	return candles
}



func (j *BackupJob) broadcastProgress(ctx context.Context, taskID string, progress int, status string, fileSizeMB float64, filePath string) {
	if j.hub == nil {
		log.Printf("🔇 [Task #%s] broadcastProgress skipped: hub is nil\n", taskID)
		return
	}

	var etaStr string
	var etaSec int
	if progress > 0 && progress < 100 {
		elapsed := time.Since(j.startTime)
		estimatedTotal := time.Duration(float64(elapsed) / (float64(progress) / 100.0))
		remaining := estimatedTotal - elapsed
		if remaining < 0 {
			remaining = 0
		}
		etaSec = int(remaining.Seconds())
		if etaSec < 60 {
			etaStr = fmt.Sprintf("~%ds left", etaSec)
		} else {
			etaStr = fmt.Sprintf("~%dm %ds left", etaSec/60, etaSec%60)
		}
	} else if progress >= 100 {
		etaStr = "Complete"
		etaSec = 0
	}

	msg := ws.ProgressMessage{
		Type:     "progress",
		TaskID:   taskID,
		Progress: progress,
		Status:   status,
		FileSize: fileSizeMB,
		FilePath: filePath,
		Eta:      etaStr,
		EtaSec:   etaSec,
	}
	data, err := json.Marshal(msg)
	if err != nil {
		log.Printf("⚠️ [Task #%s] broadcastProgress marshal error: %v\n", taskID, err)
		return
	}
	log.Printf("📡 [Task #%s] Broadcasting progress %d%% status=%s eta=%s to WS hub\n", taskID, progress, status, etaStr)
	j.hub.BroadcastToTask(taskID, data)
}

func parseHistoricalResponse(body []byte, indexName string) []map[string]interface{} {
	var resp map[string]json.RawMessage
	if err := json.Unmarshal(body, &resp); err != nil {
		log.Printf("⚠️ Failed to parse Dhan response: %v\n", err)
		return nil
	}

	var raw map[string]json.RawMessage
	if dataBytes, ok := resp["data"]; ok && string(dataBytes) != "null" {
		if err := json.Unmarshal(dataBytes, &raw); err != nil {
			log.Printf("⚠️ Failed to parse data field: %v\n", err)
			return nil
		}
	} else {
		raw = resp
	}

	opens := parseFloatArray(raw["open"])
	highs := parseFloatArray(raw["high"])
	lows := parseFloatArray(raw["low"])
	closes := parseFloatArray(raw["close"])
	volumes := parseIntArray(raw["volume"])

	timestamps := parseTimestampArray(raw["start_Time"])
	if len(timestamps) == 0 {
		timestamps = parseTimestampArray(raw["start_time"])
	}
	if len(timestamps) == 0 {
		timestamps = parseTimestampArray(raw["timestamp"])
	}
	if len(timestamps) == 0 {
		timestamps = parseTimestampArray(raw["date"])
	}
	log.Printf("[PARSE] opens=%d highs=%d lows=%d closes=%d volumes=%d timestamps=%d",
		len(opens), len(highs), len(lows), len(closes), len(volumes), len(timestamps))
	ois := parseIntArray(raw["open_interest"])

	// IST timezone for correct date partitioning (Indian market sessions)
	ist, _ := time.LoadLocation("Asia/Kolkata")

	count := len(opens)
	candles := make([]map[string]interface{}, 0, count)
	for i := 0; i < count; i++ {
		var tsEpoch int64 = 0
		if i < len(timestamps) {
			tsEpoch = timestamps[i]
		}
		candleTime := time.Unix(tsEpoch, 0).In(ist)
		candle := map[string]interface{}{
			"index_name":    indexName,
			"timestamp":     tsEpoch,
			"datetime":      candleTime.Format("2006-01-02 15:04:05"),
			"date":          candleTime.Format("2006-01-02"),
			"open":          floatAt(opens, i),
			"high":          floatAt(highs, i),
			"low":           floatAt(lows, i),
			"close":         floatAt(closes, i),
			"volume":        intAt(volumes, i),
			"open_interest": intAt(ois, i),
		}
		candles = append(candles, candle)
	}
	return candles
}

func parseFloatArray(raw json.RawMessage) []float64 {
	if len(raw) == 0 || string(raw) == "null" {
		return nil
	}
	var arr []float64
	_ = json.Unmarshal(raw, &arr)
	return arr
}

func parseIntArray(raw json.RawMessage) []int {
	if len(raw) == 0 || string(raw) == "null" {
		return nil
	}
	var arr []int
	_ = json.Unmarshal(raw, &arr)
	return arr
}

// parseTimestampArray safely parses Dhan timestamps.
// Handles numeric float64 arrays (epoch seconds/milliseconds) and string date arrays.
func parseTimestampArray(raw json.RawMessage) []int64 {
	if len(raw) == 0 || string(raw) == "null" {
		return nil
	}

	// 1. Try parsing float64 slice
	var floats []float64
	if err := json.Unmarshal(raw, &floats); err == nil && len(floats) > 0 {
		result := make([]int64, len(floats))
		for i, f := range floats {
			ts := int64(f)
			if ts > 1_000_000_000_000 { // milliseconds -> seconds
				ts = ts / 1000
			}
			result[i] = ts
		}
		log.Printf("[PARSE] Timestamps parsed as floats. Sample[0]: %d", result[0])
		return result
	}

	// 2. Try parsing string slice (e.g. "2024-09-11 09:30:00")
	var stringsArr []string
	if err := json.Unmarshal(raw, &stringsArr); err == nil && len(stringsArr) > 0 {
		ist, _ := time.LoadLocation("Asia/Kolkata")
		result := make([]int64, len(stringsArr))
		formats := []string{
			"2006-01-02 15:04:05",
			"2006-01-02T15:04:05",
			"2006-01-02T15:04:05Z",
			"2006-01-02",
		}
		for i, s := range stringsArr {
			sTrim := strings.TrimSpace(s)
			var parsedTime time.Time
			for _, fmtStr := range formats {
				if t, parseErr := time.ParseInLocation(fmtStr, sTrim, ist); parseErr == nil {
					parsedTime = t
					break
				}
			}
			if !parsedTime.IsZero() {
				result[i] = parsedTime.Unix()
			}
		}
		log.Printf("[PARSE] Timestamps parsed as strings. Sample[0]: %s -> epoch %d", stringsArr[0], result[0])
		return result
	}

	if string(raw) == "[]" || string(raw) == "null" || len(raw) == 0 {
		return nil
	}

	log.Printf("[PARSE] parseTimestampArray failed to parse (raw sample: %.80s)", string(raw))
	return nil
}

func floatAt(arr []float64, i int) float64 {
	if i < len(arr) {
		return arr[i]
	}
	return 0.0
}

func intAt(arr []int, i int) int {
	if i < len(arr) {
		return arr[i]
	}
	return 0
}
