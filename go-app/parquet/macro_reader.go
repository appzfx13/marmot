package parquet

import (
	"fmt"
	"log"
	"strings"

	parquetgo "github.com/parquet-go/parquet-go"
	"go-app/strategies"
)

// MacroRow mirrors the parquet schema of macro_1h_<INDEX>.parquet
type MacroRow struct {
	Timestamp            string  `parquet:"timestamp"`
	Datetime             string  `parquet:"datetime"`
	TimestampUnix        int64   `parquet:"timestamp_unix"`
	SessionDate          string  `parquet:"session_date"`
	MacroSentimentScore  float64 `parquet:"macro_sentiment_score"`
	FIIDIIFlowBias       float64 `parquet:"fii_dii_flow_bias"`
	RateRegimeBias       float64 `parquet:"rate_regime_bias"`
	GlobalRiskSentiment  float64 `parquet:"global_risk_sentiment"`
	EventRiskFlag        int64   `parquet:"event_risk_flag"`
	VolatilityRegimeBias float64 `parquet:"volatility_regime_bias"`
	MacroSummary         string  `parquet:"macro_summary"`
}

// LoadMacroSnapshots reads a macro parquet dataset and returns maps indexed by "YYYY-MM-DD HH" and "YYYY-MM-DD".
func LoadMacroSnapshots(filePath string) (map[string]strategies.MacroSnapshot, map[string]strategies.MacroSnapshot, error) {
	rows, err := parquetgo.ReadFile[MacroRow](filePath)
	if err != nil {
		return nil, nil, fmt.Errorf("macro parquet read error: %w", err)
	}

	hourlyMap := make(map[string]strategies.MacroSnapshot)
	dailyMap := make(map[string]strategies.MacroSnapshot)

	for _, r := range rows {
		snap := strategies.MacroSnapshot{
			SentimentScore:  r.MacroSentimentScore,
			FIIDIIFlowBias:  r.FIIDIIFlowBias,
			GlobalRisk:      r.GlobalRiskSentiment,
			EventRiskFlag:   r.EventRiskFlag > 0,
			MacroSummary:    r.MacroSummary,
		}

		dt := strings.Replace(r.Datetime, "T", " ", 1)
		if dt == "" {
			dt = strings.Replace(r.Timestamp, "T", " ", 1)
		}

		// Store by date "YYYY-MM-DD"
		dateKey := r.SessionDate
		if dateKey == "" && len(dt) >= 10 {
			dateKey = dt[:10]
		}
		if dateKey != "" {
			dailyMap[dateKey] = snap
		}

		// Store by hour "YYYY-MM-DD HH"
		if len(dt) >= 13 {
			hourKey := dt[:13]
			hourlyMap[hourKey] = snap
		}
	}

	log.Printf("🧠 [Macro Parquet] Loaded %d hourly macro snapshots from %s", len(rows), filePath)
	return hourlyMap, dailyMap, nil
}
