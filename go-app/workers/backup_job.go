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

// BackupJob handles downloading, staged Parquet chunking, and consolidated single-file dataset creation.
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
// Step 1: Downloads Index Spot candles into staging parquet chunks.
// Step 2: Downloads Option Strikes (ATM±strikeCount CE & PE) into staging parquet chunks.
// Step 3: Consolidates all staging chunks into a single binary Apache Parquet file (/app/backup/{uid}/{task_id}/dataset.parquet).
func (j *BackupJob) Run(ctx context.Context) {
	taskID := j.payload.TaskID
	params := j.payload.Params

	indexName := params.IndexName
	securityID := params.SecurityID
	startDate := params.StartDate
	endDate := params.EndDate
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

	// Resolve Dhan credentials: payload-injected token takes priority over global config env vars
	dhanClientID := params.DhanClientID
	tokenSource := "payload"
	if dhanClientID == "" {
		dhanClientID = j.config.DhanClientID
		tokenSource = "config_env"
	}
	dhanAccessToken := params.DhanAccessToken
	if dhanAccessToken == "" {
		dhanAccessToken = j.config.DhanAccessToken
		tokenSource = "config_env"
	}

	log.Printf("🔑 [Task #%s] Dhan Auth | source=%s | client_id=%s | token_len=%d (preview: %s)",
		taskID, tokenSource, dhanClientID, len(dhanAccessToken), debugTokenPreview(dhanAccessToken))

	log.Printf("🚀 [Task #%s] Starting Unified Parquet Backup (Spot + ATM±%d Option Strikes) for User #%s | %s → %s",
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
	stagingDir := filepath.Join(backupTaskDir, "staging")
	_ = os.MkdirAll(stagingDir, 0755)

	// ── STEP 1: Download Index Spot Data into Staging Parquet ─────────────────
	log.Printf("📥 [Task #%s] [Step 1/2] Downloading Index Spot candles (%s)...", taskID, indexName)
	spotFiles := j.downloadIndexSpot(ctx, taskID, stagingDir, indexName, securityID, startDate, endDate, startProgress, dhanClientID, dhanAccessToken)

	select {
	case <-ctx.Done():
		log.Printf("⏸️ [Task #%s] Backup task paused/cancelled after Step 1.", taskID)
		return
	default:
	}

	// ── STEP 2: Download Option Strikes into Staging Parquet ───────────────────
	var optionFiles []string
	if strings.EqualFold(indexName, "INDIAVIX") || strikeCount <= 0 {
		log.Printf("ℹ️ [Task #%s] Skipping Option Strikes Download for %s (Index Spot only).", taskID, indexName)
	} else {
		log.Printf("📥 [Task #%s] [Step 2/2] Downloading Option Strikes (ATM±%d CE & PE)...", taskID, strikeCount)
		optionFiles = j.runOptionsDownload(ctx, taskID, stagingDir, indexName, startDate, endDate, strikeCount, 45, dhanClientID, dhanAccessToken)
	}

	select {
	case <-ctx.Done():
		log.Printf("⏸️ [Task #%s] Backup task paused/cancelled during Step 2.", taskID)
		return
	default:
	}

	// ── STEP 3: Consolidate Staged Chunks into Single Parquet File ────────────
	log.Printf("📦 [Task #%s] [Step 3/3] Merging staged chunks into consolidated single-file dataset.parquet...", taskID)
	var allStagedFiles []string
	allStagedFiles = append(allStagedFiles, spotFiles...)
	allStagedFiles = append(allStagedFiles, optionFiles...)

	// Find any other .parquet files in stagingDir that may have been created earlier
	_ = filepath.Walk(stagingDir, func(path string, info os.FileInfo, err error) error {
		if err == nil && !info.IsDir() && strings.HasSuffix(path, ".parquet") {
			found := false
			for _, f := range allStagedFiles {
				if f == path {
					found = true
					break
				}
			}
			if !found {
				allStagedFiles = append(allStagedFiles, path)
			}
		}
		return nil
	})

	finalDatasetFile := filepath.Join(backupTaskDir, "dataset.parquet")
	totalRows, fileSizeMB, mergeErr := services.MergeParquetFiles(finalDatasetFile, allStagedFiles)
	if mergeErr != nil {
		log.Printf("❌ [Task #%s] Failed to merge parquet dataset: %v\n", taskID, mergeErr)
		j.broadcastProgress(ctx, taskID, 0, "error", 0, "")
		return
	}

	// Clean up staging directory after successful consolidation
	_ = os.RemoveAll(stagingDir)

	if err := j.dbService.MarkTaskComplete(ctx, taskID, finalDatasetFile, fileSizeMB); err != nil {
		log.Printf("❌ [Task #%s] Failed to mark completion in DB: %v\n", taskID, err)
		j.broadcastProgress(ctx, taskID, 0, "error", fileSizeMB, finalDatasetFile)
		return
	}

	log.Printf("✅ [Task #%s] Unified Single-File Parquet Backup Complete! Saved: %s (%.2f MB, %d total records)\n",
		taskID, finalDatasetFile, fileSizeMB, totalRows)
	j.broadcastProgress(ctx, taskID, 100, "completed", fileSizeMB, finalDatasetFile)
}

// downloadIndexSpot downloads 1-minute OHLCV candles for Index spot into staging Parquet chunks
func (j *BackupJob) downloadIndexSpot(
	ctx context.Context,
	taskID, stagingDir, indexName, securityID, startDate, endDate string,
	startProgress int,
	dhanClientID, dhanAccessToken string,
) []string {
	var createdFiles []string
	client := &http.Client{Timeout: 30 * time.Second}
	baseURL := "https://api.dhan.co/v2/charts/intraday"

	start, err := time.Parse("2006-01-02", startDate)
	if err != nil {
		log.Printf("⚠️ [Task #%s] Invalid start date: %v", taskID, err)
		return nil
	}
	end, err := time.Parse("2006-01-02", endDate)
	if err != nil {
		log.Printf("⚠️ [Task #%s] Invalid end date: %v", taskID, err)
		return nil
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
			log.Printf("⏸️ [Task #%s] Index download interrupted for pause/cancel.", taskID)
			return createdFiles
		default:
		}

		chunkEnd := chunkStart.AddDate(0, 0, chunkDays-1)
		if chunkEnd.After(end) {
			chunkEnd = end
		}

		chunkFileName := fmt.Sprintf("spot_%s_%s_%s.parquet", strings.ToLower(indexName), chunkStart.Format("2006-01-02"), chunkEnd.Format("2006-01-02"))
		chunkFilePath := filepath.Join(stagingDir, chunkFileName)

		// Checkpoint resume check: if valid chunk already exists on disk, skip download!
		if rows, _, statErr := services.VerifyParquetFile(chunkFilePath); statErr == nil && rows > 0 {
			log.Printf("⏩ [Task #%s] Resumed: Skipping already downloaded spot chunk %s (%d rows)", taskID, chunkFileName, rows)
			createdFiles = append(createdFiles, chunkFilePath)
			completedChunks++
			chunkStart = chunkEnd.AddDate(0, 0, 1)
			continue
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
			req.Header.Add("access-token", dhanAccessToken)
			req.Header.Add("client-id", dhanClientID)

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
			records := parseHistoricalParquetRecords(bodyBytes, indexName)
			if len(records) > 0 {
				if writeErr := services.WriteChunkParquet(chunkFilePath, records); writeErr == nil {
					createdFiles = append(createdFiles, chunkFilePath)
					log.Printf("📊 [Task #%s] Index Spot: Written %d records to %s\n", taskID, len(records), chunkFileName)
				} else {
					log.Printf("⚠️ [Task #%s] Failed to write parquet chunk: %v", taskID, writeErr)
				}
			}
		} else {
			log.Printf("⚠️ [Task #%s] Index API HTTP %d: %s | client_id=%s | token_len=%d | token_preview=%s",
				taskID, respStatusCode, string(bodyBytes), dhanClientID, len(dhanAccessToken), debugTokenPreview(dhanAccessToken))
		}

		completedChunks++
		progress := startProgress + int((float64(completedChunks)/float64(totalChunks))*40)
		_ = j.dbService.UpdateTaskProgress(ctx, taskID, "running", progress)
		j.broadcastProgress(ctx, taskID, progress, "running", 0.0, chunkFilePath)

		chunkStart = chunkEnd.AddDate(0, 0, 1)
		time.Sleep(200 * time.Millisecond)
	}

	return createdFiles
}

// runOptionsDownload fetches historical options data via DhanHQ v2 Expired Options Rolling API into staging Parquet chunks
func (j *BackupJob) runOptionsDownload(
	ctx context.Context,
	taskID, stagingDir, indexName, startDate, endDate string,
	strikeCount, startProgress int,
	dhanClientID, dhanAccessToken string,
) []string {
	var createdFiles []string
	var filesMutex sync.Mutex

	securityID := getIndexSecurityID(indexName)
	relativeStrikes := generateRelativeStrikes(strikeCount)
	optionTypes := []string{"CALL", "PUT"}
	totalContracts := len(relativeStrikes) * len(optionTypes)

	tr := &http.Transport{
		MaxIdleConns:        100,
		MaxIdleConnsPerHost: 20,
		IdleConnTimeout:     90 * time.Second,
	}
	client := &http.Client{Transport: tr, Timeout: 35 * time.Second}
	baseURL := "https://api.dhan.co/v2/charts/rollingoption"

	type optionTask struct {
		strikeName    string
		drvOptionType string
	}

	tasksChan := make(chan optionTask, totalContracts)
	for _, strike := range relativeStrikes {
		for _, optType := range optionTypes {
			tasksChan <- optionTask{strikeName: strike, drvOptionType: optType}
		}
	}
	close(tasksChan)

	workerCount := 4
	if workerCount > totalContracts {
		workerCount = totalContracts
	}

	var completedContracts int32 = 0
	var wg sync.WaitGroup

	for w := 0; w < workerCount; w++ {
		wg.Add(1)
		go func(workerID int) {
			defer wg.Done()
			for task := range tasksChan {
				select {
				case <-ctx.Done():
					return
				default:
				}

				chunkFiles := j.downloadRollingOptionChunks(
					ctx, client, baseURL, taskID, stagingDir, indexName, securityID,
					task.strikeName, task.drvOptionType, startDate, endDate, dhanClientID, dhanAccessToken,
				)

				if len(chunkFiles) > 0 {
					filesMutex.Lock()
					createdFiles = append(createdFiles, chunkFiles...)
					filesMutex.Unlock()
				}

				done := atomic.AddInt32(&completedContracts, 1)
				currentProgress := startProgress + int((float64(done)/float64(totalContracts))*50)
				if currentProgress > 95 {
					currentProgress = 95
				}

				_ = j.dbService.UpdateTaskProgress(ctx, taskID, "running", currentProgress)
				j.broadcastProgress(ctx, taskID, currentProgress, "running", 0.0, "")
			}
		}(w)
	}

	wg.Wait()
	return createdFiles
}

func (j *BackupJob) downloadRollingOptionChunks(
	ctx context.Context,
	client *http.Client,
	baseURL, taskID, stagingDir, indexName, securityID, strikeName, drvOptionType, startDate, endDate string,
	dhanClientID, dhanAccessToken string,
) []string {
	var createdFiles []string
	start, err := time.Parse("2006-01-02", startDate)
	if err != nil {
		return nil
	}
	end, err := time.Parse("2006-01-02", endDate)
	if err != nil {
		return nil
	}

	chunkDays := 30
	chunkStart := start

	instrument := "OPTIDX"
	if strings.EqualFold(indexName, "INDIAVIX") {
		instrument = "INDEX"
	}

	for chunkStart.Before(end) || chunkStart.Equal(end) {
		select {
		case <-ctx.Done():
			return createdFiles
		default:
		}

		chunkEnd := chunkStart.AddDate(0, 0, chunkDays-1)
		if chunkEnd.After(end) {
			chunkEnd = end
		}

		cleanStrike := strings.ReplaceAll(strikeName, "+", "p")
		cleanStrike = strings.ReplaceAll(cleanStrike, "-", "m")
		chunkFileName := fmt.Sprintf("opt_%s_%s_%s_%s_%s.parquet",
			strings.ToLower(indexName), strings.ToLower(drvOptionType), cleanStrike,
			chunkStart.Format("2006-01-02"), chunkEnd.Format("2006-01-02"))
		chunkFilePath := filepath.Join(stagingDir, chunkFileName)

		// Checkpoint resume check: if valid chunk already exists on disk, skip download!
		if rows, _, statErr := services.VerifyParquetFile(chunkFilePath); statErr == nil && rows > 0 {
			createdFiles = append(createdFiles, chunkFilePath)
			chunkStart = chunkEnd.AddDate(0, 0, 1)
			continue
		}

		reqPayload := map[string]interface{}{
			"securityId":      securityID,
			"exchangeSegment": "NSE_FNO",
			"instrument":      instrument,
			"interval":        "1",
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
			req.Header.Add("access-token", dhanAccessToken)
			req.Header.Add("client-id", dhanClientID)

			resp, err := client.Do(req)
			if err != nil {
				time.Sleep(300 * time.Millisecond)
				continue
			}
			bodyBytes, _ = io.ReadAll(resp.Body)
			respStatusCode = resp.StatusCode
			resp.Body.Close()

			if respStatusCode == http.StatusTooManyRequests {
				time.Sleep(2 * time.Second)
				continue
			}
			break
		}

		if respStatusCode == http.StatusOK {
			records := parseRollingOptionParquetRecords(bodyBytes, indexName, strikeName, drvOptionType)
			if len(records) > 0 {
				if writeErr := services.WriteChunkParquet(chunkFilePath, records); writeErr == nil {
					createdFiles = append(createdFiles, chunkFilePath)
					log.Printf("📊 [Task #%s] Options %s %s: Written %d records to %s\n",
						taskID, drvOptionType, strikeName, len(records), chunkFileName)
				}
			}
		} else {
			log.Printf("⚠️ [Task #%s] HTTP %d for rolling option %s %s: %s | client_id=%s | token_len=%d | token_preview=%s",
				taskID, respStatusCode, drvOptionType, strikeName, string(bodyBytes), dhanClientID, len(dhanAccessToken), debugTokenPreview(dhanAccessToken))
		}

		chunkStart = chunkEnd.AddDate(0, 0, 1)
		time.Sleep(200 * time.Millisecond)
	}

	return createdFiles
}

// generateRelativeStrikes creates ATM, ATM+1..N, ATM-1..N strike strings
func generateRelativeStrikes(count int) []string {
	if count <= 0 {
		return []string{"ATM"}
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

// parseRollingOptionParquetRecords extracts records from /charts/rollingoption payload into MarketCandleRecord
func parseRollingOptionParquetRecords(body []byte, indexName, strikeName, drvOptionType string) []models.MarketCandleRecord {
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
	timestamps := parseTimestampArray(raw["timestamp"])

	ist, _ := time.LoadLocation("Asia/Kolkata")
	count := len(opens)
	records := make([]models.MarketCandleRecord, 0, count)

	for i := 0; i < count; i++ {
		var tsEpoch int64 = 0
		if i < len(timestamps) {
			tsEpoch = timestamps[i]
		}
		candleTime := time.Unix(tsEpoch, 0).In(ist)

		rec := models.MarketCandleRecord{
			Timestamp:      tsEpoch,
			Datetime:       candleTime.Format("2006-01-02 15:04:05"),
			IndexName:      indexName,
			InstrumentType: "OPTION",
			Strike:         strikeName,
			OptionType:     strings.ToUpper(drvOptionType),
			Open:           floatAt(opens, i),
			High:           floatAt(highs, i),
			Low:            floatAt(lows, i),
			Close:          floatAt(closes, i),
			Volume:         int64(intAt(volumes, i)),
			OI:             int64(intAt(ois, i)),
			IV:             floatAt(ivs, i),
			SpotPrice:      floatAt(spots, i),
		}
		records = append(records, rec)
	}
	return records
}

// parseHistoricalParquetRecords extracts records from /charts/intraday payload into MarketCandleRecord
func parseHistoricalParquetRecords(body []byte, indexName string) []models.MarketCandleRecord {
	var resp map[string]json.RawMessage
	if err := json.Unmarshal(body, &resp); err != nil {
		return nil
	}

	var raw map[string]json.RawMessage
	if dataBytes, ok := resp["data"]; ok && string(dataBytes) != "null" {
		if err := json.Unmarshal(dataBytes, &raw); err != nil {
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

	ist, _ := time.LoadLocation("Asia/Kolkata")
	count := len(opens)
	records := make([]models.MarketCandleRecord, 0, count)

	for i := 0; i < count; i++ {
		var tsEpoch int64 = 0
		if i < len(timestamps) {
			tsEpoch = timestamps[i]
		}
		candleTime := time.Unix(tsEpoch, 0).In(ist)
		closeVal := floatAt(closes, i)

		rec := models.MarketCandleRecord{
			Timestamp:      tsEpoch,
			Datetime:       candleTime.Format("2006-01-02 15:04:05"),
			IndexName:      indexName,
			InstrumentType: "INDEX",
			Strike:         "SPOT",
			OptionType:     "INDEX",
			Open:           floatAt(opens, i),
			High:           floatAt(highs, i),
			Low:            floatAt(lows, i),
			Close:          closeVal,
			Volume:         int64(intAt(volumes, i)),
			OI:             0,
			IV:             0.0,
			SpotPrice:      closeVal,
		}
		records = append(records, rec)
	}
	return records
}

func (j *BackupJob) broadcastProgress(ctx context.Context, taskID string, progress int, status string, fileSizeMB float64, filePath string) {
	if j.hub == nil {
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
		return
	}
	log.Printf("📡 [Task #%s] Broadcasting progress %d%% status=%s eta=%s to WS hub\n", taskID, progress, status, etaStr)
	j.hub.BroadcastToTask(taskID, data)
}

func parseFloatArray(raw json.RawMessage) []float64 {
	if len(raw) == 0 || string(raw) == "null" {
		return nil
	}
	var arr []float64
	if err := json.Unmarshal(raw, &arr); err == nil {
		return arr
	}
	return nil
}

func parseIntArray(raw json.RawMessage) []int {
	if len(raw) == 0 || string(raw) == "null" {
		return nil
	}
	var arr []int
	if err := json.Unmarshal(raw, &arr); err == nil {
		return arr
	}
	return nil
}

func parseTimestampArray(raw json.RawMessage) []int64 {
	if len(raw) == 0 || string(raw) == "null" {
		return nil
	}

	var floatArr []float64
	if err := json.Unmarshal(raw, &floatArr); err == nil && len(floatArr) > 0 {
		result := make([]int64, len(floatArr))
		for i, f := range floatArr {
			result[i] = int64(f)
		}
		return result
	}

	var intArr []int64
	if err := json.Unmarshal(raw, &intArr); err == nil && len(intArr) > 0 {
		return intArr
	}

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
		return result
	}

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

func debugTokenPreview(s string) string {
	if s == "" {
		return "<EMPTY>"
	}
	if len(s) > 12 {
		return s[:6] + "..." + s[len(s)-4:]
	}
	return s
}
