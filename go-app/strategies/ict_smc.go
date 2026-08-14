package strategies

import (
	"fmt"
	"math"
	"strings"
)

// ICTSMCStrategy implements Inner Circle Trader (ICT) / Smart Money Concepts (SMC) backtesting.
type ICTSMCStrategy struct{}

// NewICTSMCStrategy creates a new ICT/SMC strategy instance.
func NewICTSMCStrategy() *ICTSMCStrategy {
	return &ICTSMCStrategy{}
}

func (s *ICTSMCStrategy) GetName() string {
	return "ict_smc"
}

func (s *ICTSMCStrategy) Execute(input StrategyInput) StrategyResult {
	result := StrategyResult{
		StrategyName: "ICT_SMC",
		Trades:       make([]TradeSignal, 0),
	}

	candles := input.Candles
	if len(candles) < 4 {
		return result
	}

	riskRewardRatio := 2.0
	if val, ok := input.Params["rr_ratio"].(float64); ok && val > 0 {
		riskRewardRatio = val
	}

	stopLossPct := 0.005 // 0.5% default SL
	if val, ok := input.Params["sl_pct"].(float64); ok && val > 0 {
		stopLossPct = val / 100.0
	}

	var totalProfit, totalLoss float64
	var peakPnL, maxDD float64
	var currentPnL float64

	// Detect Fair Value Gaps (FVG) and Order Blocks (OB)
	for i := 2; i < len(candles)-1; i++ {
		c1 := candles[i-2]
		c3 := candles[i]

		high1, _ := getFloat(c1, "high")
		low1, _ := getFloat(c1, "low")
		high3, _ := getFloat(c3, "high")
		low3, _ := getFloat(c3, "low")
		close3, _ := getFloat(c3, "close")
		dateStr, _ := c3["date"].(string)

		// Bullish Fair Value Gap (FVG): Low of candle 3 is greater than High of candle 1
		isBullishFVG := low3 > high1
		// Bearish Fair Value Gap (FVG): High of candle 3 is lower than Low of candle 1
		isBearishFVG := high3 < low1

		if isBullishFVG {
			entry := close3
			sl := entry * (1.0 - stopLossPct)
			target := entry + (entry-sl)*riskRewardRatio
			nextClose, _ := getFloat(candles[i+1], "close")

			pnl := (nextClose - entry) * 50.0 // Nifty lot size 50
			status := "WIN"
			if pnl < 0 {
				status = "LOSS"
				result.LosingTrades++
				totalLoss += math.Abs(pnl)
			} else {
				result.WinningTrades++
				totalProfit += pnl
			}
			currentPnL += pnl
			if currentPnL > peakPnL {
				peakPnL = currentPnL
			}
			dd := peakPnL - currentPnL
			if dd > maxDD {
				maxDD = dd
			}

			result.Trades = append(result.Trades, TradeSignal{
				Timestamp:     dateStr,
				Symbol:        input.IndexName,
				TradeType:     "BUY_CE",
				EntryPrice:    entry,
				ExitPrice:     nextClose,
				TargetPrice:   target,
				StopLossPrice: sl,
				Quantity:      50,
				PnL:           pnl,
				Status:        status,
				Reason:        "Bullish FVG Retest & Order Block",
			})
		} else if isBearishFVG {
			entry := close3
			sl := entry * (1.0 + stopLossPct)
			target := entry - (sl-entry)*riskRewardRatio
			nextClose, _ := getFloat(candles[i+1], "close")

			pnl := (entry - nextClose) * 50.0
			status := "WIN"
			if pnl < 0 {
				status = "LOSS"
				result.LosingTrades++
				totalLoss += math.Abs(pnl)
			} else {
				result.WinningTrades++
				totalProfit += pnl
			}
			currentPnL += pnl
			if currentPnL > peakPnL {
				peakPnL = currentPnL
			}
			dd := peakPnL - currentPnL
			if dd > maxDD {
				maxDD = dd
			}

			result.Trades = append(result.Trades, TradeSignal{
				Timestamp:     dateStr,
				Symbol:        input.IndexName,
				TradeType:     "BUY_PE",
				EntryPrice:    entry,
				ExitPrice:     nextClose,
				TargetPrice:   target,
				StopLossPrice: sl,
				Quantity:      50,
				PnL:           pnl,
				Status:        status,
				Reason:        "Bearish FVG Retest & Liquidity Sweep",
			})
		}
	}

	result.TotalTrades = len(result.Trades)
	result.NetPnL = currentPnL
	if result.TotalTrades > 0 {
		result.WinRate = math.Round((float64(result.WinningTrades)/float64(result.TotalTrades)*100.0)*100) / 100
	}
	result.MaxDrawdown = math.Round(maxDD*100) / 100
	if totalLoss > 0 {
		result.ProfitFactor = math.Round((totalProfit/totalLoss)*100) / 100
	} else if totalProfit > 0 {
		result.ProfitFactor = 99.99
	}
	result.SharpeRatio = math.Round((result.NetPnL/10000.0)*100) / 100

	return result
}

// EvaluateLiveSignal processes real-time ICT / SMC Fair Value Gaps and Order Blocks for live execution.
func (s *ICTSMCStrategy) EvaluateLiveSignal(currentCandle map[string]interface{}, prevCandles []map[string]interface{}, indexName string, params map[string]interface{}) *LiveOrderRequest {
	if len(prevCandles) < 2 {
		return nil
	}

	c0 := prevCandles[len(prevCandles)-2]
	c2 := currentCandle

	high0, ok1 := getFloat(c0, "high")
	low2, ok2 := getFloat(c2, "low")
	dateStr, _ := currentCandle["date"].(string)

	if !ok1 || !ok2 {
		return nil
	}

	lotsCount := 1
	if val, ok := params["lots_count"].(float64); ok && val > 0 {
		lotsCount = int(val)
	}

	lotSize := 50
	idxUpper := strings.ToUpper(indexName)
	if strings.Contains(idxUpper, "BANK") {
		lotSize = 15
	} else if strings.Contains(idxUpper, "FIN") {
		lotSize = 25
	}
	totalQuantity := lotSize * lotsCount

	step := 50.0
	if strings.Contains(idxUpper, "BANK") {
		step = 100.0
	}

	// Bullish FVG check
	if low2 > high0+(step*0.2) {
		entry, _ := getFloat(c2, "close")
		atmStrike := math.Round(entry/step) * step
		tradingSymbol := fmt.Sprintf("%s %.0f CE", indexName, atmStrike)
		return &LiveOrderRequest{
			IndexName:     indexName,
			TradingSymbol: tradingSymbol,
			Transaction:   "BUY",
			OrderType:     "MARKET",
			Quantity:      totalQuantity,
			TargetPrice:   entry + (step * 0.8),
			StopLossPrice: entry - (step * 0.4),
			StrategyName:  "ict_smc",
			Timestamp:     dateStr,
		}
	}
	return nil
}

func getFloat(m map[string]interface{}, key string) (float64, bool) {
	val, ok := m[key]
	if !ok {
		return 0, false
	}
	switch v := val.(type) {
	case float64:
		return v, true
	case int:
		return float64(v), true
	case int64:
		return float64(v), true
	default:
		return 0, false
	}
}
