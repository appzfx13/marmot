package strategies

// StrategyInput contains candle data and parameters for strategy execution.
type StrategyInput struct {
	Date          string                   `json:"date"`
	IndexName     string                   `json:"index_name"`
	Candles       []map[string]interface{} `json:"candles"`
	OptionCandles map[string][]map[string]interface{} `json:"option_candles"`
	Params        map[string]interface{}  `json:"params"`
}

// TradeSignal represents an executed trade entry/exit signal.
type TradeSignal struct {
	Timestamp       string  `json:"timestamp"`        // Entry time e.g. "2025-01-01 15:00:00"
	ExitTimestamp   string  `json:"exit_timestamp"`   // Exit time e.g. "2025-01-01 15:01:00"
	Strike          string  `json:"strike"`           // Contract Strike e.g. "NIFTY 22400 CE"
	Symbol          string  `json:"symbol"`           // Index Name e.g. "NIFTY"
	TradeType       string  `json:"trade_type"`       // BUY_CE, BUY_PE, SELL_CE, SELL_PE
	IndexEntryPrice float64 `json:"index_entry_price"`// Index level at entry
	IndexExitPrice  float64 `json:"index_exit_price"` // Index level at exit
	EntryPrice      float64 `json:"entry_price"`
	ExitPrice       float64 `json:"exit_price"`
	TargetPrice     float64 `json:"target_price"`
	StopLossPrice   float64 `json:"stop_loss_price"`
	Quantity        int     `json:"quantity"`
	PnL             float64 `json:"pnl"`
	Status          string  `json:"status"` // WIN, LOSS, OPEN
	Reason          string  `json:"reason"`
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
	Quantity      int     `json:"quantity"`       // Position quantity
	TargetPrice   float64 `json:"target_price"`
	StopLossPrice float64 `json:"stop_loss_price"`
	StrategyName  string  `json:"strategy_name"`
	Timestamp     string  `json:"timestamp"`
}

// Strategy defines the interface for all plug-and-play backtest & live automated trading modules.
type Strategy interface {
	GetName() string
	Execute(input StrategyInput) StrategyResult
	EvaluateLiveSignal(currentCandle map[string]interface{}, prevCandles []map[string]interface{}, indexName string, params map[string]interface{}) *LiveOrderRequest
}
