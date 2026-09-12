package streamer

import (
	"encoding/json"
	"fmt"
	"io"
	"log"
	"math"
	"math/rand"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/gorilla/websocket"
	"github.com/parquet-go/parquet-go"
	"dhan-emulator/engine"
	"dhan-emulator/models"
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
}

// ParquetStreamer replays parquet ticks or synthetic feeds into the matching engine and WebSocket clients.
type ParquetStreamer struct {
	mu              sync.RWMutex
	engine          *engine.MatchingEngine
	clients         map[*websocket.Conn]bool
	speed           int // Multiplier: 1, 5, 10, 25, 50, 100, 250
	isPlaying       bool
	stopChan        chan struct{}
	currentFile     string
	availableDir    string
	ticksIngested   int64
	totalRows       int64
	currentRow      int64
	currentDatetime string
	currentDateStr  string
	latestTicks     map[string]models.MarketTick
}

// NewParquetStreamer initializes the market feed streamer.
func NewParquetStreamer(eng *engine.MatchingEngine, backupDir string) *ParquetStreamer {
	if backupDir == "" {
		backupDir = "/app/backup"
	}
	ps := &ParquetStreamer{
		engine:          eng,
		clients:         make(map[*websocket.Conn]bool),
		speed:           1,
		isPlaying:       false,
		availableDir:    backupDir,
		currentDatetime: time.Now().Format("2006-01-02 15:04:05"),
		currentDateStr:  time.Now().Format("2006-01-02"),
		latestTicks:     make(map[string]models.MarketTick),
	}

	// Auto-select first available parquet file if present
	files := ps.ListParquetDetails()
	if len(files) > 0 {
		ps.currentFile = files[0].RelativePath
		log.Printf("[STREAMER] Initialized with primary Parquet dataset: %s (%.2f MB)", ps.currentFile, files[0].SizeMB)
	}

	ps.Start()
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

	// Broadcast to WebSocket clients
	ps.mu.RLock()
	defer ps.mu.RUnlock()

	if len(ps.clients) == 0 {
		return
	}

	msg, err := json.Marshal(tick)
	if err != nil {
		return
	}

	for client := range ps.clients {
		if err := client.WriteMessage(websocket.TextMessage, msg); err != nil {
			client.Close()
			delete(ps.clients, client)
		}
	}
}

// Start begins the market feed playback loop.
func (ps *ParquetStreamer) Start() {
	ps.mu.Lock()
	if ps.isPlaying {
		ps.mu.Unlock()
		return
	}
	ps.isPlaying = true
	ps.stopChan = make(chan struct{})
	ps.mu.Unlock()

	go ps.streamLoop()
}

// Stop pauses market feed playback.
func (ps *ParquetStreamer) Stop() {
	ps.mu.Lock()
	defer ps.mu.Unlock()
	if !ps.isPlaying {
		return
	}
	ps.isPlaying = false
	close(ps.stopChan)
}

// SetSpeed sets tick replay multiplier.
func (ps *ParquetStreamer) SetSpeed(speed int) {
	ps.mu.Lock()
	defer ps.mu.Unlock()
	if speed <= 0 {
		speed = 1
	}
	ps.speed = speed
}

// SelectParquetFile changes active dataset and restarts replay.
func (ps *ParquetStreamer) SelectParquetFile(file string) {
	ps.mu.Lock()
	ps.currentFile = file
	wasPlaying := ps.isPlaying
	if wasPlaying {
		close(ps.stopChan)
		ps.isPlaying = false
	}
	ps.mu.Unlock()

	if wasPlaying {
		ps.Start()
	}
}

// GetStatus returns current streamer operational state.
func (ps *ParquetStreamer) GetStatus() (bool, int, string, int64) {
	ps.mu.RLock()
	defer ps.mu.RUnlock()
	return ps.isPlaying, ps.speed, ps.currentFile, atomic.LoadInt64(&ps.ticksIngested)
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

// GetOptionChain builds and returns a complete, synchronized option chain matrix for the requested index.
func (ps *ParquetStreamer) GetOptionChain(indexName string) models.OptionChainResponse {
	ps.mu.RLock()
	defer ps.mu.RUnlock()

	idxClean := strings.ToUpper(strings.TrimSpace(indexName))
	if idxClean == "" {
		idxClean = "NIFTY"
	}

	strikeStep := 50
	displaySymbol := "NIFTY 50"
	baseSpot := 24542.80

	if strings.Contains(idxClean, "BANK") {
		strikeStep = 100
		displaySymbol = "BANK NIFTY"
		baseSpot = 51280.50
	} else if strings.Contains(idxClean, "SENSEX") {
		strikeStep = 100
		displaySymbol = "BSE SENSEX"
		baseSpot = 80420.50
	} else if strings.Contains(idxClean, "MIDCP") {
		strikeStep = 25
		displaySymbol = "MIDCP NIFTY"
		baseSpot = 12450.00
	}

	// 1. Locate current Spot price from latestTicks
	spotLTP := baseSpot
	dayOpen := baseSpot - 50.0
	dayHigh := baseSpot + 120.0
	dayLow := baseSpot - 80.0
	prevClose := baseSpot - 85.0

	for _, t := range ps.latestTicks {
		symUpper := strings.ToUpper(t.TradingSymbol)
		if symUpper == idxClean || symUpper == displaySymbol || t.SecurityID == "13" || t.SecurityID == "25" {
			if t.LTP > 0 {
				spotLTP = t.LTP
				if t.Open > 0 {
					dayOpen = t.Open
				}
				if t.High > 0 {
					dayHigh = t.High
				}
				if t.Low > 0 {
					dayLow = t.Low
				}
				if t.Close > 0 {
					prevClose = t.Close - (spotLTP * 0.004)
				}
				break
			}
		}
	}

	change := spotLTP - prevClose
	changePct := (change / prevClose) * 100.0
	isPositive := change >= 0

	atmStrikeVal := math.Round(spotLTP/float64(strikeStep)) * float64(strikeStep)

	// 2. Build 31 strikes window (ATM - 15*step to ATM + 15*step)
	var strikes []models.OptionStrikeRow
	totalStrikes := 31
	halfWindow := totalStrikes / 2

	totalCallVol := int64(0)
	totalPutVol := int64(0)

	for i := -halfWindow; i <= halfWindow; i++ {
		stkPrice := atmStrikeVal + float64(i*strikeStep)
		isATM := (stkPrice == atmStrikeVal)
		isActiveWindow := (i >= -3 && i <= 3) // Compact ±3 strikes (7 active)

		diff := spotLTP - stkPrice
		ceIntrinsic := math.Max(0, diff)
		peIntrinsic := math.Max(0, -diff)
		timeVal := math.Max(25.0, float64(strikeStep)*1.2-math.Abs(diff)*0.18)
		if timeVal < 5.0 {
			timeVal = 5.0
		}

		ceLTP := float64(int((ceIntrinsic+timeVal)*100)) / 100.0
		peLTP := float64(int((peIntrinsic+timeVal)*100)) / 100.0
		ceChg := float64(int((change*0.5+float64(i)*-1.2)*10)) / 10.0
		peChg := float64(int((-change*0.5+float64(i)*1.2)*10)) / 10.0
		ceOI := fmt.Sprintf("%d,000", int(math.Max(20, 150-float64(i)*4)))
		peOI := fmt.Sprintf("%d,000", int(math.Max(20, 150+float64(i)*4)))

		stkStr := fmt.Sprintf("%.0f", stkPrice)
		for _, t := range ps.latestTicks {
			if strings.Contains(t.TradingSymbol, stkStr) || t.SecurityID == stkStr {
				symUpper := strings.ToUpper(t.TradingSymbol)
				if strings.Contains(symUpper, "CE") || strings.Contains(symUpper, "CALL") {
					ceLTP = t.LTP
					ceChg = float64(int((t.LTP-t.Open)*10)) / 10.0
					if t.Volume > 0 {
						ceOI = fmt.Sprintf("%d", t.Volume*12)
						totalCallVol += t.Volume
					}
				} else if strings.Contains(symUpper, "PE") || strings.Contains(symUpper, "PUT") {
					peLTP = t.LTP
					peChg = float64(int((t.LTP-t.Open)*10)) / 10.0
					if t.Volume > 0 {
						peOI = fmt.Sprintf("%d", t.Volume*12)
						totalPutVol += t.Volume
					}
				}
			}
		}

		row := models.OptionStrikeRow{
			Strike:         stkPrice,
			IsActiveWindow: isActiveWindow,
			IsATM:          isATM,
			CE_LTP:         ceLTP,
			CE_Change:      ceChg,
			CE_ChangePct:   float64(int((ceChg/ceLTP)*1000)) / 10.0,
			CE_OI:          ceOI,
			PE_LTP:         peLTP,
			PE_Change:      peChg,
			PE_ChangePct:   float64(int((peChg/peLTP)*1000)) / 10.0,
			PE_OI:          peOI,
		}
		strikes = append(strikes, row)
	}

	pcr := 1.12
	if totalCallVol > 0 {
		pcr = float64(totalPutVol) / float64(totalCallVol)
		if pcr < 0.4 || pcr > 2.5 {
			pcr = 1.08
		}
	}

	timeStr := ps.currentDatetime
	if timeStr == "" {
		timeStr = time.Now().Format("2006-01-02 15:04:05")
	}

	sign := ""
	if change >= 0 {
		sign = "+"
	}

	return models.OptionChainResponse{
		IsLive:        true,
		IsMockLive:    true,
		FeedStatus:    "STREAMING",
		IndexName:     idxClean,
		SpotSymbol:    displaySymbol,
		FyersSymbol:   fmt.Sprintf("DHAN_MOCK:%s", idxClean),
		SpotLTP:       fmt.Sprintf("%.2f", spotLTP),
		RawSpotLTP:    spotLTP,
		SpotChange:    fmt.Sprintf("%s%.2f", sign, change),
		SpotChangePct: fmt.Sprintf("%s%.2f%%", sign, changePct),
		IsPositive:    isPositive,
		OpenPrice:     fmt.Sprintf("%.2f", dayOpen),
		HighPrice:     fmt.Sprintf("%.2f", dayHigh),
		LowPrice:      fmt.Sprintf("%.2f", dayLow),
		PrevClose:     fmt.Sprintf("%.2f", prevClose),
		ATMStrike:     fmt.Sprintf("%.0f", atmStrikeVal),
		StrikeStep:    strikeStep,
		PCR:           float64(int(pcr*100)) / 100.0,
		IndiaVIX:      13.28,
		TotalStrikes:  len(strikes),
		Strikes:       strikes,
		LastUpdated:   timeStr,
	}
}

// streamLoop routes between real parquet replay and synthetic generator.
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

	ps.streamSynthetic()
}

// streamParquetFile reads binary Parquet records and streams ticks rapidly.
func (ps *ParquetStreamer) streamParquetFile(fullPath string) {
	log.Printf("[STREAMER] Starting Parquet replay from: %s", fullPath)

	file, err := os.Open(fullPath)
	if err != nil {
		log.Printf("[STREAMER] Error opening parquet %s: %v, fallback to synthetic", fullPath, err)
		ps.streamSynthetic()
		return
	}
	defer file.Close()

	reader := parquet.NewGenericReader[models.MarketCandleRecord](file)
	defer reader.Close()

	totalRows := reader.NumRows()
	ps.mu.Lock()
	ps.totalRows = totalRows
	atomic.StoreInt64(&ps.currentRow, 0)
	ps.mu.Unlock()

	buf := make([]models.MarketCandleRecord, 64)

	for {
		ps.mu.RLock()
		if !ps.isPlaying {
			ps.mu.RUnlock()
			return
		}
		speed := ps.speed
		ps.mu.RUnlock()

		n, readErr := reader.Read(buf)
		if n > 0 {
			atomic.AddInt64(&ps.currentRow, int64(n))
			lastRec := buf[n-1]
			if lastRec.Datetime != "" {
				ps.mu.Lock()
				ps.currentDatetime = lastRec.Datetime
				if len(lastRec.Datetime) >= 10 {
					ps.currentDateStr = lastRec.Datetime[:10]
				}
				ps.mu.Unlock()
			} else if lastRec.Timestamp > 0 {
				ps.mu.Lock()
				ps.currentDatetime = time.Unix(lastRec.Timestamp, 0).Format("2006-01-02 15:04:05")
				ps.currentDateStr = time.Unix(lastRec.Timestamp, 0).Format("2006-01-02")
				ps.mu.Unlock()
			}

			now := time.Now()
			for i := 0; i < n; i++ {
				rec := buf[i]
				secID := rec.Strike
				if secID == "" || secID == "SPOT" {
					if strings.Contains(strings.ToUpper(rec.IndexName), "BANK") {
						secID = "25"
					} else {
						secID = "13"
					}
				}

				sym := fmt.Sprintf("%s %s %s", rec.IndexName, rec.Strike, rec.OptionType)
				sym = strings.TrimSpace(sym)
				if rec.OptionType == "INDEX" || rec.Strike == "SPOT" {
					sym = rec.IndexName
				}

				price := rec.Close
				if price <= 0 {
					price = rec.Open
				}
				if price <= 0 {
					price = rec.SpotPrice
				}
				if price <= 0 {
					price = 100.0
				}

				tick := models.MarketTick{
					Timestamp:     now,
					SecurityID:    secID,
					TradingSymbol: sym,
					LTP:           price,
					Open:          rec.Open,
					High:          rec.High,
					Low:           rec.Low,
					Close:         price,
					Volume:        rec.Volume,
				}
				ps.BroadcastTick(tick)
			}
		}

		if readErr == io.EOF {
			log.Printf("[STREAMER] Reached EOF on %s, restarting cycle...", fullPath)
			file.Seek(0, 0)
			reader.Reset()
			atomic.StoreInt64(&ps.currentRow, 0)
		} else if readErr != nil {
			log.Printf("[STREAMER] Parquet read error: %v, switching to synthetic", readErr)
			break
		}

		// Dynamic speed pacing
		var sleepDuration time.Duration
		if speed >= 250 {
			sleepDuration = 100 * time.Microsecond
		} else if speed >= 100 {
			sleepDuration = 400 * time.Microsecond
		} else {
			sleepDuration = time.Duration(1000/speed) * time.Millisecond
			if sleepDuration < 1*time.Millisecond {
				sleepDuration = 1 * time.Millisecond
			}
		}

		select {
		case <-ps.stopChan:
			return
		case <-time.After(sleepDuration):
		}
	}
}

// streamSynthetic runs random Brownian walk tick generation.
func (ps *ParquetStreamer) streamSynthetic() {
	symbols := []struct {
		secID  string
		symbol string
		base   float64
	}{
		{"13", "NIFTY", 24500.0},
		{"25", "BANKNIFTY", 51200.0},
		{"50001", "NIFTY 24500 CE", 120.50},
		{"50002", "NIFTY 24500 PE", 115.00},
		{"50003", "NIFTY 24600 CE", 72.25},
		{"50004", "NIFTY 24400 PE", 68.80},
		{"60001", "BANKNIFTY 51200 CE", 280.00},
		{"60002", "BANKNIFTY 51200 PE", 265.40},
		{"70001", "RELIANCE", 2980.50},
		{"70002", "HDFCBANK", 1640.20},
	}

	prices := make(map[string]float64)
	for _, s := range symbols {
		prices[s.secID] = s.base
	}

	for {
		ps.mu.RLock()
		if !ps.isPlaying {
			ps.mu.RUnlock()
			return
		}
		speed := ps.speed
		ps.mu.RUnlock()

		sleepDuration := time.Duration(1000/speed) * time.Millisecond
		if sleepDuration < 5*time.Millisecond {
			sleepDuration = 5 * time.Millisecond
		}

		select {
		case <-ps.stopChan:
			return
		case <-time.After(sleepDuration):
			now := time.Now()
			ps.mu.Lock()
			ps.currentDatetime = now.Format("2006-01-02 15:04:05")
			ps.currentDateStr = now.Format("2006-01-02")
			ps.mu.Unlock()

			for _, s := range symbols {
				curr := prices[s.secID]
				delta := (rand.Float64() - 0.49) * (curr * 0.0012)
				newPrice := curr + delta
				if newPrice <= 0.05 {
					newPrice = 0.05
				}
				prices[s.secID] = newPrice

				tick := models.MarketTick{
					Timestamp:     now,
					SecurityID:    s.secID,
					TradingSymbol: s.symbol,
					LTP:           float64(int(newPrice*100)) / 100.0,
					Volume:        int64(rand.Intn(5000) + 100),
				}
				ps.BroadcastTick(tick)
			}
		}
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

// ListParquetDetails returns full details for available datasets.
func (ps *ParquetStreamer) ListParquetDetails() []ParquetFileInfo {
	var results []ParquetFileInfo
	_ = filepath.Walk(ps.availableDir, func(path string, info os.FileInfo, err error) error {
		if err == nil && !info.IsDir() && filepath.Ext(path) == ".parquet" {
			rel, _ := filepath.Rel(ps.availableDir, path)
			results = append(results, ParquetFileInfo{
				RelativePath: filepath.ToSlash(rel),
				FileName:     filepath.Base(path),
				SizeBytes:    info.Size(),
				SizeMB:       float64(info.Size()) / (1024 * 1024),
			})
		}
		return nil
	})
	return results
}
