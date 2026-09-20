package strategies

// OptionSnap captures one option contract's OHLCV at a single timestamp.
// Mirrors a broker WebSocket option chain tick for one strike+type.
type OptionSnap struct {
	TradingSymbol string  `json:"trading_symbol,omitempty"`
	Open          float64 `json:"open"`
	High          float64 `json:"high"`
	Low           float64 `json:"low"`
	Close         float64 `json:"close"`
	Volume        int64   `json:"volume"`
	OI            int64   `json:"oi"`
	IV            float64 `json:"iv"`
	Delta         float64 `json:"delta,omitempty"`
	Gamma         float64 `json:"gamma,omitempty"`
	Theta         float64 `json:"theta,omitempty"`
	Vega          float64 `json:"vega,omitempty"`
	Bid           float64 `json:"bid,omitempty"`
	Ask           float64 `json:"ask,omitempty"`
}

// MacroSnapshot captures macro sentiment, institutional flow bias, and event risk regime.
type MacroSnapshot struct {
	SentimentScore float64 `json:"sentiment_score"`
	FIIDIIFlowBias float64 `json:"fii_dii_flow_bias"`
	GlobalRisk     float64 `json:"global_risk"`
	EventRiskFlag  bool    `json:"event_risk_flag"`
	MacroSummary   string  `json:"macro_summary"`
}

// MarketTick is a per-minute complete market snapshot — spot OHLCV + full option chain.
// Options key format: "{strike} {optionType}" e.g. "ATM CALL", "ATM+1 PUT".
// Equivalent to one broker WebSocket broadcast per minute.
type MarketTick struct {
	Timestamp int64                 `json:"timestamp"`
	Datetime  string                `json:"datetime"`
	Date      string                `json:"date"`
	IndexName string                `json:"index_name"`
	SpotOpen  float64               `json:"spot_open"`
	SpotHigh  float64               `json:"spot_high"`
	SpotLow   float64               `json:"spot_low"`
	SpotClose float64               `json:"spot_close"`
	Options   map[string]OptionSnap `json:"options"`
	Macro     *MacroSnapshot        `json:"macro,omitempty"`
}

// StrategyInput carries the full tick feed and parameters for strategy execution.
type StrategyInput struct {
	Date          string                              `json:"date"`
	IndexName     string                              `json:"index_name"`
	Ticks         []MarketTick                        `json:"ticks"`
	Candles       []map[string]interface{}            `json:"candles"`
	OptionCandles map[string][]map[string]interface{} `json:"option_candles"`
	Params        map[string]interface{}              `json:"params"`
}

// TradeSignal represents an executed trade entry/exit signal.
type TradeSignal struct {
	Timestamp       string  `json:"timestamp"`         // Entry time
	ExitTimestamp   string  `json:"exit_timestamp"`    // Exit time
	Strike          string  `json:"strike"`            // Option key e.g. "ATM+1 CALL"
	Symbol          string  `json:"symbol"`            // Index name e.g. "NIFTY"
	TradeType       string  `json:"trade_type"`        // BUY
	IndexEntryPrice float64 `json:"index_entry_price"` // Spot level at entry
	IndexExitPrice  float64 `json:"index_exit_price"`  // Spot level at exit
	EntryPrice          float64 `json:"entry_price"`       // Option premium at entry
	ExitPrice           float64 `json:"exit_price"`        // Option premium at exit
	TargetPrice         float64 `json:"target_price"`      // Current/Trailing target
	StopLossPrice       float64 `json:"stop_loss_price"`   // Current/Trailing SL
	InitialTargetPrice   float64 `json:"initial_target_price"`   // Original Option premium target at entry
	InitialStopLossPrice float64 `json:"initial_stop_loss_price"` // Original Option premium SL at entry
	TrailingStopLossPrice float64 `json:"trailing_stop_loss_price,omitempty"` // Trailed Stop Loss level
	ExitReason           string  `json:"exit_reason,omitempty"`            // TARGET_HIT, TRAILING_SL_HIT, STOP_LOSS_HIT, EOD_SQUAREOFF
	Quantity             int     `json:"quantity"`
	UtilizedCapital      float64 `json:"utilized_capital"`
	PnL                  float64 `json:"pnl"`
	Status               string  `json:"status"` // WIN, LOSS, OPEN
	Reason               string  `json:"reason"`
}

// StrategyResult holds aggregated performance metrics and trade logs.
type StrategyResult struct {
	StrategyName  string        `json:"strategy_name"`
	TotalTrades   int           `json:"total_trades"`
	WinningTrades int           `json:"winning_trades"`
	LosingTrades  int           `json:"losing_trades"`
	WinRate       float64       `json:"win_rate"`
	NetPnL        float64       `json:"net_pnl"`
	MaxDrawdown   float64       `json:"max_drawdown"`
	SharpeRatio   float64       `json:"sharpe_ratio"`
	ProfitFactor  float64       `json:"profit_factor"`
	Trades        []TradeSignal `json:"trades"`
}

// LiveOrderRequest represents an automated live order payload for DhanHQ/Fyers execution.
type LiveOrderRequest struct {
	IndexName     string  `json:"index_name"`     // e.g. NIFTY
	TradingSymbol string  `json:"trading_symbol"` // e.g. NIFTY 22400 CE
	Transaction   string  `json:"transaction"`    // BUY / SELL
	OrderType     string  `json:"order_type"`     // MARKET / LIMIT
	LimitPrice    float64 `json:"limit_price,omitempty"` // Execution limit price if LIMIT order
	Quantity      int     `json:"quantity"`       // Position quantity
	TargetPrice   float64 `json:"target_price"`
	StopLossPrice float64 `json:"stop_loss_price"`
	StrategyName  string                 `json:"strategy_name"`
	Timestamp     string                 `json:"timestamp"`
	RuleID        int                    `json:"rule_id,omitempty"`
	RuleName      string                 `json:"rule_name,omitempty"`
	TriggerReason string                 `json:"trigger_reason,omitempty"`
	Indicators    map[string]interface{} `json:"indicators,omitempty"`
	SlippagePts   float64                `json:"slippage_pts"`
}

// Strategy defines the interface for all plug-and-play backtest & live automated trading modules.
type Strategy interface {
	GetName() string
	Execute(input StrategyInput) StrategyResult
	EvaluateLiveSignal(currentCandle map[string]interface{}, prevCandles []map[string]interface{}, indexName string, params map[string]interface{}) *LiveOrderRequest
}
