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
