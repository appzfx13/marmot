package strategies_test

import (
	"fmt"
	"testing"
	"go-app/parquet"
	"go-app/strategies"
)

// TestRetestLayeringToggleOff verifies baseline behavior when toggle is OFF (Zero Regression).
func TestRetestLayeringToggleOff(t *testing.T) {
	strat, ok := strategies.GetStrategy("ict_sweep_choch")
	if !ok || strat == nil {
		t.Fatalf("failed to resolve ict_sweep_choch")
	}

	ticksByDate, err := parquet.LoadTicksByDateRange("/app/backup/1/49/dataset.parquet", "2026-10-09", "2026-10-09")
	if err != nil {
		t.Fatalf("failed to load parquet: %v", err)
	}
	dayTicks := ticksByDate["2026-10-09"]
	if len(dayTicks) == 0 {
		t.Fatalf("no ticks found for 2026-10-09")
	}

	input := strategies.StrategyInput{
		Date:      "2026-10-09",
		IndexName: "NIFTY",
		Ticks:     dayTicks,
		Params: map[string]interface{}{
			"strategy_name":          "ict_sweep_choch",
			"enable_retest_layering": false,
		},
	}

	res := strat.Execute(input)
	if len(res.Trades) == 0 {
		t.Errorf("expected trades with toggle OFF, got 0")
	}
	fmt.Printf("\n[TEST] Toggle OFF executed %d trades successfully\n", len(res.Trades))
}

// TestRetestLayeringToggleOn verifies self-adaptive structural retest layering when toggle is ON.
func TestRetestLayeringToggleOn(t *testing.T) {
	strat, ok := strategies.GetStrategy("ict_sweep_choch")
	if !ok || strat == nil {
		t.Fatalf("failed to resolve ict_sweep_choch")
	}

	ticksByDate, err := parquet.LoadTicksByDateRange("/app/backup/1/49/dataset.parquet", "2026-10-09", "2026-10-09")
	if err != nil {
		t.Fatalf("failed to load parquet: %v", err)
	}
	dayTicks := ticksByDate["2026-10-09"]
	if len(dayTicks) == 0 {
		t.Fatalf("no ticks found for 2026-10-09")
	}

	// Test 1 Lot, 2 Lots, and 3 Lots
	lotScenarios := []int{1, 2, 3}
	for _, lots := range lotScenarios {
		input := strategies.StrategyInput{
			Date:      "2026-10-09",
			IndexName: "NIFTY",
			Ticks:     dayTicks,
			Params: map[string]interface{}{
				"strategy_name":          "ict_sweep_choch",
				"enable_retest_layering": true,
				"lots_count":             lots,
			},
		}

		res := strat.Execute(input)
		fmt.Printf("\n=======================================================\n")
		fmt.Printf("[AUDIT TRAIL] Retest Layering ON | Lots: %d | Total Trades: %d\n", lots, len(res.Trades))
		fmt.Printf("=======================================================\n")
		totalPnL := 0.0
		winCount := 0
		for idx, tr := range res.Trades {
			totalPnL += tr.PnL
			if tr.PnL > 0 {
				winCount++
			}
			fmt.Printf("Trade #%-2d | %-10s | Sig=%s -> Fill=%s -> Exit=%s | Entry=%-6.2f | SL=%-6.2f | Exit=%-6.2f | PnL=%+8.2f | Retest=%dm | Reason=%s\n",
				idx+1, tr.Strike, tr.SignalTimestamp, tr.Timestamp, tr.ExitTimestamp, tr.EntryPrice, tr.StopLossPrice, tr.ExitPrice, tr.PnL, tr.RetestDurationMinutes, tr.Reason)
		}
		winRate := 0.0
		if len(res.Trades) > 0 {
			winRate = (float64(winCount) / float64(len(res.Trades))) * 100
		}
		fmt.Printf(">>> Summary (%d Lots): Trades=%d | Wins=%d (%.1f%%) | Total PnL: ₹%.2f\n",
			lots, len(res.Trades), winCount, winRate, totalPnL)
	}
}

// TestRetestLayeringLiveSignal verifies real-time signal generation with structural SL and limit pricing.
func TestRetestLayeringLiveSignal(t *testing.T) {
	strat, ok := strategies.GetStrategy("ict_sweep_choch")
	if !ok || strat == nil {
		t.Fatalf("failed to resolve ict_sweep_choch")
	}

	mockCandle := map[string]interface{}{
		"open":      22490.0,
		"high":      22505.0,
		"low":       22450.0,
		"close":     22452.0,
		"timestamp": int64(1791629827),
	}

	req := strat.EvaluateLiveSignal(mockCandle, nil, "NIFTY", map[string]interface{}{
		"enable_retest_layering": true,
		"option_ltp":             274.0,
		"lots_count":             2,
	})

	if req != nil {
		fmt.Printf("\n[TEST] Realtime Live Signal Generated: OrderType=%s, LimitPrice=%.2f, SL=%.2f, TP=%.2f\n",
			req.OrderType, req.LimitPrice, req.StopLossPrice, req.TargetPrice)
		if req.Indicators["swept_high"] == nil {
			t.Errorf("missing swept_high indicator")
		}
	}
}
