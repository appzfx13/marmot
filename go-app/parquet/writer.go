package parquet

import (
	"fmt"
	"log"
	"math"
	"os"
	"path/filepath"
	"sort"
	"sync"
	"sync/atomic"
	"time"

	parquet_go "github.com/parquet-go/parquet-go"
)

// Tick represents a single market tick suitable for Parquet storage.
type Tick struct {
	Timestamp int64   `parquet:"timestamp"`
	Datetime  string  `parquet:"datetime"`
	IndexName string  `parquet:"index_name"`
	Symbol    string  `parquet:"symbol"`
	SpotPrice float64 `parquet:"spot_price"`
	Change    float64 `parquet:"change"`
	ChangePct float64 `parquet:"change_pct"`
	High      float64 `parquet:"high"`
	Low       float64 `parquet:"low"`
}

// TickWriter manages an in-memory buffer of ticks, flushing to Parquet in chunks.
type TickWriter struct {
	mu            sync.Mutex
	buffer        []Tick
	chunkSize     int
	flushInterval time.Duration
	baseDir       string
	stopChan      chan struct{}
}

// NewTickWriter initializes a thread-safe buffered Parquet writer for live ticks.
func NewTickWriter(baseDir string, chunkSize int, flushInterval time.Duration) *TickWriter {
	tw := &TickWriter{
		buffer:        make([]Tick, 0, chunkSize),
		chunkSize:     chunkSize,
		flushInterval: flushInterval,
		baseDir:       baseDir,
		stopChan:      make(chan struct{}),
	}
	go tw.periodicFlush()
	return tw
}

// Write adds a tick to the in-memory buffer. Flushes if chunk size is reached.
func (tw *TickWriter) Write(tick Tick) {
	tw.mu.Lock()
	defer tw.mu.Unlock()

	tw.buffer = append(tw.buffer, tick)
	if len(tw.buffer) >= tw.chunkSize {
		tw.flushLocked()
	}
}

// periodicFlush triggers a flush based on the configured time interval.
func (tw *TickWriter) periodicFlush() {
	ticker := time.NewTicker(tw.flushInterval)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			tw.mu.Lock()
			if len(tw.buffer) > 0 {
				tw.flushLocked()
			}
			tw.mu.Unlock()
		case <-tw.stopChan:
			return
		}
	}
}

// Close gracefully flushes the remaining buffer and stops the periodic flusher.
func (tw *TickWriter) Close() {
	close(tw.stopChan)
	tw.mu.Lock()
	defer tw.mu.Unlock()
	if len(tw.buffer) > 0 {
		tw.flushLocked()
	}
}

// flushLocked writes the current buffer to a new Parquet file and resets the buffer.
func (tw *TickWriter) flushLocked() {
	count := len(tw.buffer)
	if count == 0 {
		return
	}

	// Create daily partitioning: /app/backup/ticks/YYYY-MM-DD
	now := time.Now()
	dateDir := now.Format("2006-01-02")
	dirPath := filepath.Join(tw.baseDir, "ticks", dateDir)
	if err := os.MkdirAll(dirPath, 0755); err != nil {
		log.Printf("⚠️ [TickWriter] Failed to create directory %s: %v\n", dirPath, err)
		return
	}

	fileName := fmt.Sprintf("ticks_%d.parquet", now.UnixNano())
	filePath := filepath.Join(dirPath, fileName)

	file, err := os.OpenFile(filePath, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, 0644)
	if err != nil {
		log.Printf("⚠️ [TickWriter] Failed to create parquet file %s: %v\n", filePath, err)
		return
	}
	defer file.Close()

	writer := parquet_go.NewGenericWriter[Tick](
		file,
		parquet_go.Compression(&parquet_go.Snappy),
	)

	if _, err := writer.Write(tw.buffer); err != nil {
		log.Printf("⚠️ [TickWriter] Failed to write %d ticks to %s: %v\n", count, filePath, err)
	}

	if err := writer.Close(); err != nil {
		log.Printf("⚠️ [TickWriter] Failed to close parquet writer for %s: %v\n", filePath, err)
	} else {
		log.Printf("💾 [TickWriter] Flushed %d ticks to %s\n", count, filePath)
	}

	// Reset buffer
	tw.buffer = tw.buffer[:0]
}

// Spot1SRecord represents an aggregated 1-second index spot candle in Parquet format.
type Spot1SRecord struct {
	Timestamp int64   `parquet:"timestamp,int(64)" json:"timestamp"`
	Datetime  string  `parquet:"datetime,string" json:"datetime"`
	IndexName string  `parquet:"index_name,string" json:"index_name"`
	Open      float64 `parquet:"open,double" json:"open"`
	High      float64 `parquet:"high,double" json:"high"`
	Low       float64 `parquet:"low,double" json:"low"`
	Close     float64 `parquet:"close,double" json:"close"`
}

// SpotTickItem represents incoming spot tick telemetry for async ingestion.
type SpotTickItem struct {
	IndexName string
	Price     float64
	Timestamp int64
}

// Spot1SRecorder aggregates live index ticks into 1-second OHLC candles and writes to Parquet.
type Spot1SRecorder struct {
	mu           sync.Mutex
	baseDir      string
	inChan       chan SpotTickItem
	stopChan     chan struct{}
	isActive     atomic.Bool
	activeBucket map[string]*Spot1SRecord // key: indexName_timestamp
	pending      []Spot1SRecord
}

// NewSpot1SRecorder initializes an asynchronous, zero-load 1-second spot recorder.
func NewSpot1SRecorder(baseDir string) *Spot1SRecorder {
	r := &Spot1SRecorder{
		baseDir:      baseDir,
		inChan:       make(chan SpotTickItem, 20000),
		stopChan:     make(chan struct{}),
		activeBucket: make(map[string]*Spot1SRecord),
		pending:      make([]Spot1SRecord, 0, 1000),
	}
	go r.runLoop()
	return r
}

// SetActive manually enables or disables the recorder.
func (r *Spot1SRecorder) SetActive(active bool) {
	r.isActive.Store(active)
	if active {
		log.Println("🟢 [Spot1SRecorder] Activated live 1-second spot tick recording.")
	} else {
		log.Println("🔴 [Spot1SRecorder] Deactivated live 1-second spot tick recording.")
		r.Flush()
	}
}

// RecordSpotTickAsync passes incoming spot ticks into the non-blocking channel.
func (r *Spot1SRecorder) RecordSpotTickAsync(indexName string, price float64, epoch int64) {
	if price <= 0 {
		return
	}
	if !r.isActive.Load() {
		if IsIndianMarketHours() {
			r.isActive.Store(true)
		} else {
			return
		}
	}
	if epoch <= 0 {
		epoch = time.Now().Unix()
	} else if epoch > 1e11 {
		epoch = epoch / 1000
	}

	select {
	case r.inChan <- SpotTickItem{IndexName: indexName, Price: price, Timestamp: epoch}:
	default:
		// Non-blocking drop safeguard ensures zero impact on live trading
	}
}

// runLoop aggregates incoming ticks by second and flushes every 60 seconds.
func (r *Spot1SRecorder) runLoop() {
	flushTicker := time.NewTicker(60 * time.Second)
	defer flushTicker.Stop()

	ist, err := time.LoadLocation("Asia/Kolkata")
	if err != nil {
		ist = time.FixedZone("IST", 5*3600+1800)
	}

	for {
		select {
		case item, ok := <-r.inChan:
			if !ok {
				return
			}
			r.processTick(item, ist)
		case <-flushTicker.C:
			r.Flush()
		case <-r.stopChan:
			r.Flush()
			return
		}
	}
}

// processTick updates or initializes the second-level candle for the given index.
func (r *Spot1SRecorder) processTick(item SpotTickItem, loc *time.Location) {
	r.mu.Lock()
	defer r.mu.Unlock()

	bucketKey := fmt.Sprintf("%s_%d", item.IndexName, item.Timestamp)
	rec, exists := r.activeBucket[bucketKey]
	if !exists {
		t := time.Unix(item.Timestamp, 0).In(loc)
		rec = &Spot1SRecord{
			Timestamp: item.Timestamp,
			Datetime:  t.Format("2006-01-02 15:04:05"),
			IndexName: item.IndexName,
			Open:      item.Price,
			High:      item.Price,
			Low:       item.Price,
			Close:     item.Price,
		}
		r.activeBucket[bucketKey] = rec
	} else {
		rec.High = math.Max(rec.High, item.Price)
		rec.Low = math.Min(rec.Low, item.Price)
		rec.Close = item.Price
	}

	// Move older seconds (current second - 2s) to pending slice
	cutoff := item.Timestamp - 2
	for k, b := range r.activeBucket {
		if b.Timestamp < cutoff {
			r.pending = append(r.pending, *b)
			delete(r.activeBucket, k)
		}
	}
}

// Flush writes all pending 1-second candles to disk in a daily part file.
func (r *Spot1SRecorder) Flush() {
	r.mu.Lock()
	// Drain any remaining active buckets
	for k, b := range r.activeBucket {
		r.pending = append(r.pending, *b)
		delete(r.activeBucket, k)
	}

	count := len(r.pending)
	if count == 0 {
		r.mu.Unlock()
		return
	}

	toFlush := make([]Spot1SRecord, count)
	copy(toFlush, r.pending)
	r.pending = r.pending[:0]
	r.mu.Unlock()

	now := time.Now()
	dateDir := now.Format("2006-01-02")
	partsDir := filepath.Join(r.baseDir, "ticks", dateDir, "spot_parts")
	if err := os.MkdirAll(partsDir, 0755); err != nil {
		log.Printf("⚠️ [Spot1SRecorder] Failed to create dir %s: %v", partsDir, err)
		return
	}

	fileName := fmt.Sprintf("spot_%d.parquet", now.UnixNano())
	filePath := filepath.Join(partsDir, fileName)

	file, err := os.OpenFile(filePath, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, 0644)
	if err != nil {
		log.Printf("⚠️ [Spot1SRecorder] Failed to create %s: %v", filePath, err)
		return
	}
	defer file.Close()

	writer := parquet_go.NewGenericWriter[Spot1SRecord](file, parquet_go.Compression(&parquet_go.Snappy))
	if _, err := writer.Write(toFlush); err != nil {
		log.Printf("⚠️ [Spot1SRecorder] Write error: %v", err)
	}
	if err := writer.Close(); err != nil {
		log.Printf("⚠️ [Spot1SRecorder] Close error: %v", err)
	} else {
		log.Printf("💾 [Spot1SRecorder] Flushed %d 1-second spot bars to %s", count, filePath)
	}
}

// Close gracefully flushes pending records and stops the background loop.
func (r *Spot1SRecorder) Close() {
	close(r.stopChan)
}

// ConsolidateDailySpot combines all spot part files into a single spot_1s.parquet file.
func ConsolidateDailySpot(baseDir, dateStr string) (string, error) {
	targetDir := filepath.Join(baseDir, "ticks", dateStr)
	targetFile := filepath.Join(targetDir, "spot_1s.parquet")

	partsDir := filepath.Join(baseDir, "ticks", dateStr, "spot_parts")
	matches, err := filepath.Glob(filepath.Join(partsDir, "spot_*.parquet"))
	if err != nil || len(matches) == 0 {
		matches, _ = filepath.Glob(filepath.Join(targetDir, "spot_*.parquet"))
	}
	if len(matches) == 0 {
		if _, statErr := os.Stat(targetFile); statErr == nil {
			return targetFile, nil
		}
		return "", fmt.Errorf("no spot part files found in %s or %s", partsDir, targetDir)
	}

	allRecords := make([]Spot1SRecord, 0)
	for _, f := range matches {
		rows, readErr := parquet_go.ReadFile[Spot1SRecord](f)
		if readErr == nil {
			allRecords = append(allRecords, rows...)
		}
	}

	if len(allRecords) == 0 {
		return "", fmt.Errorf("no valid spot records read from part files")
	}

	// Sort chronologically
	sort.Slice(allRecords, func(i, j int) bool {
		if allRecords[i].Timestamp == allRecords[j].Timestamp {
			return allRecords[i].IndexName < allRecords[j].IndexName
		}
		return allRecords[i].Timestamp < allRecords[j].Timestamp
	})

	file, err := os.OpenFile(targetFile, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, 0644)
	if err != nil {
		return "", fmt.Errorf("failed to create consolidated spot file: %w", err)
	}
	defer file.Close()

	writer := parquet_go.NewGenericWriter[Spot1SRecord](file, parquet_go.Compression(&parquet_go.Snappy))
	if _, err := writer.Write(allRecords); err != nil {
		return "", fmt.Errorf("failed to write consolidated spot records: %w", err)
	}
	if err := writer.Close(); err != nil {
		return "", fmt.Errorf("failed to close consolidated spot writer: %w", err)
	}

	log.Printf("✅ [Spot1SRecorder] Successfully consolidated %d spot records into %s", len(allRecords), targetFile)
	return targetFile, nil
}

// LoadSpotLookup loads 1-second spot close prices for an index into a map: epoch -> closePrice.
func LoadSpotLookup(baseDir, dateStr, indexName string) (map[int64]float64, error) {
	spotMap := make(map[int64]float64)
	spotFile := filepath.Join(baseDir, "ticks", dateStr, "spot_1s.parquet")

	if _, err := os.Stat(spotFile); os.IsNotExist(err) {
		// Attempt consolidation if spot_1s.parquet doesn't exist yet
		var consErr error
		spotFile, consErr = ConsolidateDailySpot(baseDir, dateStr)
		if consErr != nil {
			return spotMap, consErr
		}
	}

	rows, err := parquet_go.ReadFile[Spot1SRecord](spotFile)
	if err != nil {
		return spotMap, fmt.Errorf("failed to read spot parquet: %w", err)
	}

	for _, r := range rows {
		if indexName == "" || r.IndexName == indexName {
			spotMap[r.Timestamp] = r.Close
		}
	}

	log.Printf("📊 [SpotLookup] Loaded %d 1-second spot quotes for %s (%s)", len(spotMap), indexName, dateStr)
	return spotMap, nil
}

// IsIndianMarketHours checks if current time falls within active trading hours (09:14:55 to 15:30:10 IST Mon-Fri).
func IsIndianMarketHours() bool {
	ist, err := time.LoadLocation("Asia/Kolkata")
	if err != nil {
		ist = time.FixedZone("IST", 5*3600+1800)
	}
	now := time.Now().In(ist)
	if now.Weekday() == time.Saturday || now.Weekday() == time.Sunday {
		return false
	}
	h, m, s := now.Clock()
	secOfDay := h*3600 + m*60 + s
	return secOfDay >= (9*3600+14*60+55) && secOfDay <= (15*3600+30*60+10)
}

