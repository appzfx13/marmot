package strategies_test

import (
	"fmt"
	"testing"
	"go-app/parquet"
	"go-app/strategies"
)

func TestICTSweepCHoCHRealParquet(t *testing.T) {
	dates := []string{"2026-10-08", "2026-10-09"}
	for _, dt := range dates {
		ticksByDate, err := parquet.LoadTicksByDateRange("/app/backup/1/49/dataset.parquet", dt, dt)
		if err != nil {
			t.Fatalf("failed to load parquet: %v", err)
		}
		dayTicks := ticksByDate[dt]
		if len(dayTicks) == 0 {
			continue
		}
		fmt.Printf("\n=== Testing %s (%d ticks) [%s -> %s] ===\n", dt, len(dayTicks), dayTicks[0].Datetime, dayTicks[len(dayTicks)-1].Datetime)
		if len(dayTicks) > 100 {
			optKeys := make([]string, 0)
			for k := range dayTicks[100].Options {
				optKeys = append(optKeys, k)
			}
			fmt.Printf("All Option Keys in Parquet (%d keys): %v\n", len(optKeys), optKeys)
		}

		strat, ok := strategies.GetStrategy("ict_sweep_choch")
		if !ok || strat == nil {
			t.Fatalf("failed to resolve ict_sweep_choch")
		}

		input := strategies.StrategyInput{
			Date:      dt,
			IndexName: "NIFTY",
			Ticks:     dayTicks,
			Params: map[string]interface{}{
				"strategy_name": "ict_sweep_choch",
			},
		}

		res := strat.Execute(input)
		fmt.Printf("Real Parquet Trades Executed for %s: %d\n", dt, len(res.Trades))
		if len(res.Trades) == 0 {
			t.Errorf("expected trades for %s, got 0", dt)
		}
		for idx, tr := range res.Trades {
			fmt.Printf("Trade #%d: Strike=%s | Signal=%s -> Entry=%s -> Exit=%s | Entry=%.2f | Exit=%.2f | PnL=%.2f | RetestDur=%d | Reason=%s\n",
				idx+1, tr.Strike, tr.SignalTimestamp, tr.Timestamp, tr.ExitTimestamp, tr.EntryPrice, tr.ExitPrice, tr.PnL, tr.RetestDurationMinutes, tr.Reason)
			if tr.SignalTimestamp == "" {
				t.Errorf("trade #%d missing SignalTimestamp", idx+1)
			}
		}
	}
}
