package strategies

// MACDCrossoverPreset provides a simple 12/26 EMA Crossover (MACD baseline) setup for testing.
var MACDCrossoverPreset = StrategyConfig{
	Name:            "Simple MACD Crossover (12/26)",
	EMAFast:         12,
	EMASlow:         26,
	RR:              2.0,
	SLPts:           15.0,
	MinDisplacement: 0.50,
	EntryWindowFrom: 9*60 + 15,
	EntryWindowTo:   15 * 60,
	UseORBFilter:    false, // Disabled to purely test MACD crossovers
	TrailBreakeven:  true,
	BreakevenAtR:    1.0,
	CooldownSeconds: 300,
	OrderType:       "MARKET",
	Description:     "Basic 12/26 EMA crossover mimicking MACD baseline. Used for Go Engine verification.",
}
