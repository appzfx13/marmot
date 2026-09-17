package parquet

import (
	"fmt"
	"log"
	"os"
	"path/filepath"
	"sync"
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
// The caller must hold the mutex.
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
