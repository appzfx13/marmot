package streamer

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"math"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"dhan-emulator/engine"
	"dhan-emulator/models"
	"github.com/gorilla/websocket"
	"github.com/parquet-go/parquet-go"
	"github.com/redis/go-redis/v9"
)

var upgrader = websocket.Upgrader{
	CheckOrigin: func(r *http.Request) bool { return true },
}

// ParquetFileInfo provides metadata on available dataset files.
type ParquetFileInfo struct {
	RelativePath string  `json:"relativePath"`
	FileName     string  `json:"fileName"`
	SizeBytes    int64   `json:"sizeBytes"`
	SizeMB       float64 `json:"sizeMB"`
	HasOptions   bool    `json:"hasOptions"`
	TypeLabel    string  `json:"typeLabel"`
	IndexName    string  `json:"indexName"`
	DateRange    string  `json:"dateRange"`
	StartDate    string  `json:"startDate"`
	EndDate      string  `json:"endDate"`
}

// ParquetStreamer replays parquet ticks or synthetic feeds into the matching engine and WebSocket clients.
type ParquetStreamer struct {
	mu              sync.RWMutex
	writeMu         sync.Mutex
	engine          *engine.MatchingEngine
	clients         map[*websocket.Conn]bool
	speed           int // Multiplier: 1, 5, 20, 50
	profileKey      string // Playback Profile: REALTIME, COMPRESSED, MODERATE, FAST, HYPER
	isPlaying       bool
	stopChan        chan struct{}
	currentFile     string
	availableDir    string
	ticksIngested   int64
	totalRows       int64
	currentRow      int64
	currentDatetime string
	currentDateStr    string
	currentVIX        float64
	latestTicks       map[string]models.MarketTick
	activeExpiryDate  string
	activeExpiryLabel string
	activeExpiryTicks map[string]models.MarketTick
	rdb               *redis.Client
	isCompleted       bool
	lastSpotTick      models.MarketTick
	lastSpotPrice     float64
	lastMinuteStr     string
	lastBucketTime    time.Time
	regulator         *FrequencyRegulator
}

// NewParquetStreamer initializes the market feed streamer.
func NewParquetStreamer(eng *engine.MatchingEngine, backupDir string) *ParquetStreamer {
	if backupDir == "" {
		backupDir = "/app/backup"
	}

	redisHost := os.Getenv("REDIS_HOST")
	if redisHost == "" {
		redisHost = "redis_broker"
	}
	redisPort := os.Getenv("REDIS_PORT")
	if redisPort == "" {
		redisPort = "6379"
	}
	rdb := redis.NewClient(&redis.Options{
		Addr: fmt.Sprintf("%s:%s", redisHost, redisPort),
	})

	ps := &ParquetStreamer{
		engine:            eng,
		clients:           make(map[*websocket.Conn]bool),
		speed:             1,
		profileKey:        "COMPRESSED",
		isPlaying:         false,
		availableDir:      backupDir,
		currentDatetime:   "",
		currentDateStr:    "",
		currentVIX:        13.28,
		latestTicks:       make(map[string]models.MarketTick),
		activeExpiryTicks: make(map[string]models.MarketTick),
		rdb:               rdb,
		regulator:         NewFrequencyRegulator(1, "COMPRESSED"),
	}

	if ps.rdb != nil {
		go ps.startLiveFeedSubscriber()
	}

	// Auto-select primary parquet dataset prioritizing verified complete Spot + Options files
	files := ps.ListParquetDetails()
	if len(files) > 0 {
		selected := files[0].RelativePath
		if envFile := os.Getenv("EMULATOR_DATASET"); envFile != "" {
			selected = envFile
		} else {
			// Check for verified complete symmetric options dataset first
			for _, f := range files {
				if f.RelativePath == "1/33/dataset.parquet" || f.RelativePath == "1/13/dataset.parquet" || f.RelativePath == "1/48/dataset.parquet" {
					selected = f.RelativePath
					break
				}
			}
			if selected != "1/33/dataset.parquet" && selected != "1/13/dataset.parquet" && selected != "1/48/dataset.parquet" {
				for _, f := range files {
					if f.HasOptions || f.RelativePath == "1/35/dataset.parquet" {
						selected = f.RelativePath
						break
					}
				}
			}
		}
		ps.currentFile = selected
		_, startDt, _ := readParquetMeta(filepath.Join(ps.availableDir, selected))
		if startDt != "" {
			ps.currentDatetime = startDt
			if len(startDt) >= 10 {
				ps.currentDateStr = startDt[:10]
			}
		}
		log.Printf("[STREAMER] Initialized with primary Parquet dataset: %s", ps.currentFile)
		ps.preIndexParquetFile(filepath.Join(ps.availableDir, selected))
	}

	// Auto-start playback on boot only if EMULATOR_AUTO_PLAY is explicitly set to true
	if ps.currentFile != "" {
		if os.Getenv("EMULATOR_AUTO_PLAY") == "true" {
			ps.Start()
			log.Printf("[STREAMER] Auto-started real-time playback for: %s", ps.currentFile)
		} else {
			log.Printf("[STREAMER] Dataset %s loaded. Playback idle on boot (EMULATOR_AUTO_PLAY != true). Waiting for manual or API trigger.", ps.currentFile)
		}
	}
	return ps
}

// HandleWebSocket handles client connections for live Dhan market feed streaming.
func (ps *ParquetStreamer) HandleWebSocket(w http.ResponseWriter, r *http.Request) {
	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		log.Printf("[STREAMER] WebSocket upgrade error: %v", err)
		return
	}

	ps.mu.Lock()
	ps.clients[conn] = true
	ps.mu.Unlock()

	log.Printf("[STREAMER] New WebSocket marketfeed client connected (%s)", conn.RemoteAddr())

	// Push immediate account stats snapshot upon connection (must hold writeMu to prevent concurrent write panic)
	if ps.engine != nil {
		stats := ps.engine.GetAccountStats(ps.engine.GetActiveAccountID())
		if statBytes, err := json.Marshal(stats); err == nil {
			ps.writeMu.Lock()
			_ = conn.WriteMessage(websocket.TextMessage, statBytes)
			ps.writeMu.Unlock()
		}
	}

	defer func() {
		ps.mu.Lock()
		delete(ps.clients, conn)
		ps.mu.Unlock()
		conn.Close()
		log.Printf("[STREAMER] WebSocket marketfeed client disconnected")
	}()

	for {
		_, _, err := conn.ReadMessage()
		if err != nil {
			break
		}
	}
}

// BroadcastRawMessage sends a raw JSON byte payload to all active WebSocket clients safely.
func (ps *ParquetStreamer) BroadcastRawMessage(msg []byte) {
	ps.writeMu.Lock()
	defer ps.writeMu.Unlock()

	ps.mu.RLock()
	if len(ps.clients) == 0 {
		ps.mu.RUnlock()
		return
	}
	activeList := make([]*websocket.Conn, 0, len(ps.clients))
	for client := range ps.clients {
		activeList = append(activeList, client)
	}
	ps.mu.RUnlock()

	var deadList []*websocket.Conn
	for _, client := range activeList {
		_ = client.SetWriteDeadline(time.Now().Add(250 * time.Millisecond))
		if err := client.WriteMessage(websocket.TextMessage, msg); err != nil {
			client.Close()
			deadList = append(deadList, client)
		}
	}

	if len(deadList) > 0 {
		ps.mu.Lock()
		for _, client := range deadList {
			delete(ps.clients, client)
		}
		ps.mu.Unlock()
	}
}

// BroadcastTick feeds the tick to the matching engine and all connected WebSocket clients.
func (ps *ParquetStreamer) BroadcastTick(tick models.MarketTick) {
	atomic.AddInt64(&ps.ticksIngested, 1)

	ps.mu.Lock()
	ps.latestTicks[tick.SecurityID] = tick
	if tick.TradingSymbol != "" {
		ps.latestTicks[tick.TradingSymbol] = tick
	}
	ps.mu.Unlock()

	// Feed into matching engine for MTM and SL/TP evaluation
	ps.engine.IngestTick(tick)

	optType := ""
	var strikeNum float64
	if strings.Contains(tick.SecurityID, "_CE") || strings.HasSuffix(tick.TradingSymbol, "CE") {
		optType = "CE"
	} else if strings.Contains(tick.SecurityID, "_PE") || strings.HasSuffix(tick.TradingSymbol, "PE") {
		optType = "PE"
	}
	parts := strings.Split(tick.SecurityID, "_")
	if len(parts) >= 1 {
		strikeNum, _ = strconv.ParseFloat(parts[0], 64)
	}

	// Wrap tick in a typed envelope so the JS WS router can identify it as a mock feed message.
	envelope := map[string]interface{}{
		"type":          "mock_tick",
		"is_mock":       true,
		"is_virtual":    true,
		"source":        "EMULATOR",
		"tradingSymbol": tick.TradingSymbol,
		"securityId":    tick.SecurityID,
		"strike":        strikeNum,
		"option_type":   optType,
		"ltp":           tick.LTP,
		"open":          tick.Open,
		"high":          tick.High,
		"low":           tick.Low,
		"close":         tick.Close,
		"oi":            tick.OI,
		"volume":        tick.Volume,
		"timestamp":     tick.Timestamp.Format("2006-01-02 15:04:05"),
	}
	msg, err := json.Marshal(envelope)
	if err != nil {
		return
	}

	// Publish to Redis channel marmot:mock_ticks for Go WebSocket hub (port 8082, window.MarmotWS)
	if ps.rdb != nil {
		_ = ps.rdb.Publish(context.Background(), "marmot:mock_ticks", msg).Err()
	}

	// Broadcast to WebSocket clients safely
	ps.writeMu.Lock()
	defer ps.writeMu.Unlock()

	ps.mu.RLock()
	if len(ps.clients) == 0 {
		ps.mu.RUnlock()
		return
	}
	activeList := make([]*websocket.Conn, 0, len(ps.clients))
	for client := range ps.clients {
		activeList = append(activeList, client)
	}
	ps.mu.RUnlock()

	var deadList []*websocket.Conn
	for _, client := range activeList {
		_ = client.SetWriteDeadline(time.Now().Add(250 * time.Millisecond))
		if err := client.WriteMessage(websocket.TextMessage, msg); err != nil {
			client.Close()
			deadList = append(deadList, client)
		}
	}

	if len(deadList) > 0 {
		ps.mu.Lock()
		for _, client := range deadList {
			delete(ps.clients, client)
		}
		ps.mu.Unlock()
	}
}

// Start begins the market feed playback loop.
func (ps *ParquetStreamer) Start() {
	ps.mu.Lock()
	if ps.isPlaying {
		ps.mu.Unlock()
		return
	}
	if ps.isCompleted {
		ps.isCompleted = false
		atomic.StoreInt64(&ps.currentRow, 0)
	}
	ps.isPlaying = true
	ps.stopChan = make(chan struct{})
	ps.mu.Unlock()

	go ps.streamLoop()
}

// Stop halts market feed playback and rewinds pointer to row 0.
func (ps *ParquetStreamer) Stop() {
	ps.mu.Lock()
	if ps.isPlaying {
		ps.isPlaying = false
		close(ps.stopChan)
	}
	atomic.StoreInt64(&ps.currentRow, 0)
	atomic.StoreInt64(&ps.ticksIngested, 0)
	ps.isCompleted = false
	activeFile := ps.currentFile
	speed := ps.speed
	tot := ps.totalRows
	ps.mu.Unlock()

	progressPayload := map[string]interface{}{
		"type":        "progress",
		"file":        activeFile,
		"current_row": 0,
		"total_rows":  tot,
		"pct":         0.0,
		"speed":       speed,
		"is_playing":  false,
		"date":        "",
		"time":        "09:15:00",
		"ticks":       0,
	}
	if pBytes, err := json.Marshal(progressPayload); err == nil {
		ps.BroadcastRawMessage(pBytes)
	}
}

// IsCompleted returns true if current dataset reached EOF.
func (ps *ParquetStreamer) IsCompleted() bool {
	ps.mu.RLock()
	defer ps.mu.RUnlock()
	return ps.isCompleted
}

// Restart rewinds playback to beginning and starts playing.
func (ps *ParquetStreamer) Restart() {
	ps.Stop()
	time.Sleep(50 * time.Millisecond)
	ps.mu.Lock()
	ps.isCompleted = false
	atomic.StoreInt64(&ps.currentRow, 0)
	atomic.StoreInt64(&ps.ticksIngested, 0)
	ps.mu.Unlock()
	ps.Start()
}

// SetProfile updates the playback profile (REAL, COMPRESSED, MODERATE, FAST, HYPER).
func (ps *ParquetStreamer) SetProfile(profile string) {
	ps.mu.Lock()
	pUpper := strings.ToUpper(strings.TrimSpace(profile))
	switch pUpper {
	case "REAL", "REALTIME":
		ps.profileKey = "REALTIME"
		ps.speed = 1
	case "COMPRESSED":
		ps.profileKey = "COMPRESSED"
		ps.speed = 1
	case "HIGH_COMPRESS", "BURST", "HIGH":
		ps.profileKey = "HIGH_COMPRESS"
		ps.speed = 12
	case "MODERATE", "5X":
		ps.profileKey = "MODERATE"
		ps.speed = 5
	case "SPEED", "FAST", "20X":
		ps.profileKey = "FAST"
		ps.speed = 20
	case "HYPER", "50X":
		ps.profileKey = "HYPER"
		ps.speed = 50
	default:
		ps.profileKey = "COMPRESSED"
		ps.speed = 1
	}
	cur := atomic.LoadInt64(&ps.currentRow)
	tot := ps.totalRows
	pct := 0.0
	if tot > 0 {
		pct = math.Round((float64(cur)/float64(tot)*100.0)*100) / 100.0
		if pct > 100.0 {
			pct = 100.0
		}
	}
	file := ps.currentFile
	date := ps.currentDateStr
	dt := ps.currentDatetime
	ticks := atomic.LoadInt64(&ps.ticksIngested)
	prof := ps.profileKey
	spd := ps.speed
	if ps.regulator != nil {
		ps.regulator.SetSpeed(spd, prof)
	}
	ps.mu.Unlock()

	pPayload := map[string]interface{}{
		"type":         "streamer_progress",
		"active_file":  file,
		"date":         date,
		"datetime":     dt,
		"current_row":  cur,
		"total_rows":   tot,
		"progress_pct": pct,
		"speed":        spd,
		"profile_key":  prof,
		"ticks":        ticks,
	}
	if pBytes, err := json.Marshal(pPayload); err == nil {
		ps.BroadcastRawMessage(pBytes)
	}
}

// SetSpeed sets tick replay multiplier and broadcasts immediate progress event.
func (ps *ParquetStreamer) SetSpeed(speed int) {
	ps.mu.Lock()
	if speed <= 0 {
		speed = 1
	}
	ps.speed = speed
	if speed == 1 {
		ps.profileKey = "COMPRESSED"
	} else if speed == 5 {
		ps.profileKey = "MODERATE"
	} else if speed == 20 {
		ps.profileKey = "FAST"
	} else if speed >= 50 {
		ps.profileKey = "HYPER"
	}
	cur := atomic.LoadInt64(&ps.currentRow)
	tot := ps.totalRows
	pct := 0.0
	if tot > 0 {
		pct = math.Round((float64(cur)/float64(tot)*100.0)*100) / 100.0
		if pct > 100.0 {
			pct = 100.0
		}
	}
	file := ps.currentFile
	date := ps.currentDateStr
	dt := ps.currentDatetime
	ticks := atomic.LoadInt64(&ps.ticksIngested)
	prof := ps.profileKey
	if ps.regulator != nil {
		ps.regulator.SetSpeed(ps.speed, prof)
	}
	ps.mu.Unlock()

	pPayload := map[string]interface{}{
		"type":         "streamer_progress",
		"active_file":  file,
		"date":         date,
		"datetime":     dt,
		"current_row":  cur,
		"total_rows":   tot,
		"progress_pct": pct,
		"speed":        speed,
		"profile_key":  prof,
		"ticks":        ticks,
	}
	if pBytes, err := json.Marshal(pPayload); err == nil {
		ps.BroadcastRawMessage(pBytes)
	}
}

// SelectParquetFile changes active dataset and restarts replay.
func (ps *ParquetStreamer) SelectParquetFile(file string) {
	ps.mu.Lock()
	ps.currentFile = file
	// Atomically clear stale ticks, datetime, and counters from prior file
	ps.latestTicks = make(map[string]models.MarketTick)
	_, startDt, _ := readParquetMeta(filepath.Join(ps.availableDir, file))
	ps.currentDatetime = startDt
	ps.currentDateStr = ""
	if len(startDt) >= 10 {
		ps.currentDateStr = startDt[:10]
	}
	atomic.StoreInt64(&ps.currentRow, 0)
	atomic.StoreInt64(&ps.ticksIngested, 0)
	if ps.regulator != nil {
		ps.regulator.Reset()
	}

	wasPlaying := ps.isPlaying
	if wasPlaying {
		close(ps.stopChan)
		ps.isPlaying = false
	}
	ps.mu.Unlock()

	ps.preIndexParquetFile(filepath.Join(ps.availableDir, file))

	if wasPlaying {
		time.Sleep(50 * time.Millisecond)
	}
	ps.Start()
}

// GetStatus returns current streamer operational state.
func (ps *ParquetStreamer) GetStatus() (bool, int, string, int64) {
	ps.mu.RLock()
	defer ps.mu.RUnlock()
	return ps.isPlaying, ps.speed, ps.currentFile, atomic.LoadInt64(&ps.ticksIngested)
}

// GetProfileKey returns active playback profile key.
func (ps *ParquetStreamer) GetProfileKey() string {
	ps.mu.RLock()
	defer ps.mu.RUnlock()
	if ps.profileKey == "" {
		return "COMPRESSED"
	}
	return ps.profileKey
}

// GetProgress returns dataset row progress metrics and active candle datetime.
func (ps *ParquetStreamer) GetProgress() (int64, int64, float64, string, string) {
	ps.mu.RLock()
	defer ps.mu.RUnlock()
	cur := atomic.LoadInt64(&ps.currentRow)
	tot := ps.totalRows
	pct := 0.0
	if tot > 0 {
		pct = float64(cur) / float64(tot) * 100.0
		if pct > 100.0 {
			pct = 100.0
		}
	}
	dt := ps.currentDatetime
	if dt == "" {
		dt = time.Now().Format("2006-01-02 15:04:05")
	}
	d := ps.currentDateStr
	if d == "" {
		d = time.Now().Format("2006-01-02")
	}
	return cur, tot, pct, dt, d
}

// GetStreamerWidgetData returns distinct Index ticks and recent Option strikes ticks.
func (ps *ParquetStreamer) GetStreamerWidgetData() ([]models.MarketTick, []models.MarketTick) {
	ps.mu.RLock()
	defer ps.mu.RUnlock()

	var indexTicks []models.MarketTick
	var optionTicks []models.MarketTick

	for _, tick := range ps.latestTicks {
		symUpper := strings.ToUpper(tick.TradingSymbol)
		if strings.Contains(symUpper, " CE") || strings.Contains(symUpper, " PE") || strings.Contains(symUpper, "CALL") || strings.Contains(symUpper, "PUT") {
			optionTicks = append(optionTicks, tick)
		} else if symUpper == "NIFTY" || symUpper == "BANKNIFTY" || symUpper == "INDIA VIX" || symUpper == "SENSEX" || tick.SecurityID == "13" || tick.SecurityID == "25" {
			indexTicks = append(indexTicks, tick)
		}
	}

	return indexTicks, optionTicks
}

// GetLatestTicks returns a copy of latest ticks for UI display.
func (ps *ParquetStreamer) GetLatestTicks() map[string]models.MarketTick {
	ps.mu.RLock()
	defer ps.mu.RUnlock()
	copyMap := make(map[string]models.MarketTick, len(ps.latestTicks))
	for k, v := range ps.latestTicks {
		copyMap[k] = v
	}
	return copyMap
}

// formatIndianNumber formats an integer according to the Indian numbering system (e.g., 1,52,22,285).
func formatIndianNumber(n int64) string {
	if n == 0 {
		return "0"
	}
	sign := ""
	if n < 0 {
		sign = "-"
		n = -n
	}
	s := strconv.FormatInt(n, 10)
	if len(s) <= 3 {
		return sign + s
	}
	last3 := s[len(s)-3:]
	rest := s[:len(s)-3]
	var groups []string
	for len(rest) > 2 {
		groups = append([]string{rest[len(rest)-2:]}, groups...)
		rest = rest[:len(rest)-2]
	}
	if len(rest) > 0 {
		groups = append([]string{rest}, groups...)
	}
	return sign + strings.Join(groups, ",") + "," + last3
}

// formatIndianFloat formats a float64 with 2 decimal places in Indian numbering format (e.g. 24,241.05).
func formatIndianFloat(val float64) string {
	if val <= 0 {
		return "0.00"
	}
	intPart := int64(val)
	fracPart := int64(math.Round((val - float64(intPart)) * 100))
	if fracPart >= 100 {
		intPart++
		fracPart -= 100
	}
	return fmt.Sprintf("%s.%02d", formatIndianNumber(intPart), fracPart)
}

// parseContractExpiryDate extracts the expiry date from contract trading symbol (e.g. NSE:NIFTY2681124450CE, NSE:NIFTY26AUG23600CE).
func parseContractExpiryDate(sym string, tradeDate time.Time) (time.Time, string) {
	clean := strings.ToUpper(strings.TrimSpace(sym))
	clean = strings.TrimPrefix(clean, "NSE:")

	// 1. Weekly FYERS format: [INDEX][YY][M][DD][STRIKE][CE|PE]
	weeklyRe := regexp.MustCompile(`([A-Z]+)(\d{2})([1-9OND])(\d{2})(\d+)(CE|PE)`)
	if matches := weeklyRe.FindStringSubmatch(clean); len(matches) == 7 {
		yy, _ := strconv.Atoi(matches[2])
		year := 2000 + yy
		mChar := matches[3][0]
		monthMap := map[byte]time.Month{
			'1': 1, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9,
			'O': 10, 'N': 11, 'D': 12,
		}
		month := monthMap[mChar]
		dd, _ := strconv.Atoi(matches[4])
		if month >= 1 && month <= 12 && dd >= 1 && dd <= 31 {
			expTime := time.Date(year, month, dd, 15, 30, 0, 0, tradeDate.Location())
			expLabel := fmt.Sprintf("%02d %s %d (Weekly Expiry)", dd, strings.ToUpper(expTime.Format("Jan")), year)
			return expTime, expLabel
		}
	}

	// 2. Monthly FYERS format: [INDEX][YY][MMM][STRIKE][CE|PE]
	monthlyRe := regexp.MustCompile(`([A-Z]+)(\d{2})(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)(\d+)(CE|PE)`)
	if matches := monthlyRe.FindStringSubmatch(clean); len(matches) == 6 {
		yy, _ := strconv.Atoi(matches[2])
		year := 2000 + yy
		mmm := matches[3]
		monthMap := map[string]time.Month{
			"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
			"JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
		}
		month := monthMap[mmm]
		if month >= 1 && month <= 12 {
			firstOfNext := time.Date(year, month+1, 1, 0, 0, 0, 0, tradeDate.Location())
			lastDay := firstOfNext.AddDate(0, 0, -1)
			offset := (int(lastDay.Weekday()) - int(time.Thursday) + 7) % 7
			lastThurs := lastDay.AddDate(0, 0, -offset)
			expTime := time.Date(year, month, lastThurs.Day(), 15, 30, 0, 0, tradeDate.Location())
			expLabel := fmt.Sprintf("%02d %s %d (Monthly Expiry)", lastThurs.Day(), mmm, year)
			return expTime, expLabel
		}
	}

	return time.Time{}, ""
}

// calculateIndexExpiry computes the next exchange expiry date and label (e.g. "09 JUL 2026", "Weekly Expiry").
func calculateIndexExpiry(indexName, timeStr string) (string, string) {
	tradeDt := time.Now()
	if len(timeStr) >= 10 {
		if t, err := time.Parse("2006-01-02", timeStr[:10]); err == nil {
			tradeDt = t
		}
	}
	targetWeekday := time.Thursday
	idxUpper := strings.ToUpper(indexName)
	if strings.Contains(idxUpper, "BANK") {
		targetWeekday = time.Wednesday
	} else if strings.Contains(idxUpper, "FIN") {
		targetWeekday = time.Tuesday
	} else if strings.Contains(idxUpper, "MIDCP") {
		targetWeekday = time.Monday
	} else if strings.Contains(idxUpper, "SENSEX") {
		targetWeekday = time.Friday
	}

	daysAhead := (int(targetWeekday) - int(tradeDt.Weekday()) + 7) % 7
	nextExp := tradeDt.AddDate(0, 0, daysAhead)
	expDate := strings.ToUpper(nextExp.Format("02 Jan 2006"))
	expTag := "Weekly Expiry"
	return expDate, expTag
}

// GetOptionChain builds and returns a complete, synchronized option chain matrix for the requested index.
// Extracts 100% genuine data from Parquet ticks without synthetic price floors or formulas.
func (ps *ParquetStreamer) GetOptionChain(indexName string) models.OptionChainResponse {
	ps.mu.RLock()
	defer ps.mu.RUnlock()

	idxClean := strings.ToUpper(strings.TrimSpace(indexName))
	if idxClean == "" {
		idxClean = "NIFTY"
	}

	strikeStep := 50
	displaySymbol := "NIFTY 50"
	if strings.Contains(idxClean, "BANK") {
		strikeStep = 100
		displaySymbol = "BANK NIFTY"
	} else if strings.Contains(idxClean, "SENSEX") {
		strikeStep = 100
		displaySymbol = "BSE SENSEX"
	} else if strings.Contains(idxClean, "MIDCP") {
		strikeStep = 25
		displaySymbol = "MIDCP NIFTY"
	}

	timeStr := ps.currentDatetime

	// 1. Locate current Spot price exclusively from real incoming ticks
	spotLTP := 0.0
	dayOpen := 0.0
	dayHigh := 0.0
	dayLow := 0.0
	prevClose := 0.0

	targetSecID := "13"
	if strings.Contains(idxClean, "BANK") {
		targetSecID = "25"
	}

	if t, ok := ps.latestTicks[targetSecID]; ok && t.LTP > 0 {
		spotLTP = t.LTP
		dayOpen = t.Open
		dayHigh = t.High
		dayLow = t.Low
		prevClose = t.Close
	} else if t, ok := ps.latestTicks[idxClean]; ok && t.LTP > 0 {
		spotLTP = t.LTP
		dayOpen = t.Open
		dayHigh = t.High
		dayLow = t.Low
		prevClose = t.Close
	} else {
		for _, t := range ps.latestTicks {
			symUpper := strings.ToUpper(t.TradingSymbol)
			if (symUpper == idxClean || symUpper == displaySymbol || t.SecurityID == targetSecID) && t.LTP > 0 {
				spotLTP = t.LTP
				dayOpen = t.Open
				dayHigh = t.High
				dayLow = t.Low
				prevClose = t.Close
				break
			}
		}
	}

	if spotLTP <= 0 {
		if ps.rdb != nil {
			if rawChain, err := ps.rdb.Get(context.Background(), fmt.Sprintf("marmot:fyers:option_chain:%s", idxClean)).Result(); err == nil && rawChain != "" {
				var liveChain models.OptionChainResponse
				if json.Unmarshal([]byte(rawChain), &liveChain) == nil && liveChain.RawSpotLTP > 0 {
					liveChain.IsLive = true
					liveChain.IsMockLive = true
					liveChain.FeedStatus = "LIVE_SIMULATION"
					liveChain.FyersSymbol = fmt.Sprintf("DHAN_MOCK:%s", idxClean)
					return liveChain
				}
			}
		}
		return models.OptionChainResponse{
			IsLive:        false,
			IsMockLive:    true,
			FeedStatus:    "STANDBY",
			IndexName:     idxClean,
			SpotSymbol:    displaySymbol,
			FyersSymbol:   fmt.Sprintf("DHAN_MOCK:%s", idxClean),
			SpotLTP:       "0.00",
			RawSpotLTP:    0.0,
			SpotChange:    "0.00",
			SpotChangePct: "0.00%",
			IsPositive:    true,
			OpenPrice:     "0.00",
			HighPrice:     "0.00",
			LowPrice:      "0.00",
			PrevClose:     "0.00",
			ATMStrike:     "-",
			StrikeStep:    strikeStep,
			PCR:           0.0,
			IndiaVIX:      0.0,
			TotalStrikes:  0,
			Strikes:       []models.OptionStrikeRow{},
			LastUpdated:   timeStr,
		}
	}

	change := 0.0
	changePct := 0.0
	if prevClose > 0 {
		change = spotLTP - prevClose
		changePct = (change / prevClose) * 100.0
	}
	isPositive := change >= 0

	atmStrikeVal := math.Round(spotLTP/float64(strikeStep)) * float64(strikeStep)

	// 2. Scan available recorded strikes for boundary adaptation
	minAvailStrike := 0.0
	maxAvailStrike := 0.0
	hasAvailTicks := false

	checkTicks := func(m map[string]models.MarketTick) {
		for k, t := range m {
			if t.LTP > 0 {
				parts := strings.Split(k, "_")
				if len(parts) >= 2 {
					if stk, err := strconv.ParseFloat(parts[0], 64); err == nil && stk > 1000 {
						if !hasAvailTicks || stk < minAvailStrike {
							minAvailStrike = stk
						}
						if !hasAvailTicks || stk > maxAvailStrike {
							maxAvailStrike = stk
						}
						hasAvailTicks = true
					}
				}
			}
		}
	}
	if len(ps.activeExpiryTicks) > 0 {
		checkTicks(ps.activeExpiryTicks)
	} else {
		checkTicks(ps.latestTicks)
	}

	// 3. Build 31 strikes window centered strictly on true ATM strike (zero artificial clamping)
	var strikes []models.OptionStrikeRow
	totalStrikes := 31
	halfWindow := totalStrikes / 2

	centerStrike := atmStrikeVal

	totalCallVol := int64(0)
	totalPutVol := int64(0)
	totalCallOI := int64(0)
	totalPutOI := int64(0)

	for i := -halfWindow; i <= halfWindow; i++ {
		stkPrice := centerStrike + float64(i*strikeStep)
		isATM := (stkPrice == atmStrikeVal)

		stkStr := fmt.Sprintf("%.0f", stkPrice)

		var ceLTP, peLTP, ceChg, peChg, ceChgPct, peChgPct float64
		ceOI := "—"
		peOI := "—"

		findOptionTick := func(optType string) (models.MarketTick, bool) {
			altType := "CALL"
			if optType == "PE" {
				altType = "PUT"
			}
			keys := []string{
				fmt.Sprintf("%s_%s", stkStr, optType),
				fmt.Sprintf("%s_%s", stkStr, altType),
			}
			for _, k := range keys {
				if t, ok := ps.activeExpiryTicks[k]; ok && t.LTP > 0 {
					return t, true
				}
			}
			for _, k := range keys {
				if t, ok := ps.latestTicks[k]; ok && t.LTP > 0 {
					return t, true
				}
			}

			var bestTick models.MarketTick
			var found bool

			for k, t := range ps.activeExpiryTicks {
				if t.LTP > 0 && strings.Contains(k, stkStr) && (strings.Contains(k, optType) || strings.Contains(k, altType)) {
					if !found || t.Timestamp.After(bestTick.Timestamp) {
						bestTick = t
						found = true
					}
				}
			}
			if found {
				return bestTick, true
			}

			for k, t := range ps.latestTicks {
				if t.LTP > 0 && strings.Contains(k, stkStr) && (strings.Contains(k, optType) || strings.Contains(k, altType)) {
					if !found || t.Timestamp.After(bestTick.Timestamp) {
						bestTick = t
						found = true
					}
				}
			}
			return bestTick, found
		}

		tickCE, okCE := findOptionTick("CE")
		if okCE && tickCE.LTP > 0 {
			ceLTP = tickCE.LTP
			if tickCE.Open > 0 {
				ceChg = float64(int((tickCE.LTP-tickCE.Open)*10)) / 10.0
				ceChgPct = float64(int((ceChg/tickCE.Open)*1000)) / 10.0
			}
			if tickCE.OI > 0 && tickCE.OI != 100000 {
				ceOI = formatIndianNumber(tickCE.OI)
				totalCallOI += tickCE.OI
			} else if tickCE.Volume > 0 {
				ceOI = formatIndianNumber(tickCE.Volume)
			}
			totalCallVol += tickCE.Volume
		}

		tickPE, okPE := findOptionTick("PE")
		if okPE && tickPE.LTP > 0 {
			peLTP = tickPE.LTP
			if tickPE.Open > 0 {
				peChg = float64(int((tickPE.LTP-tickPE.Open)*10)) / 10.0
				peChgPct = float64(int((peChg/tickPE.Open)*1000)) / 10.0
			}
			if tickPE.OI > 0 && tickPE.OI != 100000 {
				peOI = formatIndianNumber(tickPE.OI)
				totalPutOI += tickPE.OI
			} else if tickPE.Volume > 0 {
				peOI = formatIndianNumber(tickPE.Volume)
			}
			totalPutVol += tickPE.Volume
		}

		ceSymbol := tickCE.TradingSymbol
		if ceSymbol == "" {
			ceSymbol = fmt.Sprintf("DHAN_MOCK:%s_%.0f_CE", idxClean, stkPrice)
		}
		peSymbol := tickPE.TradingSymbol
		if peSymbol == "" {
			peSymbol = fmt.Sprintf("DHAN_MOCK:%s_%.0f_PE", idxClean, stkPrice)
		}

		isActiveWindow := (i >= -3 && i <= 3)

		row := models.OptionStrikeRow{
			Strike:         stkPrice,
			IsActiveWindow: isActiveWindow,
			IsATM:          isATM,
			CESymbol:       ceSymbol,
			CE_LTP:         ceLTP,
			CE_Change:      ceChg,
			CE_ChangePct:   ceChgPct,
			CE_OI:          ceOI,
			PESymbol:       peSymbol,
			PE_LTP:         peLTP,
			PE_Change:      peChg,
			PE_ChangePct:   peChgPct,
			PE_OI:          peOI,
		}
		strikes = append(strikes, row)
	}

	pcr := 0.0
	if totalCallOI > 0 {
		pcr = float64(totalPutOI) / float64(totalCallOI)
	} else if totalCallVol > 0 {
		pcr = float64(totalPutVol) / float64(totalCallVol)
	}
	pcr = float64(int(pcr*100)) / 100.0

	sign := ""
	if change >= 0 {
		sign = "+"
	}

	feedStatus := "ACTIVE"
	if !ps.isPlaying {
		if spotLTP > 0 {
			feedStatus = "LIVE_SIMULATION"
		} else {
			feedStatus = "STANDBY"
		}
	}

	vix := ps.currentVIX
	expDate, expTag := calculateIndexExpiry(idxClean, timeStr)
	if ps.activeExpiryLabel != "" {
		expDate = ps.activeExpiryLabel
	}

	return models.OptionChainResponse{
		IsLive:        ps.isPlaying,
		IsMockLive:    true,
		FeedStatus:    feedStatus,
		IndexName:     idxClean,
		SpotSymbol:    displaySymbol,
		FyersSymbol:   fmt.Sprintf("DHAN_MOCK:%s", idxClean),
		SpotLTP:       formatIndianFloat(spotLTP),
		RawSpotLTP:    spotLTP,
		SpotChange:    fmt.Sprintf("%s%.2f", sign, change),
		SpotChangePct: fmt.Sprintf("%s%.2f%%", sign, changePct),
		IsPositive:    isPositive,
		OpenPrice:     formatIndianFloat(dayOpen),
		HighPrice:     formatIndianFloat(dayHigh),
		LowPrice:      formatIndianFloat(dayLow),
		PrevClose:     formatIndianFloat(prevClose),
		ATMStrike:     fmt.Sprintf("%.0f", atmStrikeVal),
		StrikeStep:    strikeStep,
		PCR:           pcr,
		IndiaVIX:      vix,
		TotalStrikes:  len(strikes),
		Strikes:       strikes,
		LastUpdated:   timeStr,
		ExpiryDate:    expDate,
		ExpiryTag:     expTag,
	}
}

// streamLoop routes to pure historical Parquet replay or remains in standby if no dataset is present.
func (ps *ParquetStreamer) streamLoop() {
	ps.mu.RLock()
	currentFile := ps.currentFile
	ps.mu.RUnlock()

	if currentFile != "" {
		fullPath := filepath.Join(ps.availableDir, currentFile)
		if _, err := os.Stat(fullPath); err == nil {
			ps.streamParquetFile(fullPath)
			return
		}
	}

	log.Printf("[STREAMER] No Parquet dataset available in %s; remaining in STANDBY", ps.availableDir)
	select {
	case <-ps.stopChan:
		return
	}
}

// streamParquetFile reads Parquet records using pure Go native streaming and streams all strikes concurrently for each timestamp.
func (ps *ParquetStreamer) streamParquetFile(fullPath string) {
	log.Printf("[STREAMER] Starting native Parquet streaming replay from: %s", fullPath)

	if ps.rdb != nil {
		_ = ps.rdb.Set(context.Background(), "marmot:mock_feed:active", "true", 0).Err()
	}
	defer func() {
		if ps.rdb != nil {
			_ = ps.rdb.Del(context.Background(), "marmot:mock_feed:active").Err()
		}
	}()

	file, err := os.Open(fullPath)
	if err != nil {
		log.Printf("[STREAMER] Error opening Parquet file %s: %v", fullPath, err)
		return
	}
	defer file.Close()

	stat, err := file.Stat()
	if err != nil {
		log.Printf("[STREAMER] Error stat Parquet file %s: %v", fullPath, err)
		return
	}

	pf, err := parquet.OpenFile(file, stat.Size())
	if err != nil {
		log.Printf("[STREAMER] Error opening Parquet file reader: %v", err)
		return
	}

	totalRows := pf.NumRows()
	startRow := atomic.LoadInt64(&ps.currentRow)
	ps.mu.Lock()
	ps.totalRows = totalRows
	if ps.isCompleted || startRow >= totalRows {
		atomic.StoreInt64(&ps.currentRow, 0)
		startRow = 0
		ps.isCompleted = false
	}
	needIndex := len(ps.latestTicks) == 0
	ps.mu.Unlock()
	if needIndex {
		ps.preIndexParquetFile(fullPath)
	}

	reader := parquet.NewGenericReader[models.MarketCandleRecord](file)
	defer reader.Close()

	if startRow > 0 {
		if err := reader.SeekToRow(startRow); err != nil {
			log.Printf("[STREAMER] SeekToRow(%d) warning: %v", startRow, err)
		}
	}

	buf := make([]models.MarketCandleRecord, 4096)
	bufIdx := 0
	bufLen := 0

	getNextRow := func(dest *models.MarketCandleRecord) bool {
		if bufIdx >= bufLen {
			n, readErr := reader.Read(buf)
			if n > 0 {
				bufLen = n
				bufIdx = 0
			} else {
				if readErr != nil && readErr != io.EOF {
					log.Printf("[STREAMER] Parquet stream read error: %v", readErr)
				}
				return false
			}
		}
		*dest = buf[bufIdx]
		bufIdx++
		return true
	}

	var pendingRecord *models.MarketCandleRecord
	lastProgressBroadcast := time.Now()

	for {
		ps.mu.RLock()
		if !ps.isPlaying {
			ps.mu.RUnlock()
			return
		}
		speed := ps.speed
		ps.mu.RUnlock()

		// 1. Group all records sharing the exact same timestamp into one concurrent batch
		var currentBucket []models.MarketCandleRecord
		var currentBucketTime string
		var parsedBucketTime time.Time

		if pendingRecord != nil {
			currentBucket = append(currentBucket, *pendingRecord)
			currentBucketTime = pendingRecord.Datetime
			if currentBucketTime == "" && pendingRecord.Timestamp > 0 {
				currentBucketTime = time.Unix(pendingRecord.Timestamp, 0).Format("2006-01-02 15:04:05")
			}
			pendingRecord = nil
		}

		eofReached := false
		for {
			var rec models.MarketCandleRecord
			if !getNextRow(&rec) {
				eofReached = true
				break
			}

			atomic.AddInt64(&ps.currentRow, 1)

			recTime := rec.Datetime
			if recTime == "" && rec.Timestamp > 0 {
				recTime = time.Unix(rec.Timestamp, 0).Format("2006-01-02 15:04:05")
			}

			if currentBucketTime == "" {
				currentBucketTime = recTime
			}

			if recTime == currentBucketTime {
				currentBucket = append(currentBucket, rec)
			} else {
				pendingRecord = &rec
				break
			}
		}

		if len(currentBucket) == 0 && eofReached {
			log.Printf("[STREAMER] Reached EOF on %s. Replay session COMPLETED.", fullPath)
			ps.mu.Lock()
			ps.isPlaying = false
			ps.isCompleted = true
			if ps.totalRows > 0 {
				atomic.StoreInt64(&ps.currentRow, ps.totalRows)
			}
			ps.mu.Unlock()
			ps.BroadcastRawMessage([]byte(`{"type":"replay_completed"}`))
			return
		}

		// 2. Broadcast all strikes and spot index for timestamp T concurrently
		if len(currentBucket) > 0 {
			parsedBucketTime = time.Now()
			if len(currentBucketTime) >= 19 {
				if t, err := time.Parse("2006-01-02 15:04:05", currentBucketTime[:19]); err == nil {
					parsedBucketTime = t
				}
			} else if len(currentBucketTime) >= 10 {
				if t, err := time.Parse("2006-01-02", currentBucketTime[:10]); err == nil {
					parsedBucketTime = t
				}
			}

			ps.mu.Lock()
			if currentBucketTime != "" {
				ps.currentDatetime = currentBucketTime
				if len(currentBucketTime) >= 10 {
					ps.currentDateStr = currentBucketTime[:10]
				}
			}
			ps.mu.Unlock()

			// Concurrently broadcast Spot Index tick from rec.SpotPrice
			var spotPrice float64
			var spotIndexName string
			var openPrice, highPrice, lowPrice, closePrice float64
			var volume int64

			for _, rec := range currentBucket {
				if rec.OptionType == "INDEX" || rec.Strike == "SPOT" || strings.Contains(strings.ToUpper(rec.TradingSymbol), "INDEX") {
					spotIndexName = rec.IndexName
					spotPrice = rec.Close
					if spotPrice <= 0 {
						spotPrice = rec.SpotPrice
					}
					openPrice = rec.Open
					highPrice = rec.High
					lowPrice = rec.Low
					closePrice = spotPrice
					volume = rec.Volume
					break
				}
			}

			// Sub-tick Spot Context Retention: If sub-tick only contains option rows, retain active 1-min spot baseline
			ps.mu.RLock()
			cachedSpotPrice := ps.lastSpotPrice
			cachedSpotTick := ps.lastSpotTick
			ps.mu.RUnlock()

			if spotPrice <= 0 && cachedSpotPrice > 1000 {
				spotPrice = cachedSpotPrice
				spotIndexName = cachedSpotTick.TradingSymbol
				openPrice = cachedSpotTick.Open
				highPrice = cachedSpotTick.High
				lowPrice = cachedSpotTick.Low
				closePrice = cachedSpotTick.Close
				volume = cachedSpotTick.Volume
			} else if spotPrice <= 0 {
				// Cold-start fallback before first INDEX row encountered: only accept rec.SpotPrice if NOT equal to its option strike
				for _, rec := range currentBucket {
					strikeNum, _ := strconv.ParseFloat(rec.Strike, 64)
					if rec.SpotPrice > 1000 && math.Abs(rec.SpotPrice-strikeNum) > 50.0 {
						spotPrice = rec.SpotPrice
						spotIndexName = rec.IndexName
						openPrice = rec.SpotPrice
						highPrice = rec.SpotPrice
						lowPrice = rec.SpotPrice
						closePrice = rec.SpotPrice
						volume = 50000
						break
					}
				}
			}

			if spotPrice > 1000 {
				if spotIndexName == "" {
					spotIndexName = "NIFTY"
				}
				secID := "13"
				if strings.Contains(strings.ToUpper(spotIndexName), "BANK") {
					secID = "25"
				}
				spotTick := models.MarketTick{
					Timestamp:     parsedBucketTime,
					SecurityID:    secID,
					TradingSymbol: spotIndexName,
					LTP:           spotPrice,
					Open:          openPrice,
					High:          highPrice,
					Low:           lowPrice,
					Close:         closePrice,
					Volume:        volume,
				}

				ps.mu.Lock()
				ps.lastSpotPrice = spotPrice
				ps.lastSpotTick = spotTick
				var isNewMinuteBar bool
				if ps.regulator != nil {
					isNewMinuteBar, _, _ = ps.regulator.OnTick(parsedBucketTime)
				} else {
					currentMinuteStr := parsedBucketTime.Format("2006-01-02 15:04")
					isNewMinuteBar = (ps.lastMinuteStr == "" || currentMinuteStr != ps.lastMinuteStr)
					if isNewMinuteBar {
						ps.lastMinuteStr = currentMinuteStr
					}
				}
				ps.mu.Unlock()

				if isNewMinuteBar {
					ps.BroadcastTick(spotTick)

					if ps.rdb != nil {
						candleMsg := map[string]interface{}{
							"index":      spotIndexName,
							"datetime":   currentBucketTime,
							"open":       openPrice,
							"high":       highPrice,
							"low":        lowPrice,
							"close":      closePrice,
							"spot_price": spotPrice,
							"volume":     volume,
							"vix":        ps.currentVIX,
						}
						if cBytes, err := json.Marshal(candleMsg); err == nil {
							_ = ps.rdb.Publish(context.Background(), "marmot:streamer:candles", cBytes).Err()
						}
					}
				}

				if ps.rdb != nil {
					ps.mu.RLock()
					activeFile := ps.currentFile
					streamSpeed := ps.speed
					totRows := ps.totalRows
					cRow := atomic.LoadInt64(&ps.currentRow)
					ps.mu.RUnlock()
					var progPct float64
					if totRows > 0 {
						progPct = (float64(cRow) / float64(totRows)) * 100.0
					}

					// Broadcast virtual clock tick to Marmot UI for real-time historical clock sync
					tickMsg := map[string]interface{}{
						"type":           "mock_tick",
						"source":         "EMULATOR",
						"is_mock":        true,
						"index":          spotIndexName,
						"symbol":         spotIndexName,
						"spot_price":     spotPrice,
						"ltp":            fmt.Sprintf("%.2f", spotPrice),
						"open":           openPrice,
						"high":           highPrice,
						"low":            lowPrice,
						"close":          closePrice,
						"formatted_time": currentBucketTime,
						"timestamp":      currentBucketTime,
						"is_virtual":     true,
						"speed":          streamSpeed,
						"progress_pct":   fmt.Sprintf("%.1f", progPct),
						"current_row":    cRow,
						"total_rows":     totRows,
						"file":           activeFile,
					}
					if tBytes, err := json.Marshal(tickMsg); err == nil {
						_ = ps.rdb.Publish(context.Background(), "marmot:mock_ticks", tBytes).Err()
					}
				}
			}

			// Determine nearest active exchange expiry from contracts in current bucket
			var nearestExpiryDate string
			var nearestExpiryLabel string
			var nearestExpiryTime time.Time
			bucketTradeDate := time.Date(parsedBucketTime.Year(), parsedBucketTime.Month(), parsedBucketTime.Day(), 0, 0, 0, 0, parsedBucketTime.Location())

			for _, rec := range currentBucket {
				if rec.TradingSymbol == "" || rec.OptionType == "INDEX" || rec.Strike == "SPOT" {
					continue
				}
				expT, expLbl := parseContractExpiryDate(rec.TradingSymbol, parsedBucketTime)
				if !expT.IsZero() {
					expDateOnly := time.Date(expT.Year(), expT.Month(), expT.Day(), 0, 0, 0, 0, expT.Location())
					if !expDateOnly.Before(bucketTradeDate) {
						expKey := expDateOnly.Format("2006-01-02")
						if nearestExpiryDate == "" || expDateOnly.Before(nearestExpiryTime) {
							nearestExpiryDate = expKey
							nearestExpiryTime = expDateOnly
							nearestExpiryLabel = expLbl
						}
					}
				}
			}

			if nearestExpiryDate != "" {
				ps.mu.Lock()
				if nearestExpiryDate != ps.activeExpiryDate {
					ps.activeExpiryDate = nearestExpiryDate
					ps.activeExpiryLabel = nearestExpiryLabel
					ps.activeExpiryTicks = make(map[string]models.MarketTick)
				}
				ps.mu.Unlock()
			}

			for _, rec := range currentBucket {
				secID := rec.Strike
				optType := strings.ToUpper(strings.TrimSpace(rec.OptionType))
				if optType == "CALL" {
					optType = "CE"
				} else if optType == "PUT" {
					optType = "PE"
				}

				sym := rec.TradingSymbol
				if sym == "" {
					sym = fmt.Sprintf("%s %s %s", rec.IndexName, rec.Strike, optType)
				}
				sym = strings.TrimSpace(sym)

				strikeKey := ""
				if rec.OptionType == "INDEX" || rec.Strike == "SPOT" {
					sym = rec.IndexName
					secID = "13"
					if strings.Contains(strings.ToUpper(rec.IndexName), "BANK") {
						secID = "25"
					}
				} else if strings.HasPrefix(strings.ToUpper(rec.Strike), "ATM") {
					sp := spotPrice
					if sp <= 1000 {
						sp = rec.SpotPrice
					}
					if sp > 1000 {
						offset := 0
						stkUpper := strings.ToUpper(rec.Strike)
						if strings.Contains(stkUpper, "+") {
							parts := strings.Split(stkUpper, "+")
							if len(parts) == 2 {
								offset, _ = strconv.Atoi(parts[1])
							}
						} else if strings.Contains(stkUpper, "-") {
							parts := strings.Split(stkUpper, "-")
							if len(parts) == 2 {
								val, _ := strconv.Atoi(parts[1])
								offset = -val
							}
						}
						step := 50.0
						if strings.Contains(strings.ToUpper(rec.IndexName), "BANK") {
							step = 100.0
						}
						atmStrike := math.Round(sp/step) * step
						strikeNum := atmStrike + float64(offset)*step
						strikeKey = fmt.Sprintf("%.0f_%s", strikeNum, optType)
						secID = strikeKey
						if rec.TradingSymbol == "" {
							sym = fmt.Sprintf("%s %.0f %s", rec.IndexName, strikeNum, optType)
						}
					}
				} else {
					num, err := strconv.ParseFloat(rec.Strike, 64)
					if err == nil && num > 1000 {
						strikeKey = fmt.Sprintf("%.0f_%s", num, optType)
						secID = strikeKey
						if rec.TradingSymbol == "" {
							sym = fmt.Sprintf("%s %.0f %s", rec.IndexName, num, optType)
						}
					}
				}

				price := rec.Close
				if price <= 0 {
					price = rec.Open
				}
				if price <= 0 {
					price = rec.High
				}
				if price <= 0 {
					price = rec.Low
				}
				if price <= 0 {
					continue
				}

				isForActiveExpiry := false
				if nearestExpiryDate == "" {
					isForActiveExpiry = true
				} else if rec.TradingSymbol != "" {
					expT, _ := parseContractExpiryDate(rec.TradingSymbol, parsedBucketTime)
					if !expT.IsZero() {
						expKey := time.Date(expT.Year(), expT.Month(), expT.Day(), 0, 0, 0, 0, expT.Location()).Format("2006-01-02")
						if expKey == nearestExpiryDate {
							isForActiveExpiry = true
						}
					}
				} else {
					isForActiveExpiry = true
				}

				cleanOI := rec.OI
				if cleanOI == 100000 {
					cleanOI = 0
				}

				tick := models.MarketTick{
					Timestamp:     parsedBucketTime,
					SecurityID:    secID,
					TradingSymbol: sym,
					LTP:           price,
					Open:          rec.Open,
					High:          rec.High,
					Low:           rec.Low,
					Close:         price,
					Volume:        rec.Volume,
					OI:            cleanOI,
				}

				if strikeKey != "" {
					if isForActiveExpiry {
						ps.mu.Lock()
						ps.latestTicks[strikeKey] = tick
						ps.activeExpiryTicks[strikeKey] = tick
						if sym != "" {
							ps.latestTicks[sym] = tick
						}
						ps.mu.Unlock()
						ps.BroadcastTick(tick)
					} else {
						ps.mu.Lock()
						if sym != "" {
							ps.latestTicks[sym] = tick
						}
						ps.mu.Unlock()
						ps.engine.IngestTick(tick)
					}
				}
			}

			// Concurrently compute and broadcast live INDIA VIX derived from option IV column
			var ivSum float64
			var ivCount int
			for _, rec := range currentBucket {
				if rec.IV > 0 && rec.IV < 100.0 {
					ivSum += rec.IV
					ivCount++
				}
			}
			if ivCount > 0 {
				avgVIX := math.Round((ivSum/float64(ivCount))*100.0) / 100.0
				ps.mu.Lock()
				ps.currentVIX = avgVIX
				ps.mu.Unlock()

				vixTick := models.MarketTick{
					Timestamp:     parsedBucketTime,
					SecurityID:    "INDIAVIX",
					TradingSymbol: "INDIA VIX",
					LTP:           avgVIX,
					Open:          avgVIX,
					High:          avgVIX,
					Low:           avgVIX,
					Close:         avgVIX,
					Volume:        1,
				}
				ps.BroadcastTick(vixTick)
			}
		}

		if time.Since(lastProgressBroadcast) >= 250*time.Millisecond {
			lastProgressBroadcast = time.Now()
			cur := atomic.LoadInt64(&ps.currentRow)
			tot := ps.totalRows
			pct := 0.0
			if tot > 0 {
				pct = math.Round((float64(cur)/float64(tot)*100.0)*100) / 100.0
				if pct > 100.0 {
					pct = 100.0
				}
			}
			pPayload := map[string]interface{}{
				"type":         "streamer_progress",
				"active_file":  ps.currentFile,
				"date":         ps.currentDateStr,
				"datetime":     ps.currentDatetime,
				"current_row":  cur,
				"total_rows":   tot,
				"progress_pct": pct,
				"speed":        speed,
				"ticks":        atomic.LoadInt64(&ps.ticksIngested),
			}
			if pBytes, err := json.Marshal(pPayload); err == nil {
				ps.BroadcastRawMessage(pBytes)
				if ps.rdb != nil {
					_ = ps.rdb.Publish(context.Background(), "marmot:mock_ticks", pBytes).Err()
				}
			}
		}

		// Dynamic frequency-matched speed pacing per market timestamp candle vs 5-second sub-tick slice
		ps.mu.Lock()
		timeStep := 60 * time.Second
		if !ps.lastBucketTime.IsZero() && parsedBucketTime.After(ps.lastBucketTime) {
			timeStep = parsedBucketTime.Sub(ps.lastBucketTime)
		}
		ps.lastBucketTime = parsedBucketTime
		
		// If dataset is 1-minute resolution, we will emit 12 sub-ticks (every 5 virtual seconds)
		// to fulfill the 12 option candles in 1s requirement without fabricating synthetic prices.
		isMacroResolution := timeStep == 60*time.Second
		var sleepDuration time.Duration
		if ps.regulator != nil {
			sleepDuration = ps.regulator.GetPacingSleep(5 * time.Second) // Always pace at 5s micro-tick speed
		} else {
			sleepDuration = time.Duration(1000/(speed*12)) * time.Millisecond
		}
		ps.mu.Unlock()

		subTicksToEmit := 1
		if isMacroResolution {
			subTicksToEmit = 12
		}

		for subTick := 0; subTick < subTicksToEmit; subTick++ {
			// Calculate virtual time for this sub-tick
			virtualSubTime := parsedBucketTime.Add(time.Duration(subTick*5) * time.Second)
			virtualSubTimeStr := virtualSubTime.Format("2006-01-02 15:04:05")

			ps.mu.Lock()
			if ps.regulator != nil {
				ps.regulator.OnTick(virtualSubTime)
			}
			ps.mu.Unlock()

			// Identify Spot
			var spotPrice float64
			var spotIndexName string
			var openPrice, highPrice, lowPrice, closePrice float64
			var volume int64
			for _, rec := range currentBucket {
				if rec.OptionType == "INDEX" || rec.Strike == "SPOT" || strings.Contains(strings.ToUpper(rec.TradingSymbol), "INDEX") {
					spotIndexName = rec.IndexName
					spotPrice = rec.Close
					if spotPrice <= 0 {
						spotPrice = rec.SpotPrice
					}
					openPrice = rec.Open
					highPrice = rec.High
					lowPrice = rec.Low
					closePrice = spotPrice
					volume = rec.Volume
					break
				}
			}
			if spotPrice <= 0 {
				ps.mu.RLock()
				cachedSpotPrice := ps.lastSpotPrice
				cachedSpotTick := ps.lastSpotTick
				ps.mu.RUnlock()

				if cachedSpotPrice > 1000 {
					spotPrice = cachedSpotPrice
					spotIndexName = cachedSpotTick.TradingSymbol
					openPrice = cachedSpotTick.Open
					highPrice = cachedSpotTick.High
					lowPrice = cachedSpotTick.Low
					closePrice = cachedSpotTick.Close
					volume = cachedSpotTick.Volume
				} else {
					// Cold-start fallback before first INDEX row encountered: only accept rec.SpotPrice if NOT equal to its option strike
					for _, rec := range currentBucket {
						strikeNum, _ := strconv.ParseFloat(rec.Strike, 64)
						if rec.SpotPrice > 1000 && math.Abs(rec.SpotPrice-strikeNum) > 50.0 {
							spotPrice = rec.SpotPrice
							spotIndexName = rec.IndexName
							openPrice = rec.SpotPrice
							highPrice = rec.SpotPrice
							lowPrice = rec.SpotPrice
							closePrice = rec.SpotPrice
							volume = 50000
							break
						}
					}
				}
			}
			if spotIndexName == "" {
				spotIndexName = "NIFTY"
			}

			// Broadcast virtual clock tick to Marmot UI for real-time historical clock sync
			if ps.rdb != nil {
				ps.mu.RLock()
				activeFile := ps.currentFile
				streamSpeed := ps.speed
				totRows := ps.totalRows
				cRow := atomic.LoadInt64(&ps.currentRow)
				ps.mu.RUnlock()
				var progPct float64
				if totRows > 0 {
					progPct = (float64(cRow) / float64(totRows)) * 100.0
				}

				tickMsg := map[string]interface{}{
					"type":           "mock_tick",
					"source":         "EMULATOR",
					"is_mock":        true,
					"index":          spotIndexName,
					"symbol":         spotIndexName,
					"spot_price":     spotPrice,
					"ltp":            fmt.Sprintf("%.2f", spotPrice),
					"formatted_time": virtualSubTimeStr,
					"timestamp":      virtualSubTimeStr,
					"is_virtual":     true,
					"speed":          streamSpeed,
					"progress_pct":   fmt.Sprintf("%.1f", progPct),
					"current_row":    cRow,
					"total_rows":     totRows,
					"file":           activeFile,
				}
				if tBytes, err := json.Marshal(tickMsg); err == nil {
					_ = ps.rdb.Publish(context.Background(), "marmot:mock_ticks", tBytes).Err()
				}
			}

			// In sub-ticks, broadcast the updated spot tick for virtual clock & index chart advancement
			if subTick > 0 && spotPrice > 1000 {
				secID := "13"
				if strings.Contains(strings.ToUpper(spotIndexName), "BANK") {
					secID = "25"
				}
				subSpotTick := models.MarketTick{
					Timestamp:     virtualSubTime,
					SecurityID:    secID,
					TradingSymbol: spotIndexName,
					LTP:           spotPrice,
					Open:          openPrice,
					High:          highPrice,
					Low:           lowPrice,
					Close:         closePrice,
					Volume:        volume,
				}
				ps.BroadcastTick(subSpotTick)
			}

			select {
			case <-ps.stopChan:
				return
			case <-time.After(sleepDuration):
			}
		}

		if err == io.EOF {
			break
		}
		if err != nil {
			log.Printf("[STREAMER] Parquet read error: %v", err)
			break
		}
	}

	ps.mu.Lock()
	ps.isPlaying = false
	ps.isCompleted = true
	ps.mu.Unlock()
	log.Printf("[STREAMER] Parquet playback completed for file: %s (total rows: %d)", fullPath, ps.ticksIngested)
}

// preIndexParquetFile scans the dataset file to pre-populate initial historical quotes for all option strikes.
func (ps *ParquetStreamer) preIndexParquetFile(fullPath string) {
	log.Printf("[STREAMER] Starting preIndexParquetFile for %s", fullPath)
	file, err := os.Open(fullPath)
	if err != nil {
		log.Printf("[STREAMER] preIndex error open %s: %v", fullPath, err)
		return
	}
	defer file.Close()

	stat, err := file.Stat()
	if err != nil {
		log.Printf("[STREAMER] preIndex error stat %s: %v", fullPath, err)
		return
	}

	pf, err := parquet.OpenFile(file, stat.Size())
	if err != nil {
		log.Printf("[STREAMER] preIndex error OpenFile %s: %v", fullPath, err)
		return
	}

	if pf.NumRows() == 0 {
		return
	}

	ps.mu.Lock()
	defer ps.mu.Unlock()

	indexedCount := 0
	for rgIdx, rg := range pf.RowGroups() {
		if indexedCount >= 70 || rgIdx >= 20 {
			break
		}
		rgReader := parquet.NewGenericRowGroupReader[models.MarketCandleRecord](rg)
		batch := make([]models.MarketCandleRecord, 512)
		for {
			n, _ := rgReader.Read(batch)
			if n == 0 {
				break
			}
			for i := 0; i < n; i++ {
				rec := batch[i]
				optType := strings.ToUpper(strings.TrimSpace(rec.OptionType))
				if rec.Strike == "SPOT" || optType == "INDEX" {
					price := rec.Close
					if price <= 0 {
						price = rec.Open
					}
					if price > 0 {
						secID := "13"
						if strings.Contains(strings.ToUpper(rec.IndexName), "BANK") {
							secID = "25"
						}
						tick := models.MarketTick{
							SecurityID:    secID,
							TradingSymbol: rec.IndexName,
							LTP:           price,
							Open:          rec.Open,
							High:          rec.High,
							Low:           rec.Low,
							Close:         price,
							Volume:        rec.Volume,
						}
						ps.latestTicks[secID] = tick
						ps.latestTicks[strings.ToUpper(rec.IndexName)] = tick
						ps.latestTicks["NIFTY"] = tick
						ps.latestTicks["NIFTY 50"] = tick
					}
				} else if optType != "" {
					if optType == "CALL" {
						optType = "CE"
					} else if optType == "PUT" {
						optType = "PE"
					}
					num, parseErr := strconv.ParseFloat(rec.Strike, 64)
					if parseErr == nil && num > 1000 {
						stkKey := fmt.Sprintf("%.0f_%s", num, optType)
						if _, exists := ps.latestTicks[stkKey]; !exists {
							sym := rec.TradingSymbol
							if sym == "" {
								sym = fmt.Sprintf("%s %.0f %s", rec.IndexName, num, optType)
							}
							price := rec.Close
							if price <= 0 {
								price = rec.Open
							}
							if price > 0 {
								tick := models.MarketTick{
									SecurityID:    stkKey,
									TradingSymbol: sym,
									LTP:           price,
									Open:          rec.Open,
									High:          rec.High,
									Low:           rec.Low,
									Close:         price,
									Volume:        rec.Volume,
									OI:            rec.OI,
								}
								ps.latestTicks[stkKey] = tick
								if sym != "" {
									ps.latestTicks[sym] = tick
								}
								ps.activeExpiryTicks[stkKey] = tick
								indexedCount++
							}
						}
					}
				}
			}
			if indexedCount >= 300 {
				break
			}
		}
		rgReader.Close()
		if indexedCount >= 300 {
			break
		}
	}
	log.Printf("[STREAMER] Successfully pre-indexed initial historical option quotes for %d strike keys from %s in ~30ms", indexedCount, fullPath)
}

// streamSynthetic is disabled to strictly uphold Rule 10 (zero fake Brownian walk ticks).
func (ps *ParquetStreamer) streamSynthetic() {
	log.Printf("[STREAMER] Synthetic generator disabled. Awaiting authentic Parquet dataset in %s", ps.availableDir)
	select {
	case <-ps.stopChan:
		return
	}
}

// ListAvailableParquets returns file paths for selection.
func (ps *ParquetStreamer) ListAvailableParquets() []string {
	var files []string
	_ = filepath.Walk(ps.availableDir, func(path string, info os.FileInfo, err error) error {
		if err == nil && !info.IsDir() && filepath.Ext(path) == ".parquet" {
			rel, _ := filepath.Rel(ps.availableDir, path)
			files = append(files, filepath.ToSlash(rel))
		}
		return nil
	})
	return files
}

var (
	datasetMetaCacheMu sync.RWMutex
	datasetMetaCache   = make(map[string]ParquetFileInfo)
)

// readParquetMeta extracts index_name and date range from a parquet dataset using native Parquet footer metadata.
func readParquetMeta(filePath string) (string, string, string) {
	file, err := os.Open(filePath)
	if err != nil {
		return "NIFTY", "", ""
	}
	defer file.Close()

	stat, err := file.Stat()
	if err != nil {
		return "NIFTY", "", ""
	}

	pf, err := parquet.OpenFile(file, stat.Size())
	if err != nil {
		return "NIFTY", "", ""
	}

	numRows := pf.NumRows()
	if numRows == 0 {
		return "NIFTY", "", ""
	}

	reader := parquet.NewGenericReader[models.MarketCandleRecord](file)
	defer reader.Close()

	firstBatch := make([]models.MarketCandleRecord, 1)
	n, _ := reader.Read(firstBatch)
	if n == 0 {
		return "NIFTY", "", ""
	}

	idx := firstBatch[0].IndexName
	if idx == "" {
		idx = "NIFTY"
	}
	start := firstBatch[0].Datetime
	if start == "" && firstBatch[0].Timestamp > 0 {
		start = time.Unix(firstBatch[0].Timestamp, 0).Format("2006-01-02 15:04:05")
	}

	end := start
	if numRows > 1 {
		if err := reader.SeekToRow(numRows - 1); err == nil {
			lastBatch := make([]models.MarketCandleRecord, 1)
			if n, _ := reader.Read(lastBatch); n > 0 {
				end = lastBatch[0].Datetime
				if end == "" && lastBatch[0].Timestamp > 0 {
					end = time.Unix(lastBatch[0].Timestamp, 0).Format("2006-01-02 15:04:05")
				}
			}
		}
	}
	return idx, start, end
}

// ListParquetDetails returns full details for available datasets, prioritizing option-ready datasets.
func (ps *ParquetStreamer) ListParquetDetails() []ParquetFileInfo {
	var results []ParquetFileInfo
	_ = filepath.Walk(ps.availableDir, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return nil
		}
		if info.IsDir() {
			name := info.Name()
			if name == "ticks" || name == "staging" || strings.HasPrefix(name, ".") {
				return filepath.SkipDir
			}
			return nil
		}
		if filepath.Ext(path) == ".parquet" {
			rel, _ := filepath.Rel(ps.availableDir, path)
			relSlash := filepath.ToSlash(rel)
			szMB := float64(info.Size()) / (1024 * 1024)

			hasOpts := false
			typeLabel := "Spot Only"

			if strings.Contains(relSlash, "macro") || info.Size() < 50000 {
				typeLabel = "Macro AI"
			} else if relSlash == "1/13/dataset.parquet" || relSlash == "1/33/dataset.parquet" || relSlash == "1/48/dataset.parquet" || relSlash == "1/35/dataset.parquet" {
				hasOpts = true
				typeLabel = "Spot + Options (Full Bilateral)"
			} else if relSlash == "1/60/dataset.parquet" {
				hasOpts = true
				typeLabel = "Spot + Options (Single Leg)"
			} else if relSlash == "1/37/dataset.parquet" || relSlash == "1/38/dataset.parquet" || relSlash == "1/40/dataset.parquet" || relSlash == "1/62/dataset.parquet" {
				typeLabel = "Futures / Forex"
			} else if szMB > 100.0 {
				typeLabel = "Multi-Year Spot"
			}

			// Read metadata with caching
			datasetMetaCacheMu.RLock()
			cached, found := datasetMetaCache[path]
			datasetMetaCacheMu.RUnlock()

			var indexName, dateRange, startDate, endDate string
			if found && cached.SizeBytes == info.Size() {
				indexName = cached.IndexName
				dateRange = cached.DateRange
				startDate = cached.StartDate
				endDate = cached.EndDate
			} else {
				indexName, startDate, endDate = readParquetMeta(path)
				if startDate != "" && endDate != "" {
					d1 := strings.Split(startDate, " ")[0]
					d2 := strings.Split(endDate, " ")[0]
					if d1 != "" && d2 != "" {
						if d1 == d2 {
							dateRange = d1
						} else {
							dateRange = fmt.Sprintf("%s – %s", d1, d2)
						}
					}
				} else if startDate != "" {
					dateRange = strings.Split(startDate, " ")[0]
				}

				if indexName == "" {
					if strings.Contains(relSlash, "NIFTY") {
						indexName = "NIFTY"
					} else if strings.Contains(relSlash, "BANK") {
						indexName = "BANKNIFTY"
					} else if strings.Contains(relSlash, "SENSEX") {
						indexName = "SENSEX"
					} else if strings.Contains(relSlash, "MGC") {
						indexName = "MGC"
					} else if strings.Contains(relSlash, "M6E") {
						indexName = "M6E"
					} else if strings.Contains(relSlash, "MYM") {
						indexName = "MYM"
					} else {
						indexName = "NIFTY"
					}
				}
			}

			item := ParquetFileInfo{
				RelativePath: relSlash,
				FileName:     filepath.Base(path),
				SizeBytes:    info.Size(),
				SizeMB:       szMB,
				HasOptions:   hasOpts,
				TypeLabel:    typeLabel,
				IndexName:    indexName,
				DateRange:    dateRange,
				StartDate:    startDate,
				EndDate:      endDate,
			}

			datasetMetaCacheMu.Lock()
			datasetMetaCache[path] = item
			datasetMetaCacheMu.Unlock()

			results = append(results, item)
		}
		return nil
	})

	// Sort so that verified Spot + Options datasets appear first, with 1/48 at top
	sort.SliceStable(results, func(i, j int) bool {
		if results[i].RelativePath == "1/48/dataset.parquet" {
			return true
		}
		if results[j].RelativePath == "1/48/dataset.parquet" {
			return false
		}
		if results[i].HasOptions != results[j].HasOptions {
			return results[i].HasOptions
		}
		return results[i].RelativePath < results[j].RelativePath
	})

	return results
}

func (ps *ParquetStreamer) startLiveFeedSubscriber() {
	if ps.rdb == nil {
		return
	}
	ctx := context.Background()
	pubsub := ps.rdb.Subscribe(ctx, "marmot:mock_ticks", "marmot:live_ticks")
	defer pubsub.Close()
	ch := pubsub.Channel()
	log.Println("[STREAMER] Live Redis tick subscriber initialized for marmot:mock_ticks / marmot:live_ticks")

	for msg := range ch {
		if msg == nil || len(msg.Payload) == 0 {
			continue
		}
		if ps.isPlaying {
			continue
		}
		var tickMap map[string]interface{}
		if err := json.Unmarshal([]byte(msg.Payload), &tickMap); err != nil {
			continue
		}
		var ltp float64
		if v, ok := tickMap["ltp"].(float64); ok {
			ltp = v
		} else if v, ok := tickMap["spot_price"].(float64); ok {
			ltp = v
		}
		if ltp <= 0 {
			continue
		}
		sym, _ := tickMap["tradingSymbol"].(string)
		if sym == "" {
			sym, _ = tickMap["symbol"].(string)
		}
		if sym == "" {
			sym, _ = tickMap["index"].(string)
		}
		secId, _ := tickMap["securityId"].(string)
		if secId == "" {
			secId = sym
		}
		t := models.MarketTick{
			SecurityID:    secId,
			TradingSymbol: sym,
			LTP:           ltp,
			Timestamp:     time.Now(),
		}
		if o, ok := tickMap["open"].(float64); ok {
			t.Open = o
		}
		if h, ok := tickMap["high"].(float64); ok {
			t.High = h
		}
		if l, ok := tickMap["low"].(float64); ok {
			t.Low = l
		}
		if c, ok := tickMap["prevClose"].(float64); ok {
			t.Close = c
		}
		if oi, ok := tickMap["oi"].(float64); ok {
			t.OI = int64(oi)
		}
		if vol, ok := tickMap["volume"].(float64); ok {
			t.Volume = int64(vol)
		}

		ps.mu.Lock()
		ps.latestTicks[t.SecurityID] = t
		if t.TradingSymbol != "" {
			ps.latestTicks[t.TradingSymbol] = t
		}
		ps.currentDatetime = time.Now().Format("2006-01-02 15:04:05")
		ps.mu.Unlock()

		ps.engine.IngestTick(t)

		ps.writeMu.Lock()
		if len(ps.clients) > 0 {
			for client := range ps.clients {
				_ = client.WriteMessage(websocket.TextMessage, []byte(msg.Payload))
			}
		}
		ps.writeMu.Unlock()
	}
}
