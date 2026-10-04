package strategies

// EMAMACDRetestPreset implements the EMA 9/21 Retest + MACD Momentum strategy.
// Price tests the fast EMA 9 level in the direction of the EMA 9/21 trend, confirmed by MACD momentum.
var EMAMACDRetestPreset = StrategyConfig{
	Name:            "EMA 9/21 Retest + MACD Momentum (1:2.0 RR)",
	EMAFast:         9,
	EMASlow:         21,
	RR:              2.0,
	SLPts:           15.0,
	MinDisplacement: 0.40,
	EntryWindowFrom: 9*60 + 20, // 09:20 AM IST (after opening range discovery)
	EntryWindowTo:   14*60 + 45, // 14:45 PM IST (before EOD square-off)
	UseORBFilter:    false,
	TrailBreakeven:  true,
	BreakevenAtR:    1.2,
	TSL2_At_R:       1.6,
	TSL2_Lock_R:     0.8,
	CooldownSeconds: 300,
	OrderType:       "LIMIT",
	Description:     "EMA 9/21 trend alignment with price pullback retest to EMA 9 and MACD zero-line momentum gatekeeper. Features Strike Sweep ATM±3 mid-price entry and 1:2.0 RR.",
}
