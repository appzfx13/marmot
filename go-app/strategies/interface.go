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
	Timestamp     string  `json:"timestamp"`
	Symbol        string  `json:"symbol"`
	TradeType     string  `json:"trade_type"` // BUY_CE, BUY_PE, SELL_CE, SELL_PE
	EntryPrice    float64 `json:"entry_price"`
	ExitPrice     float64 `json:"exit_price"`
	TargetPrice   float64 `json:"target_price"`
	StopLossPrice float64 `json:"stop_loss_price"`
	Quantity      int     `json:"quantity"`
	PnL           float64 `json:"pnl"`
	Status        string  `json:"status"` // WIN, LOSS, OPEN
	Reason        string  `json:"reason"`
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

// Strategy defines the interface for all plug-and-play backtest strategy modules.
type Strategy interface {
	GetName() string
	Execute(input StrategyInput) StrategyResult
}
