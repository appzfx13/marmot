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
	"time"

	"go-app/config"
	"go-app/models"
	"go-app/services"
	"go-app/ws"
)

// BackupJob handles the downloading, processing, and Parquet serialization logic
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

// Run executes the backup pipeline by calling DhanHQ /charts/historical API
// and writing the candle data as JSONL
func (j *BackupJob) Run(ctx context.Context) {
	taskID := j.payload.TaskID
	params := j.payload.Params

	indexName := params.IndexName
	securityID := params.SecurityID
	exchangeSegment := params.ExchangeSegment
	instrument := params.Instrument
	startDate := params.StartDate
	endDate := params.EndDate

	log.Printf("🚀 [Task #%s] Starting backup for %s (%s) from %s to %s\n",
		taskID, indexName, securityID, startDate, endDate)

	existingProgress, err := j.dbService.GetTaskProgress(ctx, taskID)
	if err != nil {
		existingProgress = 0
	}

	startProgress := 5
	if existingProgress > 5 {
		startProgress = existingProgress
	}

	if err := j.dbService.UpdateTaskProgress(ctx, taskID, "running", startProgress); err != nil {
		log.Printf("⚠️ [Task #%s] Failed to set initial DB status: %v\n", taskID, err)
		return
	}
	j.broadcastProgress(ctx, taskID, startProgress, "running", 0.0, "")

	outputDir := "/app/data/backups"
	_ = os.MkdirAll(outputDir, 0755)
	fileName := fmt.Sprintf("%s_%s_%s.jsonl", indexName, taskID, time.Now().Format("20060102_150405"))
	fullFilePath := filepath.Join(outputDir, fileName)

	file, err := os.OpenFile(fullFilePath, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err != nil {
		_ = j.dbService.RecordError(ctx, taskID, fmt.Sprintf("failed to create output file: %v", err))
		return
	}
	defer file.Close()

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
	if startProgress > 5 {
		// Reverse the progress formula: progress = 5 + (completed / total) * 90
		calculatedCompleted := (startProgress - 5) * totalChunks / 90
		if calculatedCompleted > 0 && calculatedCompleted <= totalChunks {
			completedChunks = calculatedCompleted
			log.Printf("⏩ [Task #%s] Resuming from progress %d%% (skipped %d chunks)", taskID, startProgress, completedChunks)
		}
	}

	chunkStart := start
	if completedChunks > 0 {
		chunkStart = start.AddDate(0, 0, completedChunks*chunkDays)
	}

	for ; chunkStart.Before(end) || chunkStart.Equal(end); {
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
			log.Printf("⚠️ [Task #%s] Failed to marshal request: %v\n", taskID, err)
			completedChunks++
			chunkStart = chunkEnd.AddDate(0, 0, 1)
			continue
		}

		req, err := http.NewRequestWithContext(ctx, "POST", baseURL, bytes.NewBuffer(jsonBody))
		if err != nil {
			log.Printf("⚠️ [Task #%s] Failed to create request: %v\n", taskID, err)
			completedChunks++
			chunkStart = chunkEnd.AddDate(0, 0, 1)
			continue
		}
		req.Header.Set("Content-Type", "application/json")
		req.Header.Add("access-token", j.config.DhanAccessToken)
		req.Header.Add("client-id", j.config.DhanClientID)

		resp, err := client.Do(req)
		if err != nil {
			log.Printf("⚠️ [Task #%s] Dhan API request failed: %v\n", taskID, err)
			time.Sleep(1 * time.Second)
			completedChunks++
			chunkStart = chunkEnd.AddDate(0, 0, 1)
			continue
		}

		if resp.StatusCode == http.StatusOK {
			body, err := io.ReadAll(resp.Body)
			resp.Body.Close()
			if err != nil {
				log.Printf("⚠️ [Task #%s] Failed to read response body: %v\n", taskID, err)
				completedChunks++
				chunkStart = chunkEnd.AddDate(0, 0, 1)
				continue
			}

			candles := parseHistoricalResponse(body, indexName)
			for _, candle := range candles {
				line, _ := json.Marshal(candle)
				if _, writeErr := file.Write(line); writeErr != nil {
					log.Printf("⚠️ [Task #%s] Failed to write candle: %v\n", taskID, writeErr)
				}
				if _, writeErr := file.WriteString("\n"); writeErr != nil {
					log.Printf("⚠️ [Task #%s] Failed to write newline: %v\n", taskID, writeErr)
				}
			}
			log.Printf("📊 [Task #%s] Fetched %d candles for %s to %s\n", taskID, len(candles), chunkStart.Format("2006-01-02"), chunkEnd.Format("2006-01-02"))
		} else {
			b, _ := io.ReadAll(resp.Body)
			resp.Body.Close()
			log.Printf("⚠️ [Task #%s] Dhan API error %d: %s\n", taskID, resp.StatusCode, string(b))
		}

		completedChunks++
		progress := 5 + int((float64(completedChunks)/float64(totalChunks))*90)
		if progress > 95 {
			progress = 95
		}
		log.Printf("📊 [Task #%s] Progress: %d%%\n", taskID, progress)
		_ = j.dbService.UpdateTaskProgress(ctx, taskID, "running", progress)
		j.broadcastProgress(ctx, taskID, progress, "running", 0.0, "")

		chunkStart = chunkEnd.AddDate(0, 0, 1)
		time.Sleep(1 * time.Second)
	}

	fileInfo, err := os.Stat(fullFilePath)
	var fileSizeMB float64 = 0.0
	if err == nil {
		fileSizeMB = float64(fileInfo.Size()) / (1024 * 1024)
	}

	if err := j.dbService.MarkTaskComplete(ctx, taskID, fullFilePath, fileSizeMB); err != nil {
		log.Printf("❌ [Task #%s] Failed to mark completion: %v\n", taskID, err)
		j.broadcastProgress(ctx, taskID, 0, "error", fileSizeMB, fullFilePath)
		return
	}
	log.Printf("✅ [Task #%s] Completed! Output: %s (%.2f MB)\n", taskID, fullFilePath, fileSizeMB)
	j.broadcastProgress(ctx, taskID, 100, "completed", fileSizeMB, fullFilePath)
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
