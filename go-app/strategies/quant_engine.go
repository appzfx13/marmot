package strategies

import (
	"fmt"
	"math"
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

			isClosed := false
			exitOptPrice := optClose
			exitSpotPrice := tick.SpotClose
			status := "WIN"
			exitReason := "TARGET_HIT"

			// Trailing stop loss to breakeven once option reaches +1.2R gain
			initialRisk := activeTrade.EntryPrice - activeTrade.InitialStopLossPrice
			if initialRisk > 0 && optHigh >= activeTrade.EntryPrice+(initialRisk*1.2) {
				trailedPrice := activeTrade.EntryPrice + 1.0 // Lock in entry + slippage buffer
				if activeTrade.StopLossPrice < trailedPrice {
					activeTrade.StopLossPrice = trailedPrice
					activeTrade.TrailingStopLossPrice = trailedPrice
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
				activeTrade.ExitPrice = math.Round(exitOptPrice*100) / 100
				activeTrade.IndexExitPrice = exitSpotPrice
				activeTrade.ExitTimestamp = tick.Datetime
				activeTrade.Status = status
				activeTrade.ExitReason = exitReason
				activeTrade.PnL = math.Round((activeTrade.ExitPrice-activeTrade.EntryPrice)*float64(activeTrade.Quantity)*100) / 100
				trades = append(trades, *activeTrade)
				activeTrade = nil
				activeStrikeKey = ""
			}
			continue
		}

		// ── 2. Evaluate entry signal on spot candle ───────────────────────────
		sig := localEngine.EvaluateLiveSignal(spotCandle, nil, input.IndexName, input.Params)
		if sig == nil {
			continue
		}

		// Determine option type from signal
		optionType := "CALL"
		if strings.Contains(strings.ToLower(sig.TriggerReason), "bearish") ||
			strings.Contains(strings.ToLower(sig.TriggerReason), "put") {
			optionType = "PUT"
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

		// Prefer ATM; cascade to ATM+1 / ATM-1 if premium is zero/missing.
		// Supports both relative keys ("ATM CALL") and absolute keys ("24500 CALL").
		strikeKey := ""
		entryOptPrice := 0.0

		// 1. Try relative keys first (e.g. datasets with ATM, ATM+1)
		for _, label := range []string{"ATM", "ATM+1", "ATM-1", "ATM+2", "ATM-2"} {
			candidate := label + " " + optionType
			if snap, ok := tick.Options[candidate]; ok && snap.Close > 0 {
				strikeKey = candidate
				entryOptPrice = snap.Close
				break
			}
		}

		// 2. Fallback to absolute numeric strike keys (e.g. "26200 CALL")
		if strikeKey == "" || entryOptPrice <= 0 {
			for _, offset := range []int{0, 1, -1, 2, -2, 3, -3} {
				numStrike := atmNum + (offset * strikeStep)
				candidate := fmt.Sprintf("%d %s", numStrike, optionType)
				if snap, ok := tick.Options[candidate]; ok && snap.Close > 0 {
					strikeKey = candidate
					entryOptPrice = snap.Close
					break
				}
			}
		}

		if strikeKey == "" || entryOptPrice <= 0 {
			continue // No valid option premium for entry — skip tick
		}

		// SL/TP in option premium points with dynamic default based on index
		slPts := 15.0
		switch strings.ToUpper(input.IndexName) {
		case "BANKNIFTY", "SENSEX", "BANKEX":
			slPts = 30.0 // Premium points (approx 60 spot pts)
		case "NIFTY", "FINNIFTY":
			slPts = 12.0 // Premium points (approx 24 spot pts)
		case "MIDCPNIFTY":
			slPts = 8.0
		}
		
		rrRatio := 2.5
		if p, ok := input.Params["sl_pts"].(float64); ok && p > 0 {
			slPts = p
		} else if p2, ok := input.Params["stop_loss_points"].(float64); ok && p2 > 0 {
			slPts = p2
		}
		if r, ok := input.Params["rr_ratio"].(float64); ok && r > 0 {
			rrRatio = r
		}

		targetOptPrice := math.Round((entryOptPrice+slPts*rrRatio)*100) / 100
		slOptPrice := math.Round((entryOptPrice-slPts)*100) / 100
		if slOptPrice < 0.5 {
			slOptPrice = 0.5 // floor: option can't go below 0.05 realistically
		}

		activeTrade = &TradeSignal{
			Timestamp:             tick.Datetime,
			Strike:                strikeKey,
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
		activeStrikeKey = strikeKey
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

	// 1. Maintain rolling candle buffer (last 30 candles)
	s.candleBuffer = append(s.candleBuffer, currentCandle)
	if len(s.candleBuffer) > 30 {
		s.candleBuffer = s.candleBuffer[1:]
	}

	// 2. Initial Opening Range Discovery (ORB) tracking
	if !s.orbDiscovered {
		if s.orbHigh == 0 || highPrice > s.orbHigh {
			s.orbHigh = highPrice
		}
		if s.orbLow == 0 || lowPrice < s.orbLow {
			s.orbLow = lowPrice
		}
		if len(s.candleBuffer) >= 15 {
			s.orbDiscovered = true
		}
	}

	// 3. Resolve Candle Time & Intraday Session Time Window Filter (09:20 - 15:00 IST)
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

	// Time window will be enforced after preset is loaded (placeholder check using broadest window)
	minuteOfDay := candleTime.Hour()*60 + candleTime.Minute()
	if minuteOfDay < (9*60+15) || minuteOfDay > (15*60+5) {
		return nil // Pre-filter: outside any valid market window
	}

	// Enforce trade cooldown (default 5 minutes in backtest/quant mode to avoid churning)
	cooldown := 5 * time.Minute
	if params != nil {
		if mode, ok := params["execution_mode"].(string); ok && (strings.EqualFold(mode, "MOCK") || strings.EqualFold(mode, "LIVE")) {
			cooldown = 15 * time.Second
		} else if cdSec, ok := params["cooldown_seconds"].(float64); ok && cdSec > 0 {
			cooldown = time.Duration(cdSec) * time.Second
		}
	}
	if !s.lastSignalTime.IsZero() && candleTime.Sub(s.lastSignalTime) < cooldown {
		return nil
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
			preset = GetStrategyPreset(stratName)
		}
		if rawRules, ok := params["rules"].([]interface{}); ok && len(rawRules) > 0 {
			if rMap, isMap := rawRules[0].(map[string]interface{}); isMap {
				ruleType := strings.ToLower(fmt.Sprintf("%v", rMap["rule_type"]))
				preset = GetStrategyPreset(ruleType)
			}
		}
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

	if isBullishTrend && isBullishCandle && isBullishORB && isBullishRSI && isBullishMACD && displacementRatio >= minDisplacement {
		isBullishSignal = true
		triggerReason = fmt.Sprintf(
			"⚡ [%s] EMA %d/%d Bull (%.1f>%.1f) | RSI=%.1f | MACD=%.3f | Disp=%.1f%%",
			preset.Name, preset.EMAFast, preset.EMASlow, emaFast, emaSlow, rsiValue, macdLine, displacementPct,
		)
	} else if isBearishTrend && isBearishCandle && isBearishORB && isBearishRSI && isBearishMACD && displacementRatio >= minDisplacement {
		isBearishSignal = true
		triggerReason = fmt.Sprintf(
			"⚡ [%s] EMA %d/%d Bear (%.1f<%.1f) | RSI=%.1f | MACD=%.3f | Disp=%.1f%%",
			preset.Name, preset.EMAFast, preset.EMASlow, emaFast, emaSlow, rsiValue, macdLine, displacementPct,
		)
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

	targetPrice := math.Round((closePrice+slPts*rrRatio)*100) / 100
	stopLossPrice := math.Round((closePrice-slPts)*100) / 100

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
	}

	orderType := preset.OrderType
	if orderType == "" {
		orderType = "MARKET"
	}
	limitPrice := 0.0
	if orderType == "LIMIT" {
		limitPrice = closePrice
	}

	s.lastSignalTime = candleTime

	return &LiveOrderRequest{
		IndexName:     indexName,
		TradingSymbol: tradingSymbol,
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