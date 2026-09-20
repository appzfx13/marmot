package parquet

import (
	"testing"
)

func TestLoadTicksByDateWithGreeks(t *testing.T) {
	filePath := "/app/backup/1/1/dataset.parquet"
	ticksByDate, err := LoadTicksByDate(filePath)
	if err != nil {
		t.Fatalf("Failed to load dataset: %v", err)
	}

	if len(ticksByDate) == 0 {
		t.Fatalf("Expected ticks from dataset, got 0")
	}

	foundGreeksCount := 0
	for dateStr, ticks := range ticksByDate {
		t.Logf("Date %s: %d ticks", dateStr, len(ticks))
		if len(ticks) == 0 {
			t.Errorf("No ticks for date %s", dateStr)
			continue
		}

		sampleTick := ticks[len(ticks)/2]
		t.Logf("Sample Tick at %s | SpotClose: %.2f | Options count: %d",
			sampleTick.Datetime, sampleTick.SpotClose, len(sampleTick.Options))

		// Check ATM CALL if present
		if atmCall, ok := sampleTick.Options["ATM CALL"]; ok {
			t.Logf("  ATM CALL: Symbol=%s Close=%.2f IV=%.2f%% Delta=%.3f Gamma=%.5f Theta=%.2f Vega=%.2f Bid=%.2f Ask=%.2f",
				atmCall.TradingSymbol, atmCall.Close, atmCall.IV, atmCall.Delta, atmCall.Gamma, atmCall.Theta, atmCall.Vega, atmCall.Bid, atmCall.Ask)
			if atmCall.Delta <= 0 || atmCall.Delta >= 1 {
				t.Errorf("Unexpected Delta for CALL: %v", atmCall.Delta)
			}
			if atmCall.IV <= 0 {
				t.Errorf("Expected positive IV for ATM CALL, got %v", atmCall.IV)
			}
			foundGreeksCount++
		}

		// Check ATM PUT if present
		if atmPut, ok := sampleTick.Options["ATM PUT"]; ok {
			t.Logf("  ATM PUT: Symbol=%s Close=%.2f IV=%.2f%% Delta=%.3f Gamma=%.5f Theta=%.2f Vega=%.2f Bid=%.2f Ask=%.2f",
				atmPut.TradingSymbol, atmPut.Close, atmPut.IV, atmPut.Delta, atmPut.Gamma, atmPut.Theta, atmPut.Vega, atmPut.Bid, atmPut.Ask)
			if atmPut.Delta >= 0 || atmPut.Delta <= -1 {
				t.Errorf("Unexpected Delta for PUT: %v", atmPut.Delta)
			}
			foundGreeksCount++
		}
	}

	if foundGreeksCount == 0 {
		t.Fatalf("Expected at least one day with verified ATM Greeks, got 0")
	}
}
