package parquet

import (
	"fmt"
	"log"
	"math"
	"sort"
	"strings"

	parquetgo "github.com/parquet-go/parquet-go"

	"go-app/strategies"
)

// optionRow mirrors the flat schema of dataset.parquet.
type optionRow struct {
	Timestamp      int64   `parquet:"timestamp"`
	Datetime       string  `parquet:"datetime"`
	IndexName      string  `parquet:"index_name"`
	InstrumentType string  `parquet:"instrument_type"`
	TradingSymbol  string  `parquet:"trading_symbol"`
	Strike         string  `parquet:"strike"`
	OptionType     string  `parquet:"option_type"`
	Open           float64 `parquet:"open"`
	High           float64 `parquet:"high"`
	Low            float64 `parquet:"low"`
	Close          float64 `parquet:"close"`
	Volume         int64   `parquet:"volume"`
	OI             int64   `parquet:"oi"`
	IV             float64 `parquet:"iv"`
	Delta          float64 `parquet:"delta"`
	Gamma          float64 `parquet:"gamma"`
	Theta          float64 `parquet:"theta"`
	Vega           float64 `parquet:"vega"`
	Bid            float64 `parquet:"bid"`
	Ask            float64 `parquet:"ask"`
	SpotPrice      float64 `parquet:"spot_price"`
}

// tickBucket is an intermediate container used while assembling ticks.
type tickBucket struct {
	timestamp int64
	datetime  string
	indexName string
	// spot data
	spotOpen, spotHigh, spotLow, spotClose float64
	hasSpot                                bool
	// option chain: key = "ATM CALL", "ATM+1 PUT", etc.
	options map[string]strategies.OptionSnap
}

// LoadTicksByDate reads a flat dataset.parquet and returns a map of
// "YYYY-MM-DD" -> []MarketTick (sorted chronologically by timestamp).
// Each MarketTick is a complete minute-level broker feed snapshot.
func LoadTicksByDate(filePath string) (map[string][]strategies.MarketTick, error) {
	rows, err := parquetgo.ReadFile[optionRow](filePath)
	if err != nil {
		return nil, fmt.Errorf("parquet read error: %w", err)
	}

	// Group rows by timestamp into buckets
	buckets := make(map[int64]*tickBucket)
	tsOrder := make([]int64, 0)

	for _, row := range rows {
		ts := row.Timestamp
		bucket, exists := buckets[ts]
		if !exists {
			bucket = &tickBucket{
				timestamp: ts,
				datetime:  row.Datetime,
				indexName: row.IndexName,
				options:   make(map[string]strategies.OptionSnap),
			}
			buckets[ts] = bucket
			tsOrder = append(tsOrder, ts)
		}

		instrUpper := strings.ToUpper(row.InstrumentType)
		optTypeUpper := strings.ToUpper(row.OptionType)

		if instrUpper == "INDEX" {
			// Spot OHLCV — take close from spot_price if close is zero
			cl := row.Close
			if cl <= 0 {
				cl = row.SpotPrice
			}
			op := row.Open
			if op <= 0 {
				op = cl
			}
			hi := row.High
			if hi <= 0 {
				hi = cl
			}
			lo := row.Low
			if lo <= 0 {
				lo = cl
			}
			bucket.spotOpen = op
			bucket.spotHigh = hi
			bucket.spotLow = lo
			bucket.spotClose = cl
			bucket.hasSpot = true
		} else if instrUpper == "OPTION" && (optTypeUpper == "CALL" || optTypeUpper == "PUT") {
			// Option chain entry — key: "{strike} {CALL|PUT}"
			key := row.Strike + " " + optTypeUpper
			cl := row.Close
			if cl <= 0 {
				cl = row.SpotPrice
			}
			op := row.Open
			if op <= 0 {
				op = cl
			}
			hi := row.High
			if hi <= 0 {
				hi = cl
			}
			lo := row.Low
			if lo <= 0 {
				lo = cl
			}
			bucket.options[key] = strategies.OptionSnap{
				TradingSymbol: row.TradingSymbol,
				Open:          op,
				High:          hi,
				Low:           lo,
				Close:         cl,
				Volume:        row.Volume,
				OI:            row.OI,
				IV:            row.IV,
				Delta:         row.Delta,
				Gamma:         row.Gamma,
				Theta:         row.Theta,
				Vega:          row.Vega,
				Bid:           row.Bid,
				Ask:           row.Ask,
			}
		}
	}

	// Sort timestamps chronologically
	sort.Slice(tsOrder, func(i, j int) bool { return tsOrder[i] < tsOrder[j] })

	// Build output: group by date
	byDate := make(map[string][]strategies.MarketTick)
	totalTicks := 0

	for _, ts := range tsOrder {
		b := buckets[ts]
		if !b.hasSpot || b.spotClose <= 0 {
			continue // skip ticks with no valid spot data
		}

		// Automatically create ATM, ATM±N aliases for numeric strikes to ensure all strategies match
		step := strikeStepForIndex(b.indexName)
		if step > 0 {
			atmNum := int(math.Round(b.spotClose/float64(step))) * step
			for _, optType := range []string{"CALL", "PUT"} {
				for offset := -6; offset <= 6; offset++ {
					numStrike := atmNum + (offset * step)
					numKey := fmt.Sprintf("%d %s", numStrike, optType)
					if snap, ok := b.options[numKey]; ok {
						label := "ATM"
						if offset > 0 {
							label = fmt.Sprintf("ATM+%d", offset)
						} else if offset < 0 {
							label = fmt.Sprintf("ATM-%d", -offset)
						}
						relKey := label + " " + optType
						if _, exists := b.options[relKey]; !exists {
							b.options[relKey] = snap
						}
					}
				}
			}
		}

		dateStr := ""
		if len(b.datetime) >= 10 {
			dateStr = b.datetime[:10]
		} else {
			continue
		}

		tick := strategies.MarketTick{
			Timestamp: b.timestamp,
			Datetime:  b.datetime,
			Date:      dateStr,
			IndexName: b.indexName,
			SpotOpen:  b.spotOpen,
			SpotHigh:  b.spotHigh,
			SpotLow:   b.spotLow,
			SpotClose: b.spotClose,
			Options:   b.options,
		}
		byDate[dateStr] = append(byDate[dateStr], tick)
		totalTicks++
	}

	log.Printf("📦 [Parquet] %d ticks | %d trading days | %s", totalTicks, len(byDate), filePath)
	return byDate, nil
}

func strikeStepForIndex(indexName string) int {
	switch strings.ToUpper(indexName) {
	case "BANKNIFTY", "SENSEX", "BANKEX":
		return 100
	case "MIDCPNIFTY":
		return 25
	default:
		return 50
	}
}
