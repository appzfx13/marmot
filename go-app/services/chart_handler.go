package services

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

// ChartCandle represents a single candle formatted for TradingView Lightweight Charts
type ChartCandle struct {
	Time         int64   `json:"time"`
	Open         float64 `json:"open"`
	High         float64 `json:"high"`
	Low          float64 `json:"low"`
	Close        float64 `json:"close"`
	Volume       int     `json:"volume"`
	OpenInterest int     `json:"open_interest,omitempty"`
	IV           float64 `json:"iv,omitempty"`
	Spot         float64 `json:"spot,omitempty"`
	Strike       float64 `json:"strike,omitempty"`
	DateTime     string  `json:"datetime,omitempty"`
}

// ChartResponse represents the JSON payload returned to the frontend TradingView terminal
type ChartResponse struct {
	Status           string        `json:"status"`
	TaskID           string        `json:"task_id"`
	IndexName        string        `json:"index_name"`
	SelectedSub      string        `json:"selected_sub"`
	AvailableOptions []string      `json:"available_options"`
	Count            int           `json:"count"`
	Candles          []ChartCandle `json:"candles"`
}

// ServeChartData handles GET /api/chart?task_id=1&sub=CALL/ATM
func ServeChartData(dbService *DBService, w http.ResponseWriter, r *http.Request) {
	// Enable CORS for frontend Django templates
	w.Header().Set("Access-Control-Allow-Origin", "*")
	w.Header().Set("Access-Control-Allow-Methods", "GET, OPTIONS")
	w.Header().Set("Access-Control-Allow-Headers", "Content-Type")
	w.Header().Set("Content-Type", "application/json")

	if r.Method == http.MethodOptions {
		w.WriteHeader(http.StatusOK)
		return
	}

	taskID := r.URL.Query().Get("task_id")
	if taskID == "" {
		http.Error(w, `{"status":"error","message":"task_id is required"}`, http.StatusBadRequest)
		return
	}

	subfolder := strings.TrimSpace(r.URL.Query().Get("sub"))

	// Query Task info from Postgres DB
	ctx := context.Background()
	query := fmt.Sprintf(`
		SELECT index_name, parquet_file_path, created_by_id 
		FROM %s WHERE id = $1
	`, dbService.TableName)

	var indexName, parquetPath string
	var createdByID *int
	err := dbService.Pool.QueryRow(ctx, query, taskID).Scan(&indexName, &parquetPath, &createdByID)
	if err != nil {
		log.Printf("⚠️ [Chart API] Task #%s not found in DB: %v", taskID, err)
		http.Error(w, `{"status":"error","message":"task not found"}`, http.StatusNotFound)
		return
	}

	userID := "1"
	if createdByID != nil {
		userID = fmt.Sprintf("%d", *createdByID)
	}

	// Scan both index and options directories for user and index
	idxLower := strings.ToLower(indexName)
	indexPath := fmt.Sprintf("/app/data/users/%s/%s_index", userID, idxLower)
	optsPath := fmt.Sprintf("/app/data/users/%s/%s_options", userID, idxLower)

	// If DB parquetPath is set and exists, check task-specific output directories
	if parquetPath != "" && dirExists(parquetPath) {
		if strings.HasSuffix(parquetPath, "_index") {
			indexPath = parquetPath
		} else if strings.HasSuffix(parquetPath, "_options") {
			optsPath = parquetPath
		} else {
			taskIdxDir := filepath.Join(parquetPath, fmt.Sprintf("%s_index", idxLower))
			taskOptDir := filepath.Join(parquetPath, fmt.Sprintf("%s_options", idxLower))
			if dirExists(taskIdxDir) {
				indexPath = taskIdxDir
			}
			if dirExists(taskOptDir) {
				optsPath = taskOptDir
			}
		}
	}

	// Discover all available contracts across index & options dirs
	availableSubs := discoverSubfoldersMulti(indexPath, optsPath)

	// Determine target directory for reading candles
	targetDir := ""
	if subfolder == "" || subfolder == "Index Spot" {
		if dirExists(indexPath) {
			targetDir = indexPath
		} else {
			targetDir = optsPath
		}
	} else {
		// e.g. subfolder = "CALL/ATM" or "PUT/ATM+1"
		targetDir = filepath.Join(optsPath, subfolder)
		if !dirExists(targetDir) {
			// Fallback check under indexPath
			targetDir = filepath.Join(indexPath, subfolder)
		}
	}

	log.Printf("📈 [Chart API] Task #%s | Index=%s | Sub=%s | TargetDir=%s", taskID, indexName, subfolder, targetDir)

	// Read and parse all candles from parquet files in targetDir
	candles, err := readParquetCandles(targetDir)
	if err != nil {
		log.Printf("⚠️ [Chart API] Error reading candles: %v", err)
		http.Error(w, fmt.Sprintf(`{"status":"error","message":"failed to read data from %s: %v"}`, targetDir, err), http.StatusInternalServerError)
		return
	}

	resp := ChartResponse{
		Status:           "success",
		TaskID:           taskID,
		IndexName:        indexName,
		SelectedSub:      subfolder,
		AvailableOptions: availableSubs,
		Count:            len(candles),
		Candles:          candles,
	}

	json.NewEncoder(w).Encode(resp)
}

func dirExists(path string) bool {
	info, err := os.Stat(path)
	return err == nil && info.IsDir()
}

// discoverSubfoldersMulti scans both index & options paths for CALL/..., PUT/... and Index Spot
func discoverSubfoldersMulti(indexPath, optsPath string) []string {
	var subs []string

	if dirExists(indexPath) {
		subs = append(subs, "Index Spot")
	}

	if dirExists(optsPath) {
		callDir := filepath.Join(optsPath, "CALL")
		putDir := filepath.Join(optsPath, "PUT")

		if dirExists(callDir) {
			entries, _ := os.ReadDir(callDir)
			for _, e := range entries {
				if e.IsDir() {
					subs = append(subs, "CALL/"+e.Name())
				}
			}
		}

		if dirExists(putDir) {
			entries, _ := os.ReadDir(putDir)
			for _, e := range entries {
				if e.IsDir() {
					subs = append(subs, "PUT/"+e.Name())
				}
			}
		}
	}

	if len(subs) == 0 {
		subs = append(subs, "Index Spot")
	}

	return subs
}

// readParquetCandles reads all .parquet (NDJSON) files under dirPath and sorts by time
func readParquetCandles(dirPath string) ([]ChartCandle, error) {
	var files []string
	_ = filepath.Walk(dirPath, func(path string, info os.FileInfo, err error) error {
		if err == nil && !info.IsDir() && strings.HasSuffix(path, ".parquet") {
			files = append(files, path)
		}
		return nil
	})

	if len(files) == 0 {
		return nil, fmt.Errorf("no parquet data files found in %s", dirPath)
	}

	sort.Strings(files)

	candleMap := make(map[int64]ChartCandle)

	for _, file := range files {
		f, err := os.Open(file)
		if err != nil {
			continue
		}

		scanner := bufio.NewScanner(f)
		for scanner.Scan() {
			line := strings.TrimSpace(scanner.Text())
			if line == "" {
				continue
			}

			var raw map[string]interface{}
			if err := json.Unmarshal([]byte(line), &raw); err != nil {
				continue
			}

			ts := parseRawInt64(raw["timestamp"])
			if ts == 0 {
				continue
			}

			candle := ChartCandle{
				Time:         ts,
				Open:         parseRawFloat(raw["open"]),
				High:         parseRawFloat(raw["high"]),
				Low:          parseRawFloat(raw["low"]),
				Close:        parseRawFloat(raw["close"]),
				Volume:       int(parseRawFloat(raw["volume"])),
				OpenInterest: int(parseRawFloat(raw["open_interest"])),
				IV:           parseRawFloat(raw["iv"]),
				Spot:         parseRawFloat(raw["spot"]),
				Strike:       parseRawFloat(raw["strike"]),
				DateTime:     parseRawString(raw["datetime"]),
			}

			candleMap[ts] = candle
		}
		f.Close()
	}

	// Sort chronologically
	candles := make([]ChartCandle, 0, len(candleMap))
	for _, c := range candleMap {
		candles = append(candles, c)
	}

	sort.Slice(candles, func(i, j int) bool {
		return candles[i].Time < candles[j].Time
	})

	return candles, nil
}

func parseRawFloat(val interface{}) float64 {
	if val == nil {
		return 0.0
	}
	switch v := val.(type) {
	case float64:
		return v
	case float32:
		return float64(v)
	case int:
		return float64(v)
	case int64:
		return float64(v)
	}
	return 0.0
}

func parseRawInt64(val interface{}) int64 {
	if val == nil {
		return 0
	}
	switch v := val.(type) {
	case float64:
		return int64(v)
	case int64:
		return v
	case int:
		return int64(v)
	}
	return 0
}

func parseRawString(val interface{}) string {
	if val == nil {
		return ""
	}
	if s, ok := val.(string); ok {
		return s
	}
	return ""
}

// ServeUDFConfig handles GET /api/udf/config
func ServeUDFConfig(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Access-Control-Allow-Origin", "*")
	w.Header().Set("Content-Type", "application/json")

	cfg := map[string]interface{}{
		"supported_resolutions":   []string{"1", "5", "15", "60", "D"},
		"supports_group_request": false,
		"supports_marks":         false,
		"supports_search":        true,
		"supports_timescale_marks": false,
	}
	json.NewEncoder(w).Encode(cfg)
}

// ServeUDFSymbols handles GET /api/udf/symbols?symbol=Index Spot
func ServeUDFSymbols(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Access-Control-Allow-Origin", "*")
	w.Header().Set("Content-Type", "application/json")

	symbol := r.URL.Query().Get("symbol")
	if symbol == "" {
		symbol = "Index Spot"
	}

	sym := map[string]interface{}{
		"name":                  symbol,
		"ticker":                symbol,
		"description":           symbol,
		"type":                  "index",
		"session":               "24x7",
		"exchange":              "MARMOT",
		"listed_exchange":       "MARMOT",
		"timezone":              "Asia/Kolkata",
		"minmov":                1,
		"pricescale":            100,
		"has_intraday":          true,
		"supported_resolutions": []string{"1", "5", "15", "60", "D"},
		"volume_precision":      2,
		"data_status":           "streaming",
	}
	json.NewEncoder(w).Encode(sym)
}

// ServeUDFHistory handles GET /api/udf/history?symbol=CALL/ATM&task_id=1&from=...&to=...
func ServeUDFHistory(dbService *DBService, w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Access-Control-Allow-Origin", "*")
	w.Header().Set("Content-Type", "application/json")

	taskID := r.URL.Query().Get("task_id")
	if taskID == "" {
		http.Error(w, `{"s":"error","errmsg":"task_id required"}`, http.StatusBadRequest)
		return
	}

	symbol := r.URL.Query().Get("symbol")
	sub := ""
	if symbol != "" && symbol != "Index Spot" {
		sub = symbol
	}

	// Fetch candles using ServeChartData logic
	ctx := context.Background()
	query := fmt.Sprintf(`SELECT index_name, parquet_file_path, created_by_id FROM %s WHERE id = $1`, dbService.TableName)
	var indexName, parquetPath string
	var createdByID *int
	err := dbService.Pool.QueryRow(ctx, query, taskID).Scan(&indexName, &parquetPath, &createdByID)
	if err != nil {
		http.Error(w, `{"s":"no_data"}`, http.StatusOK)
		return
	}

	userID := "1"
	if createdByID != nil {
		userID = fmt.Sprintf("%d", *createdByID)
	}

	idxLower := strings.ToLower(indexName)
	indexPath := fmt.Sprintf("/app/data/users/%s/%s_index", userID, idxLower)
	optsPath := fmt.Sprintf("/app/data/users/%s/%s_options", userID, idxLower)

	if parquetPath != "" && dirExists(parquetPath) {
		if strings.HasSuffix(parquetPath, "_index") {
			indexPath = parquetPath
		} else if strings.HasSuffix(parquetPath, "_options") {
			optsPath = parquetPath
		} else {
			taskIdxDir := filepath.Join(parquetPath, fmt.Sprintf("%s_index", idxLower))
			taskOptDir := filepath.Join(parquetPath, fmt.Sprintf("%s_options", idxLower))
			if dirExists(taskIdxDir) {
				indexPath = taskIdxDir
			}
			if dirExists(taskOptDir) {
				optsPath = taskOptDir
			}
		}
	}

	targetDir := indexPath
	if sub != "" {
		targetDir = filepath.Join(optsPath, sub)
	}

	candles, err := readParquetCandles(targetDir)
	if err != nil || len(candles) == 0 {
		http.Error(w, `{"s":"no_data"}`, http.StatusOK)
		return
	}

	t := make([]int64, len(candles))
	o := make([]float64, len(candles))
	h := make([]float64, len(candles))
	l := make([]float64, len(candles))
	c := make([]float64, len(candles))
	v := make([]int, len(candles))

	for i, candle := range candles {
		t[i] = candle.Time
		o[i] = candle.Open
		h[i] = candle.High
		l[i] = candle.Low
		c[i] = candle.Close
		v[i] = candle.Volume
	}

	resp := map[string]interface{}{
		"s": "ok",
		"t": t,
		"o": o,
		"h": h,
		"l": l,
		"c": c,
		"v": v,
	}
	json.NewEncoder(w).Encode(resp)
}
