package parquet

import (
	"fmt"
	"log"
	"os"
	"strings"
	"time"

	parquetgo "github.com/parquet-go/parquet-go"
)

// VixRecord covers both 15m/1m VIX candles (time, close) and dataset format (timestamp, datetime, close, spot_price).
type VixRecord struct {
	Time      int64   `parquet:"time,omitempty"`
	Timestamp int64   `parquet:"timestamp,omitempty"`
	Datetime  string  `parquet:"datetime,omitempty"`
	Open      float64 `parquet:"open,omitempty"`
	High      float64 `parquet:"high,omitempty"`
	Low       float64 `parquet:"low,omitempty"`
	Close     float64 `parquet:"close,omitempty"`
	SpotPrice float64 `parquet:"spot_price,omitempty"`
}

// LoadVixSnapshots reads a VIX parquet file and returns:
// 1. minuteMap: indexed by "YYYY-MM-DD HH:MM" (and "YYYY-MM-DD HH")
// 2. dailyMap: indexed by "YYYY-MM-DD"
func LoadVixSnapshots(filePath string) (map[string]float64, map[string]float64, error) {
	file, err := os.Open(filePath)
	if err != nil {
		return nil, nil, fmt.Errorf("vix parquet open error: %w", err)
	}
	defer file.Close()

	stat, err := file.Stat()
	if err != nil {
		return nil, nil, fmt.Errorf("vix parquet stat error: %w", err)
	}

	pf, err := parquetgo.OpenFile(file, stat.Size())
	if err != nil {
		return nil, nil, fmt.Errorf("vix parquet parse error: %w", err)
	}

	ist, _ := time.LoadLocation("Asia/Kolkata")
	if ist == nil {
		ist = time.FixedZone("IST", 19800) // UTC + 5:30
	}

	minuteMap := make(map[string]float64)
	dailyMap := make(map[string]float64)

	reader := parquetgo.NewGenericReader[VixRecord](pf)
	defer reader.Close()

	buf := make([]VixRecord, 2048)
	totalLoaded := 0

	for {
		n, rErr := reader.Read(buf)
		for i := 0; i < n; i++ {
			row := &buf[i]
			val := row.Close
			if val <= 0 {
				val = row.SpotPrice
			}
			if val <= 0 {
				val = row.Open
			}
			if val <= 0 {
				continue
			}

			// Determine datetime string
			dtStr := strings.TrimSpace(row.Datetime)
			if dtStr == "" {
				ts := row.Timestamp
				if ts <= 0 {
					ts = row.Time
				}
				if ts > 0 {
					// Handle unix millis vs seconds
					if ts > 100000000000 {
						ts = ts / 1000
					}
					t := time.Unix(ts, 0).In(ist)
					dtStr = t.Format("2006-01-02 15:04:05")
				}
			}

			dtStr = strings.Replace(dtStr, "T", " ", 1)
			if len(dtStr) >= 10 {
				dateKey := dtStr[:10]
				dailyMap[dateKey] = val // latest close of the day
			}
			if len(dtStr) >= 13 {
				hourKey := dtStr[:13]
				minuteMap[hourKey] = val
			}
			if len(dtStr) >= 16 {
				minKey := dtStr[:16]
				minuteMap[minKey] = val
			}
			totalLoaded++
		}

		if rErr != nil {
			break
		}
	}

	log.Printf("📊 [VIX Parquet] Loaded %d VIX records across %d days from %s", totalLoaded, len(dailyMap), filePath)
	return minuteMap, dailyMap, nil
}
