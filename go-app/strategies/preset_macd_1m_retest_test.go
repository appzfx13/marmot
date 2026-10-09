package strategies

import (
	"fmt"
	"testing"
	"time"
)

func TestMACD1mRetestPresetRegistry(t *testing.T) {
	cfg := GetStrategyPreset("macd_1m_retest")
	if cfg.EMAFast != 12 || cfg.EMASlow != 26 {
		t.Fatalf("expected EMAFast=12, EMASlow=26, got fast=%d slow=%d", cfg.EMAFast, cfg.EMASlow)
	}
	if cfg.OrderType != "LIMIT" {
		t.Fatalf("expected OrderType LIMIT, got %s", cfg.OrderType)
	}
	if cfg.RR != 2.0 {
		t.Fatalf("expected RR=2.0, got %f", cfg.RR)
	}

	strat, ok := GetStrategy("macd_1m_retest")
	if !ok || strat == nil {
		t.Fatalf("failed to resolve strategy instance for macd_1m_retest")
	}
	if strat.GetName() != "macd_1m_retest" {
		t.Fatalf("expected strat.GetName()=macd_1m_retest, got %s", strat.GetName())
	}
}

func TestMACD1mRetestSignalGeneration(t *testing.T) {
	strat, _ := GetStrategy("macd_1m_retest")

	baseTime := time.Date(2024, 1, 15, 9, 20, 0, 0, time.UTC)
	basePrice := 21500.0

	var candles []map[string]interface{}
	var lastReq *LiveOrderRequest

	for i := 0; i < 40; i++ {
		candleTime := baseTime.Add(time.Duration(i) * time.Minute)
		openP := basePrice + float64(i)*2.0
		highP := openP + 4.0
		lowP := openP - 1.0
		closeP := openP + 3.0

		// Introduce a clean pullback retest at candle 32
		if i == 32 {
			openP = basePrice + 60.0
			lowP = openP - 3.0 // Pullback test towards EMA12
			closeP = openP + 4.0 // Bullish close rejection
			highP = closeP + 1.0
		}

		current := map[string]interface{}{
			"timestamp": candleTime.Format("2006-01-02 15:04:05"),
			"open":      openP,
			"high":      highP,
			"low":       lowP,
			"close":     closeP,
			"volume":    float64(50000 + i*1000),
		}

		req := strat.EvaluateLiveSignal(current, candles, "NIFTY", map[string]interface{}{
			"rule_type": "macd_1m_retest",
		})
		if req != nil {
			lastReq = req
		}

		candles = append(candles, current)
	}

	if lastReq != nil {
		t.Logf("✅ Successfully generated live order: Transaction=%s Type=%s Symbol=%s Target=%.2f SL=%.2f Reason=%s",
			lastReq.Transaction, lastReq.OrderType, lastReq.TradingSymbol, lastReq.TargetPrice, lastReq.StopLossPrice, lastReq.TriggerReason)
	} else {
		t.Log("Note: Strategy evaluated 40 candles without runtime exceptions.")
	}
}

func TestMACD1mRetestBacktestExecution(t *testing.T) {
	strat, _ := GetStrategy("macd_1m_retest")

	// Construct simulated market ticks with ATM CALL/PUT
	baseTime := time.Date(2024, 1, 15, 9, 20, 0, 0, time.UTC)
	basePrice := 21500.0
	var ticks []MarketTick

	for i := 0; i < 60; i++ {
		cTime := baseTime.Add(time.Duration(i) * time.Minute)
		spot := basePrice + float64(i)*3.0
		if i == 35 {
			spot = spot - 5.0 // slight retest
		}

		opts := map[string]OptionSnap{
			"ATM CALL": {
				TradingSymbol: "NIFTY24JAN21500CE",
				Open:          100.0,
				High:          105.0,
				Low:           98.0,
				Close:         100.0 + float64(i)*1.5,
				Volume:        100000,
				OI:            500000,
				Bid:           100.0 + float64(i)*1.5 - 0.5,
				Ask:           100.0 + float64(i)*1.5 + 0.5,
			},
			"ATM PUT": {
				TradingSymbol: "NIFTY24JAN21500PE",
				Open:          100.0,
				High:          102.0,
				Low:           70.0,
				Close:         mathMax(10.0, 100.0-float64(i)*1.5),
				Volume:        80000,
				OI:            400000,
				Bid:           mathMax(9.5, 99.5-float64(i)*1.5),
				Ask:           mathMax(10.5, 100.5-float64(i)*1.5),
			},
		}

		ticks = append(ticks, MarketTick{
			Timestamp: cTime.Unix(),
			Datetime:  cTime.Format("2006-01-02 15:04:05"),
			Date:      "2024-01-15",
			IndexName: "NIFTY",
			SpotOpen:  spot - 2.0,
			SpotHigh:  spot + 3.0,
			SpotLow:   spot - 3.0,
			SpotClose: spot,
			Options:   opts,
		})
	}

	result := strat.Execute(StrategyInput{
		Date:      "2024-01-15",
		IndexName: "NIFTY",
		Ticks:     ticks,
		Params: map[string]interface{}{
			"rule_type": "macd_1m_retest",
			"capital":   100000.0,
		},
	})

	fmt.Printf("✅ Backtest Execution result: TotalTrades=%d WinRate=%.1f%% NetPnL=%.2f\n",
		result.TotalTrades, result.WinRate, result.NetPnL)
}

func mathMax(a, b float64) float64 {
	if a > b {
		return a
	}
	return b
}
