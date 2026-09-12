package models

import "time"

// OrderRequest represents Dhan API v2 place/modify order payload.
type OrderRequest struct {
	DhanClientID      string  `json:"dhanClientId"`
	CorrelationID     string  `json:"correlationId"`
	TransactionType   string  `json:"transactionType"` // BUY / SELL
	ExchangeSegment   string  `json:"exchangeSegment"` // NSE_EQ, NSE_FNO, BSE_EQ, MCX_COMM
	ProductType       string  `json:"productType"`     // CNC, INTRADAY, MARGIN, MTF, CO, BO
	OrderType         string  `json:"orderType"`       // LIMIT, MARKET, STOP_LOSS, STOP_LOSS_MARKET
	Validity          string  `json:"validity"`        // DAY, IOC
	SecurityID        string  `json:"securityId"`
	Quantity          int     `json:"quantity"`
	DisclosedQuantity int     `json:"disclosedQuantity,omitempty"`
	Price             float64 `json:"price,omitempty"`
	TriggerPrice      float64 `json:"triggerPrice,omitempty"`
	AfterMarketOrder  bool    `json:"afterMarketOrder,omitempty"`
	AmoTime           string  `json:"amoTime,omitempty"`
	BoProfitValue     float64 `json:"boProfitValue,omitempty"`
	BoStopLossValue   float64 `json:"boStopLossValue,omitempty"`
	DrvExpiryDate     string  `json:"drvExpiryDate,omitempty"`
	DrvOptionsType    string  `json:"drvOptionsType,omitempty"` // CALL / PUT
	DrvStrikePrice    float64 `json:"drvStrikePrice,omitempty"`
}

// OrderResponse represents Dhan API v2 immediate synchronous response.
type OrderResponse struct {
	OrderID        string `json:"orderId"`
	OrderStatus    string `json:"orderStatus"` // PENDING
	OrderTimestamp string `json:"orderTimestamp,omitempty"`
}

// DhanPostbackWebhook represents official Dhan JSON webhook postback payload.
type DhanPostbackWebhook struct {
	DhanClientID      string  `json:"dhanClientId"`
	OrderID           string  `json:"orderId"`
	ExchangeOrderID   string  `json:"exchangeOrderId"`
	CorrelationID     string  `json:"correlationId"`
	OrderStatus       string  `json:"orderStatus"` // TRADED, REJECTED, CANCELLED, PENDING
	TransactionType   string  `json:"transactionType"`
	ExchangeSegment   string  `json:"exchangeSegment"`
	ProductType       string  `json:"productType"`
	OrderType         string  `json:"orderType"`
	Validity          string  `json:"validity"`
	TradingSymbol     string  `json:"tradingSymbol"`
	SecurityID        string  `json:"securityId"`
	Quantity          int     `json:"quantity"`
	DisclosedQuantity int     `json:"disclosedQuantity,omitempty"`
	Price             float64 `json:"price"`
	TriggerPrice      float64 `json:"triggerPrice,omitempty"`
	AfterMarketOrder  bool    `json:"afterMarketOrder,omitempty"`
	BoProfitValue     float64 `json:"boProfitValue,omitempty"`
	BoStopLossValue   float64 `json:"boStopLossValue,omitempty"`
	LegName           string  `json:"legName,omitempty"`
	CreateTime        string  `json:"createTime"`
	UpdateTime        string  `json:"updateTime"`
	ExchangeTime      string  `json:"exchangeTime"`
	DrvExpiryDate     string  `json:"drvExpiryDate,omitempty"`
	DrvOptionsType    string  `json:"drvOptionsType,omitempty"`
	DrvStrikePrice    float64 `json:"drvStrikePrice,omitempty"`
	TradedPrice       float64 `json:"tradedPrice"`
	TradedQuantity    int     `json:"tradedQuantity"`
	RejectionReason   string  `json:"rejectionReason,omitempty"`
}

// FundLimitResponse represents Dhan API v2 GET /v2/fundlimit.
type FundLimitResponse struct {
	DhanClientID        string  `json:"dhanClientId"`
	AvailabelBalance    float64 `json:"availabelBalance"`
	SodLimit            float64 `json:"sodLimit"`
	CollateralAmount    float64 `json:"collateralAmount"`
	ReceiveableAmount   float64 `json:"receiveableAmount"`
	UtilizedAmount      float64 `json:"utilizedAmount"`
	BlockedPayoutAmount float64 `json:"blockedPayoutAmount"`
	WithdrawableBalance float64 `json:"withdrawableBalance"`
}

// PositionItem represents Dhan API v2 GET /v2/positions item.
type PositionItem struct {
	DhanClientID          string  `json:"dhanClientId"`
	TradingSymbol         string  `json:"tradingSymbol"`
	SecurityID            string  `json:"securityId"`
	PositionType          string  `json:"positionType"` // LONG, SHORT, CLOSED
	ExchangeSegment       string  `json:"exchangeSegment"`
	ProductType           string  `json:"productType"`
	BuyAvg                float64 `json:"buyAvg"`
	BuyQty                int     `json:"buyQty"`
	CostPrice             float64 `json:"costPrice"`
	SellAvg               float64 `json:"sellAvg"`
	SellQty               int     `json:"sellQty"`
	NetQty                int     `json:"netQty"`
	RealizedProfit        float64 `json:"realizedProfit"`
	UnrealizedProfit      float64 `json:"unrealizedProfit"`
	RbiReferenceRate      float64 `json:"rbiReferenceRate"`
	Multiplier            int     `json:"multiplier"`
	CarryForwardBuyQty    int     `json:"carryForwardBuyQty"`
	CarryForwardSellQty   int     `json:"carryForwardSellQty"`
	CarryForwardBuyValue  float64 `json:"carryForwardBuyValue"`
	CarryForwardSellValue float64 `json:"carryForwardSellValue"`
	DayBuyQty             int     `json:"dayBuyQty"`
	DaySellQty            int     `json:"daySellQty"`
	DayBuyValue           float64 `json:"dayBuyValue"`
	DaySellValue          float64 `json:"daySellValue"`
	DrvExpiryDate         string  `json:"drvExpiryDate,omitempty"`
	DrvOptionType         string  `json:"drvOptionType,omitempty"`
	DrvStrikePrice        float64 `json:"drvStrikePrice,omitempty"`
	CrossCurrency         string  `json:"crossCurrency,omitempty"`
	EntryTime             string  `json:"entryTime,omitempty"`
	ExitTime              string  `json:"exitTime,omitempty"`
	StopLoss              float64 `json:"stopLoss,omitempty"`
	TakeProfit            float64 `json:"takeProfit,omitempty"`
}

// HoldingItem represents Dhan API v2 GET /v2/holdings item.
type HoldingItem struct {
	Exchange      string  `json:"exchange"`
	TradingSymbol string  `json:"tradingSymbol"`
	SecurityID    string  `json:"securityId"`
	ISIN          string  `json:"isin"`
	TotalQty      int     `json:"totalQty"`
	DpQty         int     `json:"dpQty"`
	T1Qty         int     `json:"t1Qty"`
	AvailableQty  int     `json:"availableQty"`
	CollateralQty int     `json:"collateralQty"`
	AvgCostPrice  float64 `json:"avgCostPrice"`
}

// OrderRecord holds in-memory order tracking metadata.
type OrderRecord struct {
	Order       OrderRequest `json:"order"`
	OrderID     string       `json:"orderId"`
	ExchangeID  string       `json:"exchangeOrderId"`
	Status      string       `json:"status"` // PENDING, TRADED, REJECTED, CANCELLED
	FilledQty   int          `json:"filledQty"`
	FilledPrice float64      `json:"filledPrice"`
	RejectMsg   string       `json:"rejectReason,omitempty"`
	CreatedAt   time.Time    `json:"createdAt"`
	UpdatedAt   time.Time    `json:"updatedAt"`
	EntryTime   time.Time    `json:"entryTime,omitempty"`
	ExitTime    time.Time    `json:"exitTime,omitempty"`
	StopLoss    float64      `json:"stopLoss,omitempty"`
	TakeProfit  float64      `json:"takeProfit,omitempty"`
}

// MarketTick represents an options or spot tick for MTM and streaming.
type MarketTick struct {
	Timestamp     time.Time `json:"timestamp"`
	SecurityID    string    `json:"securityId"`
	TradingSymbol string    `json:"tradingSymbol"`
	LTP           float64   `json:"ltp"`
	Open          float64   `json:"open"`
	High          float64   `json:"high"`
	Low           float64   `json:"low"`
	Close         float64   `json:"close"`
	Volume        int64     `json:"volume"`
}

// MarketCandleRecord represents a single OHLCV/OI/IV market candle in Apache Parquet format.
type MarketCandleRecord struct {
	Timestamp      int64   `parquet:"timestamp,int(64)" json:"timestamp"`
	Datetime       string  `parquet:"datetime,string" json:"datetime"`
	IndexName      string  `parquet:"index_name,string" json:"index_name"`
	InstrumentType string  `parquet:"instrument_type,string" json:"instrument_type"`
	Strike         string  `parquet:"strike,string" json:"strike"`
	OptionType     string  `parquet:"option_type,string" json:"option_type"`
	Open           float64 `parquet:"open,double" json:"open"`
	High           float64 `parquet:"high,double" json:"high"`
	Low            float64 `parquet:"low,double" json:"low"`
	Close          float64 `parquet:"close,double" json:"close"`
	Volume         int64   `parquet:"volume,int(64)" json:"volume"`
	OI             int64   `parquet:"oi,int(64)" json:"oi"`
	IV             float64 `parquet:"iv,double" json:"iv"`
	SpotPrice      float64 `parquet:"spot_price,double" json:"spot_price"`
}

// OptionStrikeRow represents a single bilateral (CE & PE) strike entry in the option chain matrix.
type OptionStrikeRow struct {
	Strike         float64 `json:"strike"`
	IsActiveWindow bool    `json:"is_active_window"`
	IsATM          bool    `json:"is_atm"`
	CE_LTP         float64 `json:"ce_ltp"`
	CE_Change      float64 `json:"ce_chg"`
	CE_ChangePct   float64 `json:"ce_chg_pct"`
	CE_OI          string  `json:"ce_oi"`
	PE_LTP         float64 `json:"pe_ltp"`
	PE_Change      float64 `json:"pe_chg"`
	PE_ChangePct   float64 `json:"pe_chg_pct"`
	PE_OI          string  `json:"pe_oi"`
}

// OptionChainResponse represents a comprehensive option chain payload compatible with Marmot's UI.
type OptionChainResponse struct {
	IsLive        bool              `json:"is_live"`
	IsMockLive    bool              `json:"is_mock_live"`
	FeedStatus    string            `json:"feed_status"`
	IndexName     string            `json:"index_name"`
	SpotSymbol    string            `json:"spot_symbol"`
	FyersSymbol   string            `json:"fyers_symbol"`
	SpotLTP       string            `json:"spot_ltp"`
	RawSpotLTP    float64           `json:"raw_spot_ltp"`
	SpotChange    string            `json:"spot_change"`
	SpotChangePct string            `json:"spot_change_pct"`
	IsPositive    bool              `json:"is_positive"`
	OpenPrice     string            `json:"open_price"`
	HighPrice     string            `json:"high_price"`
	LowPrice      string            `json:"low_price"`
	PrevClose     string            `json:"prev_close"`
	ATMStrike     string            `json:"atm_strike"`
	StrikeStep    int               `json:"strike_step"`
	PCR           float64           `json:"pcr"`
	IndiaVIX      float64           `json:"india_vix"`
	TotalStrikes  int               `json:"total_strikes"`
	Strikes       []OptionStrikeRow `json:"strikes"`
	LastUpdated   string            `json:"last_updated"`
}

