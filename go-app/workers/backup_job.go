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

// Run executes the backup pipeline. For INDEX instrument it downloads spot candles.
// For OPTIDX instrument it loads the scrip master, calculates ATM±StrikeCount strikes,
// and downloads each CE + PE contract separately.
func (j *BackupJob) Run(ctx context.Context) {
	taskID := j.payload.TaskID
	params := j.payload.Params

	indexName := params.IndexName
	securityID := params.SecurityID
	exchangeSegment := params.ExchangeSegment
	instrument := params.Instrument
	startDate := params.StartDate
	endDate := params.EndDate
	expiryDate := params.ExpiryDate
	strikeCount := params.StrikeCount
	userID := params.UserID
	if userID == "" {
		userID = "1"
	}

	log.Printf("🚀 [Task #%s] Starting backup for User #%s | Index=%s | Instrument=%s | Strikes=%d | %s → %s",
		taskID, userID, indexName, instrument, strikeCount, startDate, endDate)

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

	// Branch: options multi-strike download vs simple index download
	if strings.ToUpper(instrument) == "OPTIDX" {
		j.runOptionsDownload(ctx, taskID, userID, indexName, exchangeSegment, expiryDate, startDate, endDate, strikeCount, startProgress)
		return
	}

	// ── INDEX (spot) download — Intraday API ─────────────────────────────────
	baseOutputDir := fmt.Sprintf("/app/data/users/%s/%s_index", userID, strings.ToLower(indexName))
	_ = os.MkdirAll(baseOutputDir, 0755)

	client := &http.Client{Timeout: 30 * time.Second}
	baseURL := "https://api.dhan.co/v2/charts/intraday"

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

	chunkDays := 30 // Max 90 days allowed for intraday, using 30 for safety
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
			"interval":        "1",
			"oi":              false,
			"fromDate":        chunkStart.Format("2006-01-02") + " 09:15:00",
			"toDate":          chunkEnd.Format("2006-01-02") + " 15:30:00",
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
		time.Sleep(250 * time.Millisecond)
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

// runOptionsDownload fetches historical options data via DhanHQ v2 Expired Options Rolling API (/v2/charts/rollingoption)
// It fetches relative strikes (ATM, ATM+1..N, ATM-1..N) for both CALL and PUT.
// Output: /app/data/users/{uid}/{index}_options/{CALL|PUT}/{strike_name}/year=YYYY/month=MM/YYYY-MM-DD.parquet
func (j *BackupJob) runOptionsDownload(
	ctx context.Context,
	taskID, userID, indexName, exchangeSegment, expiryDate, startDate, endDate string,
	strikeCount, startProgress int,
) {
	log.Printf("🚀 [Task #%s] Starting Expired Options Rolling Data Download for %s (Strikes count=%d)", taskID, indexName, strikeCount)

	securityID := getIndexSecurityID(indexName)
	relativeStrikes := generateRelativeStrikes(strikeCount)
	optionTypes := []string{"CALL", "PUT"}
	totalContracts := len(relativeStrikes) * len(optionTypes)

	client := &http.Client{Timeout: 30 * time.Second}
	baseURL := "https://api.dhan.co/v2/charts/rollingoption"
	baseOutputDir := fmt.Sprintf("/app/data/users/%s/%s_options", userID, strings.ToLower(indexName))

	completedContracts := 0
	for _, drvOptType := range optionTypes {
		for _, strikeName := range relativeStrikes {
			select {
			case <-ctx.Done():
				log.Printf("⏸️ [Task #%s] Options download interrupted.", taskID)
				return
			default:
			}

			contractDir := fmt.Sprintf("%s/%s/%s", baseOutputDir, drvOptType, strikeName)
			_ = os.MkdirAll(contractDir, 0755)

			log.Printf("📥 [Task #%s] Downloading %s %s %s | SecurityID=%s | %s → %s",
				taskID, indexName, drvOptType, strikeName, securityID, startDate, endDate)

			j.downloadRollingOptionCandles(
				ctx, taskID, securityID, "NSE_FNO", "OPTIDX",
				strikeName, drvOptType, startDate, endDate, contractDir, client, baseURL,
			)

			completedContracts++
			progress := startProgress + int(float64(completedContracts)/float64(totalContracts)*float64(95-startProgress))
			_ = j.dbService.UpdateTaskProgress(ctx, taskID, "running", progress)
			j.broadcastProgress(ctx, taskID, progress, "running", 0.0, contractDir)

			time.Sleep(250 * time.Millisecond) // rate limit buffer
		}
	}

	var totalSizeBytes int64
	_ = filepath.Walk(baseOutputDir, func(path string, info os.FileInfo, err error) error {
		if err == nil && !info.IsDir() {
			totalSizeBytes += info.Size()
		}
		return nil
	})

	fileSizeMB := float64(totalSizeBytes) / (1024 * 1024)
	if err := j.dbService.MarkTaskComplete(ctx, taskID, baseOutputDir, fileSizeMB); err != nil {
		log.Printf("❌ [Task #%s] Failed to mark options download complete: %v", taskID, err)
		j.broadcastProgress(ctx, taskID, 0, "error", fileSizeMB, baseOutputDir)
		return
	}
	log.Printf("✅ [Task #%s] Options download complete: %s (%.2f MB)", taskID, baseOutputDir, fileSizeMB)
	j.broadcastProgress(ctx, taskID, 100, "completed", fileSizeMB, baseOutputDir)
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
		req, err := http.NewRequestWithContext(ctx, "POST", baseURL, bytes.NewBuffer(jsonBody))
		if err != nil {
			continue
		}
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("Accept", "application/json")
		req.Header.Add("access-token", j.config.DhanAccessToken)
		req.Header.Add("client-id", j.config.DhanClientID)

		resp, err := client.Do(req)
		if err != nil {
			log.Printf("⚠️ [Task #%s] Rolling option API error for strike %s: %v", taskID, strikeName, err)
			continue
		}
		bodyBytes, _ := io.ReadAll(resp.Body)
		resp.Body.Close()

		if resp.StatusCode != http.StatusOK {
			log.Printf("⚠️ [Task #%s] HTTP %d for rolling option %s %s: %s", taskID, resp.StatusCode, drvOptionType, strikeName, string(bodyBytes))
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
			for _, candle := range dayCandles {
				line, _ := json.Marshal(candle)
				_, _ = dayFile.Write(line)
				_, _ = dayFile.WriteString("\n")
			}
			dayFile.Close()
		}
		time.Sleep(200 * time.Millisecond)
	}
}

// generateRelativeStrikes creates ATM, ATM+1..N, ATM-1..N strike strings
func generateRelativeStrikes(count int) []string {
	if count <= 0 {
		count = 5
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
