package models

// MarketCandleRecord represents a single OHLCV/OI/IV market candle in Apache Parquet format.
// Uses parquet-go struct tags for columnar serialization with Snappy compression.
type MarketCandleRecord struct {
	Timestamp      int64   `parquet:"timestamp,int(64)" json:"timestamp"`
	Datetime       string  `parquet:"datetime,string" json:"datetime"`
	IndexName      string  `parquet:"index_name,string" json:"index_name"`
	InstrumentType string  `parquet:"instrument_type,string" json:"instrument_type"` // INDEX or OPTION
	Strike         string  `parquet:"strike,string" json:"strike"`                   // SPOT, ATM, ATM+1, 24500, etc.
	OptionType     string  `parquet:"option_type,string" json:"option_type"`         // INDEX, CALL, PUT
	Open           float64 `parquet:"open,double" json:"open"`
	High           float64 `parquet:"high,double" json:"high"`
	Low            float64 `parquet:"low,double" json:"low"`
	Close          float64 `parquet:"close,double" json:"close"`
	Volume         int64   `parquet:"volume,int(64)" json:"volume"`
	OI             int64   `parquet:"oi,int(64)" json:"oi"`
	IV             float64 `parquet:"iv,double" json:"iv"`
	SpotPrice      float64 `parquet:"spot_price,double" json:"spot_price"`
}

// ForexOrderFlowRecord represents a single Databento MBP-10 / Order Flow market record in Parquet format.
type ForexOrderFlowRecord struct {
	Timestamp int64   `parquet:"timestamp,int(64)" json:"timestamp"`
	Datetime  string  `parquet:"datetime,string" json:"datetime"`
	Symbol    string  `parquet:"symbol,string" json:"symbol"`
	Action    string  `parquet:"action,string" json:"action"`
	Side      string  `parquet:"side,string" json:"side"`
	Price     float64 `parquet:"price,double" json:"price"`
	Size      int64   `parquet:"size,int(64)" json:"size"`
	BidPx00   float64 `parquet:"bid_px_00,double" json:"bid_px_00"`
	AskPx00   float64 `parquet:"ask_px_00,double" json:"ask_px_00"`
	BidSz00   int64   `parquet:"bid_sz_00,int(64)" json:"bid_sz_00"`
	AskSz00   int64   `parquet:"ask_sz_00,int(64)" json:"ask_sz_00"`
	BidCt00   int64   `parquet:"bid_ct_00,int(64)" json:"bid_ct_00"`
	AskCt00   int64   `parquet:"ask_ct_00,int(64)" json:"ask_ct_00"`
	Delta     int64   `parquet:"delta,int(64)" json:"delta"`
	CVD       int64   `parquet:"cvd,int(64)" json:"cvd"`
}
