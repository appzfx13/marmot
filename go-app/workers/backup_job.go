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
}

// NewBackupJob creates a new instance of BackupJob
func NewBackupJob(dbService *services.DBService, cfg *config.Config, payload models.CommandPayload, hub *ws.Hub) *BackupJob {
	return &BackupJob{
		dbService: dbService,
		config:    cfg,
		payload:   payload,
		hub:       hub,
	}
}

// Run executes the backup pipeline by calling DhanHQ /charts/historical API,
// partitioning candles by date inside /app/data/users/{user_id}/{index_name}_options/year=YYYY/month=MM/YYYY-MM-DD.parquet
func (j *BackupJob) Run(ctx context.Context) {
	taskID := j.payload.TaskID
	params := j.payload.Params

	indexName := params.IndexName
	securityID := params.SecurityID
	exchangeSegment := params.ExchangeSegment
	instrument := params.Instrument
	startDate := params.StartDate
	endDate := params.EndDate
	userID := params.UserID
	if userID == "" {
		userID = "1"
	}

	log.Printf("🚀 [Task #%s] Starting backup for User #%s, Index %s (%s) from %s to %s\n",
		taskID, userID, indexName, securityID, startDate, endDate)

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

	baseOutputDir := fmt.Sprintf("/app/data/users/%s/%s_options", userID, strings.ToLower(indexName))
	_ = os.MkdirAll(baseOutputDir, 0755)

	client := &http.Client{Timeout: 30 * time.Second}
	baseURL := "https://api.dhan.co/v2/charts/historical"

	start, err := time.Parse("2006-01-02", startDate)
	if err != nil {
		_ = j.dbService.RecordError(ctx, taskID, fmt.Sprintf("invalid start date: %v", err))
		return
	}
	end, err := time.Parse("2006-01-02", endDate)
	if err != nil {
		_ = j.dbService.RecordError(ctx, taskID, fmt.Sprintf("invalid end date: %v", err))
		return
	}

	chunkDays := 10
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
	if startProgress > 5 && startProgress < 100 {
		calculatedCompleted := (startProgress - 5) * totalChunks / 90
		if calculatedCompleted > 0 && calculatedCompleted < totalChunks {
			completedChunks = calculatedCompleted
			log.Printf("⏩ [Task #%s] Resuming from progress %d%% (skipped %d chunks)", taskID, startProgress, completedChunks)
		}
	}

	chunkStart := start
	if completedChunks > 0 {
		chunkStart = start.AddDate(0, 0, completedChunks*chunkDays)
	}

	for chunkStart.Before(end) || chunkStart.Equal(end) {
		select {
		case <-ctx.Done():
			log.Printf("⏸️ [Task #%s] Execution interrupted by control command.\n", taskID)
			return
		default:
		}

		chunkEnd := chunkStart.AddDate(0, 0, chunkDays-1)
		if chunkEnd.After(end) {
			chunkEnd = end
		}

		reqPayload := map[string]interface{}{
			"securityId":      securityID,
			"exchangeSegment": exchangeSegment,
			"instrument":      instrument,
			"expiryCode":      0,
			"oi":              false,
			"fromDate":        chunkStart.Format("2006-01-02"),
			"toDate":          chunkEnd.Format("2006-01-02"),
		}

		jsonBody, err := json.Marshal(reqPayload)
		if err != nil {
			errStr := fmt.Sprintf("[%s] Request marshal error: %v", time.Now().Format("2006-01-02 15:04:05"), err)
			log.Printf("⚠️ [Task #%s] %s\n", taskID, errStr)
			_ = j.dbService.RecordError(ctx, taskID, errStr)
			completedChunks++
			chunkStart = chunkEnd.AddDate(0, 0, 1)
			continue
		}

		req, err := http.NewRequestWithContext(ctx, "POST", baseURL, bytes.NewBuffer(jsonBody))
		if err != nil {
			errStr := fmt.Sprintf("[%s] HTTP request creation error: %v", time.Now().Format("2006-01-02 15:04:05"), err)
			log.Printf("⚠️ [Task #%s] %s\n", taskID, errStr)
			_ = j.dbService.RecordError(ctx, taskID, errStr)
			completedChunks++
			chunkStart = chunkEnd.AddDate(0, 0, 1)
			continue
		}
		req.Header.Set("Content-Type", "application/json")
		req.Header.Add("access-token", j.config.DhanAccessToken)
		req.Header.Add("client-id", j.config.DhanClientID)

		resp, err := client.Do(req)
		if err != nil {
			_ = os.RemoveAll(baseOutputDir)
			errStr := fmt.Sprintf("[%s] Dhan API request failed: %v", time.Now().Format("2006-01-02 15:04:05"), err)
			log.Printf("❌ [Task #%s] %s\n", taskID, errStr)
			_ = j.dbService.RecordError(ctx, taskID, errStr)
			j.broadcastProgress(ctx, taskID, startProgress, "error", 0.0, "")
			return
		}

		bodyBytes, readErr := io.ReadAll(resp.Body)
		resp.Body.Close()
		if readErr != nil {
			_ = os.RemoveAll(baseOutputDir)
			errStr := fmt.Sprintf("[%s] Failed to read Dhan API response body: %v", time.Now().Format("2006-01-02 15:04:05"), readErr)
			log.Printf("❌ [Task #%s] %s\n", taskID, errStr)
			_ = j.dbService.RecordError(ctx, taskID, errStr)
			j.broadcastProgress(ctx, taskID, startProgress, "error", 0.0, "")
			return
		}

		// Pretty-print raw API response in Go terminal logs
		var prettyJSON bytes.Buffer
		if jsonErr := json.Indent(&prettyJSON, bodyBytes, "", "  "); jsonErr == nil {
			log.Printf("\n==================== [DHAN API RESPONSE (HTTP %d)] ====================\n%s\n=======================================================================\n", resp.StatusCode, prettyJSON.String())
		} else {
			log.Printf("\n==================== [DHAN API RESPONSE (HTTP %d)] ====================\n%s\n=======================================================================\n", resp.StatusCode, string(bodyBytes))
		}

		if resp.StatusCode == http.StatusOK {
			candles := parseHistoricalResponse(bodyBytes, indexName)
			if len(candles) == 0 {
				_ = os.RemoveAll(baseOutputDir)
				errStr := fmt.Sprintf("[%s] Dhan API returned 0 candles for date range %s to %s. Check API token / access parameters.", time.Now().Format("2006-01-02 15:04:05"), chunkStart.Format("2006-01-02"), chunkEnd.Format("2006-01-02"))
				log.Printf("❌ [Task #%s] %s\n", taskID, errStr)
				_ = j.dbService.RecordError(ctx, taskID, errStr)
				j.broadcastProgress(ctx, taskID, startProgress, "error", 0.0, "")
				return
			}

			// Partition candles by Date into year=YYYY/month=MM/YYYY-MM-DD.parquet
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
					for _, candle := range dayCandles {
						line, _ := json.Marshal(candle)
						_, _ = dayFile.Write(line)
						_, _ = dayFile.WriteString("\n")
					}
					dayFile.Close()
				} else {
					errStr := fmt.Sprintf("[%s] Failed to open day file %s: %v", time.Now().Format("2006-01-02 15:04:05"), dayFilePath, openErr)
					_ = j.dbService.RecordError(ctx, taskID, errStr)
				}
			}
			log.Printf("📊 [Task #%s] Fetched %d candles for %s to %s\n", taskID, len(candles), chunkStart.Format("2006-01-02"), chunkEnd.Format("2006-01-02"))
		} else {
			_ = os.RemoveAll(baseOutputDir)
			errStr := fmt.Sprintf("[%s] Dhan API HTTP %d Error: %s", time.Now().Format("2006-01-02 15:04:05"), resp.StatusCode, string(bodyBytes))
			log.Printf("❌ [Task #%s] %s\n", taskID, errStr)
			_ = j.dbService.RecordError(ctx, taskID, errStr)
			j.broadcastProgress(ctx, taskID, startProgress, "error", 0.0, "")
			return
		}

		completedChunks++
		progress := 5 + int((float64(completedChunks)/float64(totalChunks))*90)
		if progress > 95 {
			progress = 95
		}
		log.Printf("📊 [Task #%s] Progress: %d%%\n", taskID, progress)
		_ = j.dbService.UpdateTaskProgress(ctx, taskID, "running", progress)
		j.broadcastProgress(ctx, taskID, progress, "running", 0.0, baseOutputDir)

		chunkStart = chunkEnd.AddDate(0, 0, 1)
		time.Sleep(1 * time.Second)
	}

	var totalSizeBytes int64 = 0
	_ = filepath.Walk(baseOutputDir, func(path string, info os.FileInfo, err error) error {
		if err == nil && !info.IsDir() {
			totalSizeBytes += info.Size()
		}
		return nil
	})

	if totalSizeBytes == 0 {
		_ = os.RemoveAll(baseOutputDir)
		errStr := fmt.Sprintf("[%s] Backup Task #%s failed: 0 candles written. Check Dhan API client ID, access token, or credentials.", time.Now().Format("2006-01-02 15:04:05"), taskID)
		log.Printf("❌ [Task #%s] %s\n", taskID, errStr)
		_ = j.dbService.RecordError(ctx, taskID, errStr)
		j.broadcastProgress(ctx, taskID, startProgress, "error", 0.0, "")
		return
	}

	fileSizeMB := float64(totalSizeBytes) / (1024 * 1024)

	if err := j.dbService.MarkTaskComplete(ctx, taskID, baseOutputDir, fileSizeMB); err != nil {
		log.Printf("❌ [Task #%s] Failed to mark completion: %v\n", taskID, err)
		j.broadcastProgress(ctx, taskID, 0, "error", fileSizeMB, baseOutputDir)
		return
	}
	log.Printf("✅ [Task #%s] Completed! Partitioned output: %s (%.2f MB)\n", taskID, baseOutputDir, fileSizeMB)
	j.broadcastProgress(ctx, taskID, 100, "completed", fileSizeMB, baseOutputDir)
}

func (j *BackupJob) broadcastProgress(ctx context.Context, taskID string, progress int, status string, fileSizeMB float64, filePath string) {
	if j.hub == nil {
		log.Printf("🔇 [Task #%s] broadcastProgress skipped: hub is nil\n", taskID)
		return
	}
	msg := ws.ProgressMessage{
		Type:     "progress",
		TaskID:   taskID,
		Progress: progress,
		Status:   status,
		FileSize: fileSizeMB,
		FilePath: filePath,
	}
	data, err := json.Marshal(msg)
	if err != nil {
		log.Printf("⚠️ [Task #%s] broadcastProgress marshal error: %v\n", taskID, err)
		return
	}
	log.Printf("📡 [Task #%s] Broadcasting progress %d%% status=%s to WS hub\n", taskID, progress, status)
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
	
	timestamps := parseIntArray(raw["start_Time"])
	if len(timestamps) == 0 {
		timestamps = parseIntArray(raw["timestamp"])
	}
	ois := parseIntArray(raw["open_interest"])

	count := len(opens)
	candles := make([]map[string]interface{}, 0, count)
	for i := 0; i < count; i++ {
		ts := 0
		if i < len(timestamps) {
			ts = timestamps[i]
		}
		candle := map[string]interface{}{
			"index_name":    indexName,
			"timestamp":     ts,
			"date":          time.Unix(int64(ts), 0).UTC().Format("2006-01-02"),
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
