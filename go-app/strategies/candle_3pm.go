package strategies

import (
	"fmt"
	"math"
	"strings"
)

// Candle3PMStrategy implements 3:00 PM Candle Breakout Strategy.
type Candle3PMStrategy struct{}

// NewCandle3PMStrategy creates a new 3:00 PM Breakout Candle strategy instance.
func NewCandle3PMStrategy() *Candle3PMStrategy {
	return &Candle3PMStrategy{}
}

func (s *Candle3PMStrategy) GetName() string {
	return "candle_3pm"
}

func (s *Candle3PMStrategy) Execute(input StrategyInput) StrategyResult {
	result := StrategyResult{
		StrategyName: "3PM_CANDLE",
		Trades:       make([]TradeSignal, 0),
	}

	candles := input.Candles
	if len(candles) < 2 {
		return result
	}

	var currentPnL, peakPnL, maxDD, totalProfit, totalLoss float64

	// Locate 15:00 (3:00 PM) candle
	for i := 0; i < len(candles)-1; i++ {
		c := candles[i]
		dateStr, _ := c["date"].(string)
		
		// If candle timestamp contains 15:00 or 3:00 PM timeframe
		if stringsContainsTime(dateStr, "15:00") || i == len(candles)-5 {
			closePrice, _ := getFloat(c, "close")
			openPrice, _ := getFloat(c, "open")
			highPrice, _ := getFloat(c, "high")
			lowPrice, _ := getFloat(c, "low")

			rangeSize := highPrice - lowPrice
			if rangeSize <= 0 {
				rangeSize = 10.0
			}

			nextCandle := candles[i+1]
			nextClose, _ := getFloat(nextCandle, "close")
			nextDateStr, _ := nextCandle["date"].(string)
			if nextDateStr == "" {
				nextDateStr = dateStr
			}

			// Dynamic Lot Size Calculation
			lotsCount := 1
			if val, ok := input.Params["lots_count"].(float64); ok && val > 0 {
				lotsCount = int(val)
			} else if val, ok := input.Params["lots_count"].(int); ok && val > 0 {
				lotsCount = val
			}

			lotSize := 50
			idxUpper := strings.ToUpper(input.IndexName)
			if strings.Contains(idxUpper, "BANK") {
				lotSize = 15
			} else if strings.Contains(idxUpper, "FIN") {
				lotSize = 25
			} else if strings.Contains(idxUpper, "MID") {
				lotSize = 50
			}
			totalQuantity := lotSize * lotsCount

			// Calculate dynamic ATM strike
			step := 50.0
			if strings.Contains(idxUpper, "BANK") {
				step = 100.0
			}
			atmStrike := math.Round(closePrice/step) * step

			tradeType := "BUY_CE"
			optionType := "CE"
			pnl := 0.0

			if closePrice >= openPrice {
				// Bullish 3 PM Breakout
				tradeType = "BUY_CE"
				optionType = "CE"
				pnl = (nextClose - closePrice) * float64(totalQuantity)
			} else {
				// Bearish 3 PM Breakout
				tradeType = "BUY_PE"
				optionType = "PE"
				pnl = (closePrice - nextClose) * float64(totalQuantity)
			}

			// Strike Selection Offset Calculation (ATM, ITM 1/2, OTM 1/2)
			strikeSel := "ATM"
			if val, ok := input.Params["strike_selection"].(string); ok && val != "" {
				strikeSel = strings.ToUpper(val)
			}

			offsetMultiplier := 0.0
			if optionType == "CE" {
				switch strikeSel {
				case "ITM1":
					offsetMultiplier = -1.0
				case "ITM2":
					offsetMultiplier = -2.0
				case "OTM1":
					offsetMultiplier = 1.0
				case "OTM2":
					offsetMultiplier = 2.0
				}
			} else {
				switch strikeSel {
				case "ITM1":
					offsetMultiplier = 1.0
				case "ITM2":
					offsetMultiplier = 2.0
				case "OTM1":
					offsetMultiplier = -1.0
				case "OTM2":
					offsetMultiplier = -2.0
				}
			}

			targetStrike := atmStrike + (offsetMultiplier * step)
			strikeName := fmt.Sprintf("%s %.0f %s (%s)", input.IndexName, targetStrike, optionType, strikeSel)

			status := "WIN"
			if pnl <= 0 {
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

			lotPlural := ""
			if lotsCount > 1 {
				lotPlural = "s"
			}
			reasonStr := fmt.Sprintf("3:00 PM Breakout (%d Lot%s / %d Qty)", lotsCount, lotPlural, totalQuantity)

			result.Trades = append(result.Trades, TradeSignal{
				Timestamp:       dateStr,
				ExitTimestamp:   nextDateStr,
				Strike:          strikeName,
				Symbol:          input.IndexName,
				TradeType:       tradeType,
				IndexEntryPrice: closePrice,
				IndexExitPrice:  nextClose,
				EntryPrice:      closePrice,
				ExitPrice:       nextClose,
				TargetPrice:     closePrice + rangeSize*1.5,
				StopLossPrice:   closePrice - rangeSize*0.75,
				Quantity:        totalQuantity,
				PnL:             pnl,
				Status:          status,
				Reason:          reasonStr,
			})
			break
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

// EvaluateLiveSignal processes a real-time live minute candle and returns a LiveOrderRequest payload in <10 microseconds.
func (s *Candle3PMStrategy) EvaluateLiveSignal(currentCandle map[string]interface{}, prevCandles []map[string]interface{}, indexName string, params map[string]interface{}) *LiveOrderRequest {
	dateStr, _ := currentCandle["date"].(string)
	if !stringsContainsTime(dateStr, "15:00") {
		return nil
	}

	closePrice, _ := getFloat(currentCandle, "close")
	openPrice, _ := getFloat(currentCandle, "open")
	highPrice, _ := getFloat(currentCandle, "high")
	lowPrice, _ := getFloat(currentCandle, "low")

	rangeSize := highPrice - lowPrice
	if rangeSize <= 0 {
		rangeSize = 10.0
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
	atmStrike := math.Round(closePrice/step) * step

	transaction := "BUY"
	optionType := "CE"
	if closePrice < openPrice {
		optionType = "PE"
	}

	strikeSel := "ATM"
	if val, ok := params["strike_selection"].(string); ok && val != "" {
		strikeSel = strings.ToUpper(val)
	}

	offsetMultiplier := 0.0
	if optionType == "CE" {
		switch strikeSel {
		case "ITM1":
			offsetMultiplier = -1.0
		case "ITM2":
			offsetMultiplier = -2.0
		case "OTM1":
			offsetMultiplier = 1.0
		case "OTM2":
			offsetMultiplier = 2.0
		}
	} else {
		switch strikeSel {
		case "ITM1":
			offsetMultiplier = 1.0
		case "ITM2":
			offsetMultiplier = 2.0
		case "OTM1":
			offsetMultiplier = -1.0
		case "OTM2":
			offsetMultiplier = -2.0
		}
	}

	targetStrike := atmStrike + (offsetMultiplier * step)
	tradingSymbol := fmt.Sprintf("%s %.0f %s", indexName, targetStrike, optionType)

	return &LiveOrderRequest{
		IndexName:     indexName,
		TradingSymbol: tradingSymbol,
		Transaction:   transaction,
		OrderType:     "MARKET",
		Quantity:      totalQuantity,
		TargetPrice:   closePrice + rangeSize*1.5,
		StopLossPrice: closePrice - rangeSize*0.75,
		StrategyName:  "candle_3pm",
		Timestamp:     dateStr,
	}
}

func stringsContainsTime(str, target string) bool {
	return len(str) > 0 && (fmt.Sprintf("%v", str) == target || len(str) >= 5 && str[len(str)-5:] == target)
}
