package strategies

import (
	"fmt"
	"math"
	"strconv"
	"strings"
	"sync"
	"time"
)

// QuantEngineStrategy implements the Strategy interface for Marmot's native Go quantitative rule engine.
type QuantEngineStrategy struct {
	mu             sync.Mutex
	name           string
	lastSignalTime time.Time
	candleBuffer   []map[string]interface{}
	orbHigh        float64
	orbLow         float64
	orbDiscovered  bool
	currentBarKey  string
	runningOpen    float64
	runningHigh    float64
	runningLow     float64
	runningClose   float64
	runningVolume  int64
}

// NewQuantEngineStrategy creates a new QuantEngineStrategy instance.
func NewQuantEngineStrategy(name string) *QuantEngineStrategy {
	if name == "" {
		name = "quant_engine"
	}
	return &QuantEngineStrategy{
		name:         name,
		candleBuffer: make([]map[string]interface{}, 0, 50),
		orbHigh:      0,
		orbLow:       0,
	}
}

var istLocation = time.FixedZone("IST", 5*3600+1800)

// nowIST returns current time in Indian Standard Time (Asia/Kolkata).
func nowIST() time.Time {
	return time.Now().In(istLocation)
}

// GetName returns the strategy identifier.
func (s *QuantEngineStrategy) GetName() string {
	if s.name != "" {
		return s.name
	}
	return "quant_engine"
}

// Execute processes a broker-feed tick stream for leak-proof quantitative backtesting.
// Signal entry is determined by spot OHLCV; all SL/TP/exit logic uses option premium prices.
func (s *QuantEngineStrategy) Execute(input StrategyInput) StrategyResult {
	trades := make([]TradeSignal, 0)

	ticks := input.Ticks
	if len(ticks) < 5 {
		return StrategyResult{
			StrategyName: s.GetName(),
			Trades:       trades,
		}
	}

	// Local stateless engine per day — ensures no cross-day ORB/EMA contamination
	localEngine := NewQuantEngineStrategy(s.GetName())

	// Trailing Stop Loss parameter parsing (user-configured overrides have ultimate precedence)
	enableTrailingSL := true
	trailingTriggerR := 1.2
	if input.Params != nil {
		if val, exists := input.Params["enable_trailing_sl"]; exists {
			switch v := val.(type) {
			case bool:
				enableTrailingSL = v
			case string:
				enableTrailingSL = strings.EqualFold(v, "true") || v == "1" || strings.EqualFold(v, "on")
			case float64:
				enableTrailingSL = v != 0
			case int:
				enableTrailingSL = v != 0
			}
		} else if val, exists := input.Params["trail_breakeven"]; exists {
			switch v := val.(type) {
			case bool:
				enableTrailingSL = v
			case string:
				enableTrailingSL = strings.EqualFold(v, "true") || v == "1" || strings.EqualFold(v, "on")
			case float64:
				enableTrailingSL = v != 0
			case int:
				enableTrailingSL = v != 0
			}
		}

		if val, exists := input.Params["trailing_sl_trigger_r"]; exists {
			switch v := val.(type) {
			case float64:
				if v > 0 {
					trailingTriggerR = v
				}
			case int:
				if v > 0 {
					trailingTriggerR = float64(v)
				}
			case string:
				if f, err := strconv.ParseFloat(v, 64); err == nil && f > 0 {
					trailingTriggerR = f
				}
			}
		} else if val, exists := input.Params["breakeven_at_r"]; exists {
			switch v := val.(type) {
			case float64:
				if v > 0 {
					trailingTriggerR = v
				}
			case int:
				if v > 0 {
					trailingTriggerR = float64(v)
				}
			case string:
				if f, err := strconv.ParseFloat(v, 64); err == nil && f > 0 {
					trailingTriggerR = f
				}
			}
		}
	}

	// Retest Layering execution parameters
	enableRetestLayering := false
	layerCount := 3
	retestPercentages := []float64{25.0, 50.0, 75.0}
	layerLots := []int{1, 1, 1}

	if input.Params != nil {
		if val, exists := input.Params["enable_retest_layering"]; exists {
			switch v := val.(type) {
			case bool:
				enableRetestLayering = v
			case string:
				enableRetestLayering = (strings.EqualFold(v, "true") || v == "1" || strings.EqualFold(v, "on"))
			}
		}
		if val, exists := input.Params["layer_count"]; exists {
			switch v := val.(type) {
			case int:
				if v >= 1 { layerCount = v }
			case float64:
				if v >= 1 { layerCount = int(v) }
			}
		}
		if val, exists := input.Params["retest_percentages"]; exists {
			if arr, ok := val.([]interface{}); ok && len(arr) > 0 {
				var pcts []float64
				for _, item := range arr {
					if f, ok := item.(float64); ok {
						pcts = append(pcts, f)
					} else if n, ok := item.(int); ok {
						pcts = append(pcts, float64(n))
					}
				}
				if len(pcts) > 0 {
					retestPercentages = pcts
				}
			} else if farr, ok := val.([]float64); ok && len(farr) > 0 {
				retestPercentages = farr
			}
		}
		if val, exists := input.Params["layer_lots"]; exists {
			if arr, ok := val.([]interface{}); ok && len(arr) > 0 {
				var lots []int
				for _, item := range arr {
					if n, ok := item.(int); ok && n >= 1 {
						lots = append(lots, n)
					} else if f, ok := item.(float64); ok && f >= 1 {
						lots = append(lots, int(f))
					}
				}
				if len(lots) > 0 {
					layerLots = lots
				}
			} else if iarr, ok := val.([]int); ok && len(iarr) > 0 {
				layerLots = iarr
			}
		}
	}

	type pendingLayer struct {
		LimitPrice float64
		Quantity   int
		Filled     bool
	}
	var activeLayers []pendingLayer
	filledCost := 0.0
	filledQty := 0
	activeSlPts := 15.0
	activeRRRatio := 2.0

	var activeTrade *TradeSignal
	activeStrikeKey := "" // e.g. "ATM CALL" or "ATM+1 PUT"

	for i, tick := range ticks {
		// ── Build spot candle for signal evaluation ──────────────────────────
		spotCandle := map[string]interface{}{
			"datetime":  tick.Datetime,
			"timestamp": tick.Timestamp,
			"open":      tick.SpotOpen,
			"high":      tick.SpotHigh,
			"low":       tick.SpotLow,
			"close":     tick.SpotClose,
		}

		// ── 1. Manage active position using OPTION PREMIUM prices ─────────────
		if activeTrade != nil {
			optSnap, hasOpt := tick.Options[activeStrikeKey]

			// Fallback: hold at last known premium if option row missing for this tick
			optLow := activeTrade.EntryPrice
			optHigh := activeTrade.EntryPrice
			optClose := activeTrade.EntryPrice
			if hasOpt && optSnap.Close > 0 {
				optLow = optSnap.Low
				optHigh = optSnap.High
				optClose = optSnap.Close
			}

			// Fill any pending limit layers during option pullback before checking exit
			if enableRetestLayering && len(activeLayers) > 0 {
				newFill := false
				for lIdx := range activeLayers {
					if !activeLayers[lIdx].Filled && optLow <= activeLayers[lIdx].LimitPrice {
						activeLayers[lIdx].Filled = true
						filledQty += activeLayers[lIdx].Quantity
						filledCost += activeLayers[lIdx].LimitPrice * float64(activeLayers[lIdx].Quantity)
						newFill = true
					}
				}
				if newFill && filledQty > 0 {
					avgPrice := math.Round((filledCost/float64(filledQty))*100) / 100
					activeTrade.EntryPrice = avgPrice
					activeTrade.Quantity = filledQty
					activeTrade.UtilizedCapital = math.Round(filledCost)
					activeTrade.TargetPrice = math.Round((avgPrice+activeSlPts*activeRRRatio)*100) / 100
					activeTrade.StopLossPrice = math.Round((avgPrice-activeSlPts)*100) / 100
					if activeTrade.StopLossPrice < 0.5 {
						activeTrade.StopLossPrice = 0.5
					}
					activeTrade.InitialTargetPrice = activeTrade.TargetPrice
					activeTrade.InitialStopLossPrice = activeTrade.StopLossPrice
					activeTrade.TrailingStopLossPrice = activeTrade.StopLossPrice
				}
			}

			isClosed := false
			exitOptPrice := optClose
			exitSpotPrice := tick.SpotClose
			status := "WIN"
			exitReason := "TARGET_HIT"

			// Trailing stop loss to breakeven once option reaches +trailingTriggerR gain (if enabled)
			if enableTrailingSL {
				initialRisk := activeTrade.EntryPrice - activeTrade.InitialStopLossPrice
				if initialRisk > 0 && optHigh >= activeTrade.EntryPrice+(initialRisk*trailingTriggerR) {
					trailedPrice := activeTrade.EntryPrice + 1.0 // Lock in entry + slippage buffer
					if activeTrade.StopLossPrice < trailedPrice {
						activeTrade.StopLossPrice = trailedPrice
						activeTrade.TrailingStopLossPrice = trailedPrice
					}
				}
			}

			// All SL/TP decisions are on option premium — strictly no spot reference
			if optLow <= activeTrade.StopLossPrice {
				exitOptPrice = activeTrade.StopLossPrice
				if exitOptPrice >= activeTrade.EntryPrice {
					status = "WIN"
					exitReason = "TRAILING_SL_HIT"
				} else {
					status = "LOSS"
					exitReason = "STOP_LOSS_HIT"
				}
				isClosed = true
			} else if optHigh >= activeTrade.TargetPrice {
				exitOptPrice = activeTrade.TargetPrice
				status = "WIN"
				exitReason = "TARGET_HIT"
				isClosed = true
			}

			// EOD square-off at last tick of the day
			if !isClosed && i == len(ticks)-1 {
				exitOptPrice = optClose
				if exitOptPrice >= activeTrade.EntryPrice {
					status = "WIN"
				} else {
					status = "LOSS"
				}
				exitReason = "EOD_SQUAREOFF"
				isClosed = true
			}

			if isClosed {
				activeLayers = nil
				activeTrade.ExitPrice = math.Round(exitOptPrice*100) / 100
				activeTrade.IndexExitPrice = exitSpotPrice
				activeTrade.ExitTimestamp = tick.Datetime
				activeTrade.Status = status
				activeTrade.ExitReason = exitReason
				activeTrade.PnL = math.Round((activeTrade.ExitPrice-activeTrade.EntryPrice)*float64(activeTrade.Quantity)*100) / 100
				trades = append(trades, *activeTrade)
				activeTrade = nil
				activeStrikeKey = ""

				exitTime := time.Unix(tick.Timestamp, 0).In(istLocation)
				if len(tick.Datetime) >= 19 {
					if pt, err := time.ParseInLocation("2006-01-02 15:04:05", tick.Datetime[:19], istLocation); err == nil {
						exitTime = pt
					}
				}
				localEngine.lastSignalTime = exitTime
			}
			continue
		}

		// ── 2. Evaluate entry signal on spot candle ───────────────────────────
		sig := localEngine.EvaluateLiveSignal(spotCandle, nil, input.IndexName, input.Params)
		if sig == nil {
			continue
		}

		// Determine option type from signal (checks explicit OptionType, TradingSymbol, and triggerReason)
		optionType := sig.OptionType
		if optionType == "" {
			upperSymbol := strings.ToUpper(sig.TradingSymbol)
			lowerReason := strings.ToLower(sig.TriggerReason)
			if strings.Contains(upperSymbol, "PUT") ||
				strings.HasSuffix(upperSymbol, "PE") ||
				strings.Contains(upperSymbol, " PE") ||
				strings.Contains(lowerReason, "bear") ||
				strings.Contains(lowerReason, "put") {
				optionType = "PUT"
			} else {
				optionType = "CALL"
			}
		}

		// ── 2b. AI Macro Assist Directional Filter ────────────────────────────
		macroTag := ""
		if tick.Macro != nil {
			// Skip trades conflicting strongly with institutional / sentiment bias:
			// If Macro is Bearish (score < -0.15 or FII/DII flow < -0.20), block CALL entries
			if optionType == "CALL" && (tick.Macro.SentimentScore < -0.15 || tick.Macro.FIIDIIFlowBias < -0.20) {
				continue // Blocked by Bearish AI Macro
			}
			// If Macro is Bullish (score > +0.15 or FII/DII flow > +0.20), block PUT entries
			if optionType == "PUT" && (tick.Macro.SentimentScore > 0.15 || tick.Macro.FIIDIIFlowBias > 0.20) {
				continue // Blocked by Bullish AI Macro
			}
			macroTag = fmt.Sprintf(" [Macro: Sent=%.2f, Flow=%.2f]", tick.Macro.SentimentScore, tick.Macro.FIIDIIFlowBias)
		}

		// Strike step resolution
		strikeStep := 50
		if input.Params != nil {
			if step, ok := input.Params["strike_step"].(float64); ok && step > 0 {
				strikeStep = int(step)
			} else if stepInt, ok := input.Params["strike_step"].(int); ok && stepInt > 0 {
				strikeStep = stepInt
			}
		}
		if strikeStep <= 0 {
			if strings.EqualFold(input.IndexName, "BANKNIFTY") || strings.EqualFold(input.IndexName, "SENSEX") {
				strikeStep = 100
			} else if strings.EqualFold(input.IndexName, "MIDCPNIFTY") {
				strikeStep = 25
			} else {
				strikeStep = 50
			}
		}

		// Calculate ATM strike dynamically from current Spot Close
		atmNum := int(math.Round(tick.SpotClose/float64(strikeStep))) * strikeStep
		concreteStrike := fmt.Sprintf("%d %s", atmNum, optionType)
		entryOptPrice := 0.0

		// Strike sweep: score ATM±3 strikes and pick the best entry candidate
		bestStrike := SweepStrikesForBestEntry(tick.Options, atmNum, optionType, strikeStep, input.IndexName, "")
		if bestStrike != nil && bestStrike.LimitPrice > 0 {
			concreteStrike = bestStrike.Key
			entryOptPrice = bestStrike.LimitPrice
		} else {
			// Fallback: original ATM priority chain
			if snap, ok := tick.Options[concreteStrike]; ok && snap.Close > 0 {
				entryOptPrice = snap.Close
			} else if snap, ok := tick.Options["ATM "+optionType]; ok && snap.Close > 0 {
				entryOptPrice = snap.Close
			} else {
				for _, off := range []int{1, -1, 2, -2} {
					candidate := fmt.Sprintf("%d %s", atmNum+(off*strikeStep), optionType)
					if snap, ok := tick.Options[candidate]; ok && snap.Close > 0 {
						concreteStrike = candidate
						entryOptPrice = snap.Close
						break
					}
				}
				// Nearest strike fallback if exact ATM offsets are absent in dataset
				if entryOptPrice <= 0 {
					for optKey, snap := range tick.Options {
						if snap.Close > 0 && strings.Contains(strings.ToUpper(optKey), optionType) {
							concreteStrike = optKey
							entryOptPrice = snap.Close
							break
						}
					}
				}
			}
		}

		if entryOptPrice <= 0 {
			continue // No valid option premium for entry — skip tick
		}

		// Load strategy preset dynamically (from s.GetName() or params["strategy_name"] or params["rules"])
		presetKey := "momentum_scalp"
		if s.GetName() != "" && s.GetName() != "quant_engine" {
			presetKey = s.GetName()
		}
		if input.Params != nil {
			if stratName, ok := input.Params["strategy_name"].(string); ok && stratName != "" {
				presetKey = strings.ToLower(strings.TrimSpace(stratName))
			}
			if s.GetName() == "" || s.GetName() == "quant_engine" {
				if rawRules, ok := input.Params["rules"].([]interface{}); ok && len(rawRules) > 0 {
					if rMap, isMap := rawRules[0].(map[string]interface{}); isMap {
						ruleType := strings.ToLower(fmt.Sprintf("%v", rMap["rule_type"]))
						if ruleType != "" && ruleType != "<nil>" {
							presetKey = ruleType
						}
					}
				}
			}
		}
		preset := GetStrategyPreset(presetKey)

		// SL/TP in option premium points with dynamic default based on preset and index
		slPts := preset.SLPts
		if slPts <= 0 {
			switch strings.ToUpper(input.IndexName) {
			case "BANKNIFTY", "SENSEX", "BANKEX":
				slPts = 30.0 // Premium points (approx 60 spot pts)
			case "NIFTY", "FINNIFTY":
				slPts = 12.0 // Premium points (approx 24 spot pts)
			case "MIDCPNIFTY":
				slPts = 8.0
			default:
				slPts = 15.0
			}
		}

		rrRatio := preset.RR
		if rrRatio <= 0 {
			rrRatio = 2.0
		}

		// User overrides in input.Params take highest priority
		if input.Params != nil {
			if p, ok := parseParamFloat(input.Params["sl_pts"]); ok && p > 0 {
				slPts = p
			} else if p2, ok := parseParamFloat(input.Params["stop_loss_points"]); ok && p2 > 0 {
				slPts = p2
			}
			if r, ok := parseParamFloat(input.Params["rr_ratio"]); ok && r > 0 {
				rrRatio = r
			} else if r2, ok := parseParamFloat(input.Params["risk_reward"]); ok && r2 > 0 {
				rrRatio = r2
			}
		}

		targetOptPrice := math.Round((entryOptPrice+slPts*rrRatio)*100) / 100
		slOptPrice := math.Round((entryOptPrice-slPts)*100) / 100
		if slOptPrice < 0.5 {
			slOptPrice = 0.5 // floor: option can't go below 0.05 realistically
		}

		activeSlPts = slPts
		activeRRRatio = rrRatio

		activeTrade = &TradeSignal{
			Timestamp:             tick.Datetime,
			Strike:                concreteStrike,
			Symbol:                input.IndexName,
			TradeType:             "BUY",
			IndexEntryPrice:       tick.SpotClose,
			EntryPrice:            entryOptPrice,
			TargetPrice:           targetOptPrice,
			StopLossPrice:         slOptPrice,
			InitialTargetPrice:    targetOptPrice,
			InitialStopLossPrice:  slOptPrice,
			TrailingStopLossPrice: slOptPrice,
			Quantity:              sig.Quantity,
			UtilizedCapital:       math.Round(entryOptPrice * float64(sig.Quantity)),
			Status:                "OPEN",
			Reason:                sig.TriggerReason + macroTag,
		}
		activeStrikeKey = concreteStrike

		activeLayers = nil
		filledCost = 0.0
		filledQty = 0

		if enableRetestLayering && layerCount > 1 {
			optSnap := tick.Options[concreteStrike]
			candleHigh := optSnap.High
			candleLow := optSnap.Low
			if candleHigh <= 0 || candleHigh <= candleLow {
				candleHigh = entryOptPrice * 1.02
				candleLow = entryOptPrice * 0.98
			}
			candleRange := candleHigh - candleLow

			baseLotSize := sig.Quantity / max(1, layerCount)
			if baseLotSize <= 0 {
				baseLotSize = sig.Quantity
			}

			sumPresetLots := sumLots(layerLots)
			for idx := 0; idx < layerCount; idx++ {
				pct := 25.0 * float64(idx+1)
				if idx < len(retestPercentages) {
					pct = retestPercentages[idx]
				}
				layerLimit := math.Round((candleHigh - (candleRange * (pct / 100.0))) * 100) / 100
				if layerLimit <= 0.5 {
					layerLimit = math.Round(entryOptPrice*(1.0-(float64(idx+1)*0.01))*100) / 100
				}
				layerQty := baseLotSize
				if idx < len(layerLots) && layerLots[idx] > 0 && sumPresetLots > 0 {
					layerQty = layerLots[idx] * (sig.Quantity / sumPresetLots)
					if layerQty <= 0 {
						layerQty = baseLotSize
					}
				}

				isFilled := false
				if optSnap.Low > 0 && optSnap.Low <= layerLimit {
					isFilled = true
					filledQty += layerQty
					filledCost += layerLimit * float64(layerQty)
				}

				activeLayers = append(activeLayers, pendingLayer{
					LimitPrice: layerLimit,
					Quantity:   layerQty,
					Filled:     isFilled,
				})
			}

			if filledQty > 0 {
				avgPrice := math.Round((filledCost/float64(filledQty))*100) / 100
				activeTrade.EntryPrice = avgPrice
				activeTrade.Quantity = filledQty
				activeTrade.UtilizedCapital = math.Round(filledCost)
				activeTrade.TargetPrice = math.Round((avgPrice+slPts*rrRatio)*100) / 100
				activeTrade.StopLossPrice = math.Round((avgPrice-slPts)*100) / 100
				if activeTrade.StopLossPrice < 0.5 {
					activeTrade.StopLossPrice = 0.5
				}
				activeTrade.InitialTargetPrice = activeTrade.TargetPrice
				activeTrade.InitialStopLossPrice = activeTrade.StopLossPrice
				activeTrade.TrailingStopLossPrice = activeTrade.StopLossPrice
			}
		}
	}

	totalPnL := 0.0
	winningTrades, losingTrades := 0, 0
	totalProfit, totalLoss := 0.0, 0.0
	peakPnL, maxDD := 0.0, 0.0

	for _, t := range trades {
		totalPnL += t.PnL
		if t.PnL > 0 {
			winningTrades++
			totalProfit += t.PnL
		} else if t.PnL < 0 {
			losingTrades++
			totalLoss += math.Abs(t.PnL)
		}
		if totalPnL > peakPnL {
			peakPnL = totalPnL
		}
		if dd := peakPnL - totalPnL; dd > maxDD {
			maxDD = dd
		}
	}

	winRate := 0.0
	if len(trades) > 0 {
		winRate = math.Round((float64(winningTrades)/float64(len(trades))*100.0)*100) / 100
	}
	profitFactor := 99.99
	if totalLoss > 0 {
		profitFactor = math.Round((totalProfit/totalLoss)*100) / 100
	}

	return StrategyResult{
		StrategyName:  s.GetName(),
		TotalTrades:   len(trades),
		WinningTrades: winningTrades,
		LosingTrades:  losingTrades,
		WinRate:       winRate,
		NetPnL:        math.Round(totalPnL*100) / 100,
		MaxDrawdown:   math.Round(maxDD*100) / 100,
		SharpeRatio:   math.Round((totalPnL/10000.0)*100) / 100,
		ProfitFactor:  profitFactor,
		Trades:        trades,
	}
}

// EvaluateLiveSignal evaluates live signals strictly enforcing backtest Rule 20 (Momentum Guardrails) & Rule 23 (ICT SMC v3).
func (s *QuantEngineStrategy) EvaluateLiveSignal(
	currentCandle map[string]interface{},
	prevCandles []map[string]interface{},
	indexName string,
	params map[string]interface{},
) *LiveOrderRequest {
	s.mu.Lock()
	defer s.mu.Unlock()

	closePrice, ok := currentCandle["close"].(float64)
	if !ok || closePrice <= 0 {
		return nil
	}

	openPrice, _ := currentCandle["open"].(float64)
	if openPrice <= 0 {
		openPrice = closePrice
	}
	highPrice, _ := currentCandle["high"].(float64)
	if highPrice <= 0 {
		highPrice = math.Max(openPrice, closePrice) + 2.0
	}
	lowPrice, _ := currentCandle["low"].(float64)
	if lowPrice <= 0 {
		lowPrice = math.Min(openPrice, closePrice) - 2.0
	}

	volFloat := 10000.0
	if v, ok := currentCandle["volume"].(float64); ok && v > 0 {
		volFloat = v
	} else if vInt, ok := currentCandle["volume"].(int64); ok && vInt > 0 {
		volFloat = float64(vInt)
	}

	// 1. Resolve Candle Time & Market Session Boundaries (09:15 - 15:30 IST)
	candleTime := nowIST()
	if dtStr, ok := currentCandle["datetime"].(string); ok && len(dtStr) >= 19 {
		if pt, err := time.ParseInLocation("2006-01-02 15:04:05", dtStr[:19], istLocation); err == nil {
			candleTime = pt
		}
	} else if tsInt, ok := currentCandle["timestamp"].(int64); ok && tsInt > 0 {
		candleTime = time.Unix(tsInt, 0).In(istLocation)
	} else if tsFloat, ok := currentCandle["timestamp"].(float64); ok && tsFloat > 0 {
		candleTime = time.Unix(int64(tsFloat), 0).In(istLocation)
	}

	// 2. Mathematical Consistency: 1-Minute OHLC Time-Bar Resampling
	// Aggregates sub-second and 1-second live ticks into standard 1-minute OHLC bars,
	// ensuring live trading and historical 1M replay evaluate mathematically identical candles.
	barKey := candleTime.Format("2006-01-02 15:04")
	if s.currentBarKey == barKey && len(s.candleBuffer) > 0 {
		// Intra-minute tick: update active running bar in place
		s.runningHigh = math.Max(s.runningHigh, highPrice)
		s.runningLow = math.Min(s.runningLow, lowPrice)
		s.runningClose = closePrice
		s.runningVolume += int64(volFloat)

		lastIdx := len(s.candleBuffer) - 1
		s.candleBuffer[lastIdx]["high"] = s.runningHigh
		s.candleBuffer[lastIdx]["low"] = s.runningLow
		s.candleBuffer[lastIdx]["close"] = s.runningClose
		s.candleBuffer[lastIdx]["volume"] = s.runningVolume
	} else {
		// New minute candle boundary: initialize new 1-minute OHLC bar
		s.currentBarKey = barKey
		s.runningOpen = openPrice
		s.runningHigh = highPrice
		s.runningLow = lowPrice
		s.runningClose = closePrice
		s.runningVolume = int64(volFloat)

		newBar := map[string]interface{}{
			"datetime":  candleTime.Format("2006-01-02 15:04:05"),
			"timestamp": candleTime.Unix(),
			"open":      openPrice,
			"high":      highPrice,
			"low":       lowPrice,
			"close":     closePrice,
			"volume":    s.runningVolume,
		}
		s.candleBuffer = append(s.candleBuffer, newBar)
		if len(s.candleBuffer) > 30 {
			s.candleBuffer = s.candleBuffer[1:]
		}
	}

	// 3. Time-Based Opening Range Discovery (ORB) (09:15 - 09:30 AM IST = 15 Minutes)
	minuteOfDay := candleTime.Hour()*60 + candleTime.Minute()
	if !s.orbDiscovered {
		if s.orbHigh == 0 || highPrice > s.orbHigh {
			s.orbHigh = highPrice
		}
		if s.orbLow == 0 || lowPrice < s.orbLow {
			s.orbLow = lowPrice
		}
		// ORB discovered after 15 minutes of market opening (at or after 09:30 AM IST)
		if minuteOfDay >= (9*60+30) || (s.orbHigh > 0 && len(s.candleBuffer) >= 15) {
			s.orbDiscovered = true
		}
	}

	// Time window pre-filter: outside any valid market trading hours
	if minuteOfDay < (9*60+15) || minuteOfDay > (15*60+5) {
		return nil // Outside valid market hours
	}

	// Need at least 5 candles to compute valid moving averages
	if len(s.candleBuffer) < 5 {
		return nil
	}

	// Load strategy preset from strategy name or first attached BacktestRule rule_type.
	// Falls back to "momentum_scalp" default if no specific preset key matches.
	presetKey := "momentum_scalp"
	if s.GetName() != "" && s.GetName() != "quant_engine" {
		presetKey = s.GetName()
	}
	preset := GetStrategyPreset(presetKey)
	if params != nil {
		if stratName, ok := params["strategy_name"].(string); ok && stratName != "" {
			presetKey = strings.ToLower(strings.TrimSpace(stratName))
			preset = GetStrategyPreset(presetKey)
		}
		// Only allow attached rules to define presetKey if strategy is generic "quant_engine"
		if s.GetName() == "" || s.GetName() == "quant_engine" {
			if rawRules, ok := params["rules"].([]interface{}); ok && len(rawRules) > 0 {
				if rMap, isMap := rawRules[0].(map[string]interface{}); isMap {
					ruleType := strings.ToLower(fmt.Sprintf("%v", rMap["rule_type"]))
					if ruleType != "" && ruleType != "<nil>" {
						presetKey = ruleType
						preset = GetStrategyPreset(presetKey)
					}
				}
			}
		}
	}

	// Enforce trade cooldown (default 5 minutes in backtest/quant mode to avoid churning)
	cooldown := 5 * time.Minute
	if preset.CooldownSeconds > 0 {
		cooldown = time.Duration(preset.CooldownSeconds) * time.Second
	}

	if params != nil {
		if cdSec, ok := params["cooldown_seconds"].(float64); ok && cdSec > 0 {
			cooldown = time.Duration(cdSec) * time.Second
		} else if mode, ok := params["execution_mode"].(string); ok && (strings.EqualFold(mode, "MOCK") || strings.EqualFold(mode, "LIVE") || strings.EqualFold(mode, "SANDBOX")) {
			// If not provided in params, fallback to preset or 15 seconds
			if preset.CooldownSeconds == 0 {
				cooldown = 15 * time.Second
			}
		}
	}
	if !s.lastSignalTime.IsZero() && candleTime.Sub(s.lastSignalTime) < cooldown {
		return nil
	}
	if params != nil {
		// Optimizer overrides
		if emaF, ok := params["ema_fast"].(int); ok && emaF > 0 {
			preset.EMAFast = emaF
		} else if emaF2, ok := params["ema_fast"].(float64); ok && emaF2 > 0 {
			preset.EMAFast = int(emaF2)
		}
		if emaS, ok := params["ema_slow"].(int); ok && emaS > 0 {
			preset.EMASlow = emaS
		} else if emaS2, ok := params["ema_slow"].(float64); ok && emaS2 > 0 {
			preset.EMASlow = int(emaS2)
		}
	}
	minDisplacement := preset.MinDisplacement
	ruleID := 0
	ruleName := preset.Name

	// 4. Calculate Exponential Moving Averages using preset EMA periods
	emaFast := s.calculateEMA(s.candleBuffer, preset.EMAFast)
	emaSlow := s.calculateEMA(s.candleBuffer, preset.EMASlow)

	// Compute RSI (period 14) — used as optional confirmation filter
	rsiBuy, rsiSell := 35.0, 65.0
	if params != nil {
		if v, ok := params["rsi_buy"].(float64); ok && v > 0 {
			rsiBuy = v
		} else if v2, ok := params["rsi_buy"].(int); ok && v2 > 0 {
			rsiBuy = float64(v2)
		}
		if v, ok := params["rsi_sell"].(float64); ok && v > 0 {
			rsiSell = v
		} else if v2, ok := params["rsi_sell"].(int); ok && v2 > 0 {
			rsiSell = float64(v2)
		}
	}
	rsiValue := s.calculateRSI(s.candleBuffer, 14)
	useRSIFilter := len(s.candleBuffer) >= 14 && rsiValue > 0

	// Compute MACD (12, 26, 9) — used as momentum crossover confirmation
	macdLine, signalLine, _ := s.calculateMACD(s.candleBuffer, 12, 26, 9)
	useMACDFilter := len(s.candleBuffer) >= 26 && (macdLine != 0 || signalLine != 0)

	// 5. Calculate Price Action Momentum Metrics:
	// - candBody: real directional body (require >= 3.5 index pts to avoid flat chop candles)
	// - candRange: total candle range
	// - directionalClose: close in upper 30% for Call, lower 30% for Put
	candBody := math.Abs(closePrice - openPrice)
	candRange := math.Max(1.0, highPrice-lowPrice)
	displacementRatio := candBody / candRange
	displacementPct := math.Round(displacementRatio*1000) / 10


	// 6. High-Probability Momentum Verification
	isBullishSignal := false
	isBearishSignal := false
	var triggerReason string

	// Bullish Criteria:
	// 1. EMA divergence
	// 2. Strong green candle: close > open AND candBody >= 3.0 pts
	// 3. Directional close in top 35% of candle range (buyers in full control)
	// 4. Above ORB Midpoint / ORB High (if UseORBFilter is enabled)
	orbMid := 0.0
	if s.orbHigh > 0 && s.orbLow > 0 {
		orbMid = (s.orbHigh + s.orbLow) / 2.0
	}
	isBullishTrend := emaFast >= (emaSlow + 0.3)
	isBullishCandle := closePrice > openPrice && candBody >= 3.0 && (closePrice >= (highPrice-candRange*0.35))
	isBullishORB := !preset.UseORBFilter || (orbMid == 0.0 || closePrice >= orbMid)
	// RSI confirmation: for Calls, RSI should show bullish momentum (> 50) but not be overbought (<= rsiSell)
	isBullishRSI := !useRSIFilter || (rsiValue > 50 && rsiValue <= rsiSell)
	// MACD confirmation: MACD line must be above or crossing signal for bullish
	isBullishMACD := !useMACDFilter || macdLine >= signalLine

	// Bearish Criteria:
	// 1. EMA divergence
	// 2. Strong red candle: close < open AND candBody >= 3.0 pts
	// 3. Directional close in bottom 35% of candle range (sellers in full control)
	// 4. Below ORB Midpoint / ORB Low (if UseORBFilter is enabled)
	isBearishTrend := emaFast <= (emaSlow - 0.3)
	isBearishCandle := closePrice < openPrice && candBody >= 3.0 && (closePrice <= (lowPrice+candRange*0.35))
	isBearishORB := !preset.UseORBFilter || (orbMid == 0.0 || closePrice <= orbMid)
	// RSI confirmation: for Puts, RSI should show bearish momentum (< 50) but not be oversold (>= rsiBuy)
	isBearishRSI := !useRSIFilter || (rsiValue < 50 && rsiValue >= rsiBuy)
	// MACD confirmation: MACD line must be below or crossing signal for bearish
	isBearishMACD := !useMACDFilter || macdLine <= signalLine

	// Apply preset entry time window filter
	if minuteOfDay < preset.EntryWindowFrom || minuteOfDay > preset.EntryWindowTo {
		return nil
	}

	// Apply expiry day restriction if required by preset (e.g. Gamma Blast)
	if preset.RequireExpiryDay && !isIndexExpiryDay(indexName, candleTime) {
		return nil
	}

	if presetKey == "macd_ict_hybrid" && len(s.candleBuffer) >= 3 {
		c1 := s.candleBuffer[len(s.candleBuffer)-3]
		c2 := s.candleBuffer[len(s.candleBuffer)-2]
		c3 := s.candleBuffer[len(s.candleBuffer)-1]

		h1, _ := c1["high"].(float64)
		l1, _ := c1["low"].(float64)
		o2, _ := c2["open"].(float64)
		c2Close, _ := c2["close"].(float64)
		h2, _ := c2["high"].(float64)
		l2, _ := c2["low"].(float64)
		h3, _ := c3["high"].(float64)
		l3, _ := c3["low"].(float64)

		body2 := math.Abs(c2Close - o2)
		range2 := math.Max(1.0, h2-l2)
		disp2 := body2 / range2

		// Bullish FVG with 50% CE Re-test + Bullish MACD
		if l3 > h1 && c2Close > o2 && disp2 >= minDisplacement && isBullishMACD {
			ce := (l3 + h1) / 2.0
			if lowPrice <= (ce+2.0) && closePrice >= h1 {
				isBullishSignal = true
				triggerReason = fmt.Sprintf(
					"⚡ [%s] Bullish FVG [CE=%.1f] Retest | MACD=%.3f | Disp=%.1f%%",
					preset.Name, ce, macdLine, disp2*100,
				)
			}
		}

		// Bearish FVG with 50% CE Re-test + Bearish MACD
		if !isBullishSignal && h3 < l1 && c2Close < o2 && disp2 >= minDisplacement && isBearishMACD {
			ce := (h3 + l1) / 2.0
			if highPrice >= (ce-2.0) && closePrice <= l1 {
				isBearishSignal = true
				triggerReason = fmt.Sprintf(
					"⚡ [%s] Bearish FVG [CE=%.1f] Retest | MACD=%.3f | Disp=%.1f%%",
					preset.Name, ce, macdLine, disp2*100,
				)
			}
		}
	} else if presetKey == "volume_amd" && len(s.candleBuffer) >= 5 {
		// Volume + AMD (Accumulation, Manipulation, Distribution) Pattern
		// Phase 1: Accumulation Boundaries (Rolling 15 bars or ORB if established)
		accHigh := 0.0
		accLow := 99999999.0
		lookback := len(s.candleBuffer) - 1
		if lookback > 15 {
			lookback = 15
		}
		startIdx := len(s.candleBuffer) - 1 - lookback
		for b := startIdx; b < len(s.candleBuffer)-1; b++ {
			cHigh, _ := s.candleBuffer[b]["high"].(float64)
			cLow, _ := s.candleBuffer[b]["low"].(float64)
			if cHigh > accHigh {
				accHigh = cHigh
			}
			if cLow > 0 && cLow < accLow {
				accLow = cLow
			}
		}

		// Phase 2: Volume Confirmation (previous bar surge or strong intra-minute pace)
		avgVol := s.calculateAvgVolume(s.candleBuffer[:len(s.candleBuffer)-1], 15)
		prevVol := 0.0
		if len(s.candleBuffer) >= 2 {
			if v, ok := s.candleBuffer[len(s.candleBuffer)-2]["volume"].(int64); ok {
				prevVol = float64(v)
			} else if vf, ok := s.candleBuffer[len(s.candleBuffer)-2]["volume"].(float64); ok {
				prevVol = vf
			}
		}
		isVolSurge := avgVol <= 0 || prevVol >= (avgVol * 1.1) || float64(s.runningVolume) >= (avgVol * 0.4)

		// Rejection Wick Calculations
		lowerWick := math.Min(openPrice, closePrice) - lowPrice
		upperWick := highPrice - math.Max(openPrice, closePrice)
		lowerWickRatio := lowerWick / candRange
		upperWickRatio := upperWick / candRange

		// Previous candle metrics (for 2-bar manipulation -> distribution)
		prevLow, prevHigh := 0.0, 0.0
		prevOpen, prevClose := 0.0, 0.0
		prevRange := 1.0
		prevLowerWickRatio := 0.0
		prevUpperWickRatio := 0.0
		if len(s.candleBuffer) >= 2 {
			p := s.candleBuffer[len(s.candleBuffer)-2]
			prevLow, _ = p["low"].(float64)
			prevHigh, _ = p["high"].(float64)
			prevOpen, _ = p["open"].(float64)
			prevClose, _ = p["close"].(float64)
			prevRange = math.Max(1.0, prevHigh-prevLow)
			prevLowerWickRatio = (math.Min(prevOpen, prevClose) - prevLow) / prevRange
			prevUpperWickRatio = (prevHigh - math.Max(prevOpen, prevClose)) / prevRange
		}

		// Bullish AMD (Spring / Sell-side Sweep below AccLow)
		// 1-bar: dipped below accLow, closed above accLow with lower wick >= 25%
		// 2-bar: previous bar dipped below accLow with rejection wick, current bar is green breaking structure
		if isVolSurge && (
			(lowPrice < accLow && closePrice >= accLow && lowerWickRatio >= 0.25 && closePrice > openPrice) ||
			(prevLow > 0 && prevLow < accLow && prevLowerWickRatio >= 0.25 && closePrice > openPrice && closePrice >= prevHigh) ) {
			isBullishSignal = true
			triggerReason = fmt.Sprintf(
				"⚡ [%s] Bullish Sweep (Low=%.1f < AccLow=%.1f) | Wick=%.1f%% | Close=%.1f",
				preset.Name, math.Min(lowPrice, prevLow), accLow, math.Max(lowerWickRatio, prevLowerWickRatio)*100, closePrice,
			)
		}

		// Bearish AMD (Upthrust / Buy-side Sweep above AccHigh)
		// 1-bar: popped above accHigh, closed below accHigh with upper wick >= 25%
		// 2-bar: previous bar popped above accHigh with rejection wick, current bar is red breaking structure
		if !isBullishSignal && isVolSurge && (
			(highPrice > accHigh && closePrice <= accHigh && upperWickRatio >= 0.25 && closePrice < openPrice) ||
			(prevHigh > 0 && prevHigh > accHigh && prevUpperWickRatio >= 0.25 && closePrice < openPrice && closePrice <= prevLow) ) {
			isBearishSignal = true
			triggerReason = fmt.Sprintf(
				"⚡ [%s] Bearish Sweep (High=%.1f > AccHigh=%.1f) | Wick=%.1f%% | Close=%.1f",
				preset.Name, math.Max(highPrice, prevHigh), accHigh, math.Max(upperWickRatio, prevUpperWickRatio)*100, closePrice,
			)
		}
	} else if presetKey == "ema_macd_retest" && len(s.candleBuffer) >= 3 {
		// EMA 9/21 Retest + MACD Momentum Engine
		isBullishRetest := emaFast > emaSlow &&
			lowPrice <= (emaFast + 2.0) &&
			closePrice > openPrice &&
			closePrice >= (emaFast - 0.5) &&
			macdLine >= signalLine &&
			macdLine >= -0.5 &&
			displacementRatio >= minDisplacement

		isBearishRetest := emaFast < emaSlow &&
			highPrice >= (emaFast - 2.0) &&
			closePrice < openPrice &&
			closePrice <= (emaFast + 0.5) &&
			macdLine <= signalLine &&
			macdLine <= 0.5 &&
			displacementRatio >= minDisplacement

		if isBullishRetest {
			isBullishSignal = true
			triggerReason = fmt.Sprintf(
				"⚡ [%s] Bullish EMA Retest (Low=%.1f <= EMA9=%.1f) | MACD=%.3f > Sig=%.3f | Disp=%.1f%%",
				preset.Name, lowPrice, emaFast, macdLine, signalLine, displacementPct,
			)
		} else if isBearishRetest {
			isBearishSignal = true
			triggerReason = fmt.Sprintf(
				"⚡ [%s] Bearish EMA Retest (High=%.1f >= EMA9=%.1f) | MACD=%.3f < Sig=%.3f | Disp=%.1f%%",
				preset.Name, highPrice, emaFast, macdLine, signalLine, displacementPct,
			)
		}
	}

	if !isBullishSignal && !isBearishSignal {
		if isBullishTrend && isBullishCandle && isBullishORB && isBullishRSI && isBullishMACD && displacementRatio >= minDisplacement {
			isBullishSignal = true
			triggerReason = fmt.Sprintf(
				"⚡ [%s] EMA %d/%d Bullish (%.1f>%.1f) | RSI=%.1f | MACD=%.3f | Disp=%.1f%%",
				preset.Name, preset.EMAFast, preset.EMASlow, emaFast, emaSlow, rsiValue, macdLine, displacementPct,
			)
		} else if isBearishTrend && isBearishCandle && isBearishORB && isBearishRSI && isBearishMACD && displacementRatio >= minDisplacement {
			isBearishSignal = true
			triggerReason = fmt.Sprintf(
				"⚡ [%s] EMA %d/%d Bearish (%.1f<%.1f) | RSI=%.1f | MACD=%.3f | Disp=%.1f%%",
				preset.Name, preset.EMAFast, preset.EMASlow, emaFast, emaSlow, rsiValue, macdLine, displacementPct,
			)
		}
	}

	// If neither rule criteria is met, hold state (NO TRADE)
	if !isBullishSignal && !isBearishSignal {
		return nil
	}

	// Mark signal timestamp for cooldown enforcement
	s.lastSignalTime = candleTime

	// 7. Dynamic Lot Sizing & Strike Selection from Incoming Data
	strikeStep := 50
	if params != nil {
		if step, ok := params["strike_step"].(float64); ok && step > 0 {
			strikeStep = int(step)
		} else if stepInt, ok := params["strike_step"].(int); ok && stepInt > 0 {
			strikeStep = stepInt
		}
	}
	if strikeStep <= 0 {
		if indexName == "BANKNIFTY" || indexName == "SENSEX" {
			strikeStep = 100
		} else if indexName == "MIDCPNIFTY" {
			strikeStep = 25
		} else {
			strikeStep = 50
		}
	}
	atmStrike := int(math.Round(closePrice/float64(strikeStep)) * float64(strikeStep))

	lotSize := 65
	if params != nil {
		if l, ok := params["lot_size"].(float64); ok && l > 0 {
			lotSize = int(l)
		} else if lInt, ok := params["lot_size"].(int); ok && lInt > 0 {
			lotSize = lInt
		}
	}
	if lotSize <= 0 {
		if indexName == "BANKNIFTY" {
			lotSize = 30
		} else {
			lotSize = 65
		}
	}

	lotsCount := 1
	if params != nil {
		if lc, ok := params["lots_count"].(float64); ok && lc > 0 {
			lotsCount = int(lc)
		} else if lcInt, ok := params["lots_count"].(int); ok && lcInt > 0 {
			lotsCount = lcInt
		}
	}
	if lotsCount <= 0 {
		lotsCount = 1
	}

	optionType := "CALL"
	transaction := "BUY"
	if isBearishSignal {
		optionType = "PUT"
	}

	activeExpiry := ""
	if params != nil {
		if exp, ok := params["active_expiry"].(string); ok && exp != "" {
			activeExpiry = strings.TrimSpace(exp)
		}
	}
	tradingSymbol := fmt.Sprintf("%s %s %d %s", indexName, activeExpiry, atmStrike, optionType)
	if activeExpiry == "" {
		tradingSymbol = fmt.Sprintf("%s %d %s", indexName, atmStrike, optionType)
	}

	slPts := preset.SLPts
	if slPts <= 0 {
		switch indexName {
		case "BANKNIFTY", "SENSEX", "BANKEX":
			slPts = 60.0
		case "NIFTY", "FINNIFTY":
			slPts = 25.0
		case "MIDCPNIFTY":
			slPts = 15.0
		default:
			slPts = 25.0
		}
	}
	rrRatio := preset.RR
	if rrRatio <= 0 {
		rrRatio = 2.5
	}
	if params != nil {
		if sl, ok := params["sl_pts"].(float64); ok && sl > 0 {
			slPts = sl
		}
		if rr, ok := params["rr_ratio"].(float64); ok && rr > 0 {
			rrRatio = rr
		}
	}

	orderType := preset.OrderType
	if orderType == "" {
		orderType = "MARKET"
	}
	limitPrice := 0.0

	// Strike sweep: if live option chain is available via params, find optimal entry strike + limit price.
	// Injected by strategy_worker as params["option_chain"] before calling EvaluateLiveSignal.
	strikeSweptSymbol := ""
	if params != nil {
		if oc, ok := params["option_chain"].(map[string]OptionSnap); ok && len(oc) > 0 {
			bestStrike := SweepStrikesForBestEntry(oc, atmStrike, optionType, strikeStep, indexName, activeExpiry)
			if bestStrike != nil && bestStrike.LimitPrice > 0 {
				tradingSymbol = bestStrike.TradingSymbol
				strikeSweptSymbol = bestStrike.Key
				limitPrice = bestStrike.LimitPrice
				orderType = "LIMIT"
			}
		}
	}

	// Always anchor SL/TP on the actual traded instrument price (Option Premium if trading options, else Spot)
	isOptionContract := strings.Contains(tradingSymbol, "CALL") || strings.Contains(tradingSymbol, "PUT") ||
		strings.HasSuffix(tradingSymbol, "CE") || strings.HasSuffix(tradingSymbol, "PE") ||
		strings.Contains(tradingSymbol, " CE") || strings.Contains(tradingSymbol, " PE")

	basePrice := limitPrice
	if isOptionContract {
		if basePrice <= 0 || basePrice > 2000 {
			if optLtp, ok := params["option_ltp"].(float64); ok && optLtp > 0 && optLtp < 2000 {
				basePrice = optLtp
			} else {
				if strings.Contains(indexName, "BANK") {
					basePrice = 250.0
				} else {
					basePrice = 120.0
				}
			}
			if orderType == "LIMIT" {
				limitPrice = basePrice
			}
		}
	} else {
		if basePrice <= 0 {
			basePrice = closePrice
		}
		if orderType == "LIMIT" && limitPrice <= 0 {
			limitPrice = closePrice
		}
	}

	var targetPrice, stopLossPrice float64
	if isOptionContract || basePrice < 2000 {
		// Option premium contract
		optSLPts := slPts
		if optSLPts <= 0 || optSLPts >= basePrice*0.70 {
			optSLPts = math.Max(1.0, math.Round(basePrice*0.20*100)/100)
		}
		stopLossPrice = math.Max(0.5, math.Round((basePrice-optSLPts)*100)/100)
		targetPrice = math.Round((basePrice+(optSLPts*rrRatio))*100) / 100
	} else {
		// Index spot contract
		stopLossPrice = math.Round((basePrice-slPts)*100) / 100
		targetPrice = math.Round((basePrice+slPts*rrRatio)*100) / 100
	}

	indicators := map[string]interface{}{
		"ema_fast":          preset.EMAFast,
		"ema_slow":          preset.EMASlow,
		"ema_fast_val":      math.Round(emaFast*100) / 100,
		"ema_slow_val":      math.Round(emaSlow*100) / 100,
		"rsi":               math.Round(rsiValue*100) / 100,
		"macd":              math.Round(macdLine*1000) / 1000,
		"macd_signal":       math.Round(signalLine*1000) / 1000,
		"macd_histogram":    math.Round((macdLine-signalLine)*1000) / 1000,
		"displacement_pct":  displacementPct,
		"orb_high":          math.Round(s.orbHigh*100) / 100,
		"orb_low":           math.Round(s.orbLow*100) / 100,
		"spot_price":        closePrice,
		"swept_strike":      strikeSweptSymbol,
		"limit_entry_price": limitPrice,
	}

	s.lastSignalTime = candleTime

	return &LiveOrderRequest{
		IndexName:     indexName,
		TradingSymbol: tradingSymbol,
		OptionType:    optionType,
		Transaction:   transaction,
		OrderType:     orderType,
		LimitPrice:    limitPrice,
		Quantity:      lotSize * lotsCount,
		TargetPrice:   targetPrice,
		StopLossPrice: stopLossPrice,
		StrategyName:  s.GetName(),
		Timestamp:     candleTime.Format("03:04:05 PM"),
		RuleID:        ruleID,
		RuleName:      ruleName,
		TriggerReason: triggerReason,
		Indicators:    indicators,
		SlippagePts:   0.00,
	}
}

// calculateEMA calculates the Exponential Moving Average over the provided candle closes.
func (s *QuantEngineStrategy) calculateEMA(candles []map[string]interface{}, period int) float64 {
	if len(candles) == 0 {
		return 0
	}
	k := 2.0 / float64(period+1)
	ema, _ := candles[0]["close"].(float64)

	for i := 1; i < len(candles); i++ {
		price, ok := candles[i]["close"].(float64)
		if ok && price > 0 {
			ema = (price * k) + (ema * (1.0 - k))
		}
	}
	return ema
}

// calculateRSI computes RSI over the candle buffer using Wilder's smoothing method.
func (s *QuantEngineStrategy) calculateRSI(candles []map[string]interface{}, period int) float64 {
	if len(candles) < period+1 {
		return 50.0
	}
	var gains, losses float64
	for i := 1; i <= period; i++ {
		prev, _ := candles[i-1]["close"].(float64)
		curr, _ := candles[i]["close"].(float64)
		change := curr - prev
		if change > 0 {
			gains += change
		} else {
			losses -= change
		}
	}
	avgGain := gains / float64(period)
	avgLoss := losses / float64(period)
	for i := period + 1; i < len(candles); i++ {
		prev, _ := candles[i-1]["close"].(float64)
		curr, _ := candles[i]["close"].(float64)
		change := curr - prev
		if change > 0 {
			avgGain = (avgGain*float64(period-1) + change) / float64(period)
			avgLoss = (avgLoss * float64(period-1)) / float64(period)
		} else {
			avgGain = (avgGain * float64(period-1)) / float64(period)
			avgLoss = (avgLoss*float64(period-1) - change) / float64(period)
		}
	}
	if avgLoss == 0 {
		return 100.0
	}
	rs := avgGain / avgLoss
	return 100.0 - (100.0 / (1.0 + rs))
}

// calculateAvgVolume computes simple moving average of volume over last N candles.
func (s *QuantEngineStrategy) calculateAvgVolume(candles []map[string]interface{}, period int) float64 {
	if len(candles) == 0 {
		return 0
	}
	start := 0
	if len(candles) > period {
		start = len(candles) - period
	}
	var total float64
	count := 0
	for i := start; i < len(candles); i++ {
		if v, ok := candles[i]["volume"].(int64); ok && v > 0 {
			total += float64(v)
			count++
		} else if vFloat, ok := candles[i]["volume"].(float64); ok && vFloat > 0 {
			total += vFloat
			count++
		}
	}
	if count == 0 {
		return 0
	}
	return total / float64(count)
}

// calculateMACD returns (macdLine, signalLine, histogram) using standard 12/26/9 periods.
func (s *QuantEngineStrategy) calculateMACD(candles []map[string]interface{}, fastP, slowP, signalP int) (float64, float64, float64) {
	if len(candles) < slowP {
		return 0, 0, 0
	}
	ema12 := s.calculateEMA(candles, fastP)
	ema26 := s.calculateEMA(candles, slowP)
	macdLine := ema12 - ema26

	// Build synthetic MACD series for the signal EMA (approximate using last N candles)
	macdSeries := make([]map[string]interface{}, 0, len(candles)-slowP+1)
	for i := slowP - 1; i < len(candles); i++ {
		slice := candles[:i+1]
		e12 := s.calculateEMA(slice, fastP)
		e26 := s.calculateEMA(slice, slowP)
		macdSeries = append(macdSeries, map[string]interface{}{"close": e12 - e26})
	}
	var signalLine float64
	if len(macdSeries) >= signalP {
		signalLine = s.calculateEMA(macdSeries, signalP)
	}
	return macdLine, signalLine, macdLine - signalLine
}

// isIndexExpiryDay checks if the given time corresponds to the regulatory exchange expiry day for the index.
func isIndexExpiryDay(indexName string, t time.Time) bool {
	idx := strings.ToUpper(strings.TrimSpace(indexName))
	weekday := t.Weekday()
	dateStr := t.Format("2006-01-02")

	switch idx {
	case "NIFTY":
		return weekday == time.Thursday
	case "BANKNIFTY":
		// Historical: Wednesday (Sept 2023 - Nov 2024), otherwise Thursday
		if dateStr >= "2023-09-04" && dateStr < "2024-11-20" {
			return weekday == time.Wednesday
		}
		return weekday == time.Thursday
	case "FINNIFTY":
		return weekday == time.Tuesday
	case "MIDCPNIFTY":
		if dateStr >= "2023-08-21" {
			return weekday == time.Monday
		}
		return weekday == time.Wednesday
	case "SENSEX":
		return weekday == time.Friday
	case "BANKEX":
		return weekday == time.Monday
	default:
		// Default to Thursday for Indian equity derivatives
		return weekday == time.Thursday
	}
}

func sumLots(lots []int) int {
	s := 0
	for _, l := range lots {
		s += l
	}
	return s
}

func parseParamFloat(val interface{}) (float64, bool) {
	if val == nil {
		return 0, false
	}
	switch v := val.(type) {
	case float64:
		return v, true
	case int:
		return float64(v), true
	case string:
		if f, err := strconv.ParseFloat(v, 64); err == nil {
			return f, true
		}
	}
	return 0, false
}