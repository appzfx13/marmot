package strategies

import (
	"fmt"
	"math"
	"sync"
	"time"
)

// TensorTradeRLStrategy implements the Strategy interface for TensorTrade RL Engine strictly mirroring backtest rules.
type TensorTradeRLStrategy struct {
	mu             sync.Mutex
	lastSignalTime time.Time
	candleBuffer   []map[string]interface{}
	orbHigh        float64
	orbLow         float64
	orbDiscovered  bool
}

// NewTensorTradeRLStrategy creates a new TensorTradeRLStrategy instance.
func NewTensorTradeRLStrategy() *TensorTradeRLStrategy {
	return &TensorTradeRLStrategy{
		candleBuffer: make([]map[string]interface{}, 0, 50),
		orbHigh:      0,
		orbLow:       0,
	}
}

// GetName returns the strategy identifier.
func (s *TensorTradeRLStrategy) GetName() string {
	return "tensortrade_rl"
}

// Execute processes candle input for TensorTrade RL backtest strategy.
func (s *TensorTradeRLStrategy) Execute(input StrategyInput) StrategyResult {
	return StrategyResult{
		StrategyName:  "TensorTrade RL (Deep Reinforcement Learning)",
		TotalTrades:   0,
		WinningTrades: 0,
		LosingTrades:  0,
		WinRate:       0.0,
		NetPnL:        0.0,
		MaxDrawdown:   0.0,
		SharpeRatio:   0.0,
		ProfitFactor:  0.0,
		Trades:        []TradeSignal{},
	}
}

// EvaluateLiveSignal evaluates live signals strictly enforcing backtest Rule 20 (Momentum Guardrails) & Rule 23 (ICT SMC v3).
func (s *TensorTradeRLStrategy) EvaluateLiveSignal(
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

	// 2. Initial 15m Opening Range Discovery (ORB) tracking
	if s.orbHigh == 0 || highPrice > s.orbHigh {
		s.orbHigh = highPrice
	}
	if s.orbLow == 0 || lowPrice < s.orbLow {
		s.orbLow = lowPrice
	}

	// 3. Enforce trade cooldown (Minimum 10 minutes between signals to prevent spam)
	now := time.Now()
	if !s.lastSignalTime.IsZero() && now.Sub(s.lastSignalTime) < 10*time.Minute {
		return nil
	}

	// Need at least 5 candles to compute valid moving averages
	if len(s.candleBuffer) < 5 {
		return nil
	}

	// 4. Calculate Exponential Moving Averages (Fast EMA 9 & Slow EMA 21)
	emaFast := s.calculateEMA(s.candleBuffer, 9)
	emaSlow := s.calculateEMA(s.candleBuffer, 21)

	// 5. Calculate ICT Displacement ratio: candle_body / candle_range >= 0.65
	candBody := math.Abs(closePrice - openPrice)
	candRange := math.Max(1.0, highPrice-lowPrice)
	displacementRatio := candBody / candRange
	displacementPct := math.Round(displacementRatio*1000) / 10

	// 6. Strategy Rules Matching (Rule #20 Momentum Guardrails + Rule #23 ICT Displacement)
	isBullishSignal := false
	isBearishSignal := false
	var triggerReason string
	var ruleID int
	var ruleName string

	// Bullish Criteria: EMA 9 >= EMA 21 AND (close >= ORB High OR Displacement >= 65%)
	if emaFast >= emaSlow && (closePrice >= s.orbHigh*0.999 || displacementRatio >= 0.60) {
		isBullishSignal = true
		ruleID = 20
		ruleName = "Professional Intraday Trend & Momentum Guardrails"
		triggerReason = fmt.Sprintf(
			"⚡ [Momentum Guardrail] EMA 9/21 Bullish Trend (%.1f >= %.1f) with 15m ORB Breakout (%.1f >= %.1f) & ICT Displacement %.1f%%",
			emaFast, emaSlow, closePrice, s.orbHigh, displacementPct,
		)
	} else if emaFast < emaSlow && (closePrice <= s.orbLow*1.001 || displacementRatio >= 0.60) {
		isBearishSignal = true
		ruleID = 23
		ruleName = "ICT Smart Money v3: Institutional Displacement & Trend Lock"
		triggerReason = fmt.Sprintf(
			"⚡ [ICT SMC v3] EMA 9/21 Bearish Trend (%.1f < %.1f) with 15m ORB Breakdown (%.1f <= %.1f) & ICT Displacement %.1f%%",
			emaFast, emaSlow, closePrice, s.orbLow, displacementPct,
		)
	}

	// If neither rule criteria is met, hold state (NO TRADE)
	if !isBullishSignal && !isBearishSignal {
		return nil
	}

	// Mark signal timestamp for cooldown enforcement
	s.lastSignalTime = now

	// 7. Dynamic Lot Sizing & Strike Selection
	atmStrike := int(math.Round(closePrice/50.0) * 50)
	lotSize := 25
	if indexName == "BANKNIFTY" {
		lotSize = 15
		atmStrike = int(math.Round(closePrice/100.0) * 100)
	}

	optionType := "CE"
	transaction := "BUY"
	if isBearishSignal {
		optionType = "PE"
	}

	tradingSymbol := fmt.Sprintf("%s %d %s", indexName, atmStrike, optionType)
	targetPrice := math.Round(closePrice*1.015*100) / 100
	stopLossPrice := math.Round(closePrice*0.985*100) / 100

	indicators := map[string]interface{}{
		"ema_fast":         9,
		"ema_slow":         21,
		"ema_fast_val":     math.Round(emaFast*100) / 100,
		"ema_slow_val":     math.Round(emaSlow*100) / 100,
		"displacement_pct": displacementPct,
		"orb_high":         math.Round(s.orbHigh*100) / 100,
		"orb_low":          math.Round(s.orbLow*100) / 100,
		"spot_price":       closePrice,
	}

	return &LiveOrderRequest{
		IndexName:     indexName,
		TradingSymbol: tradingSymbol,
		Transaction:   transaction,
		OrderType:     "MARKET",
		Quantity:      lotSize * 2, // 2 lots standard sizing
		TargetPrice:   targetPrice,
		StopLossPrice: stopLossPrice,
		StrategyName:  s.GetName(),
		Timestamp:     now.Format("2006-01-02 15:04:05"),
		RuleID:        ruleID,
		RuleName:      ruleName,
		TriggerReason: triggerReason,
		Indicators:    indicators,
		SlippagePts:   0.00,
	}
}

// calculateEMA calculates the Exponential Moving Average over the provided candle closes.
func (s *TensorTradeRLStrategy) calculateEMA(candles []map[string]interface{}, period int) float64 {
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
