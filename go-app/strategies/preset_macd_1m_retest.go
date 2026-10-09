package strategies

// MACD1mRetestPreset defines a 1-minute MACD (12/26/9) crossover entry with a 1-minute pullback retest.
var MACD1mRetestPreset = StrategyConfig{
	Name:            "MACD 1-Min Crossover + Retest (1:2.0 RR)",
	EMAFast:         12,
	EMASlow:         26,
	RR:              2.0,
	SLPts:           15.0,
	MinDisplacement: 0.35,
	EntryWindowFrom: 9*60 + 18,
	EntryWindowTo:   15 * 60,
	UseORBFilter:    false,
	TrailBreakeven:  true,
	BreakevenAtR:    1.0,
	TSL2_At_R:       1.5,
	TSL2_Lock_R:     0.75,
	CooldownSeconds: 60,
	OrderType:       "LIMIT",
	Description:     "1-min MACD (12/26/9) crossover confirmed by 1-min candle retest to fast EMA with Strike Sweep ATM±3 mid-price entry and 1:2.0 RR.",
}
