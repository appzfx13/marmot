package strategies

// MACDICTHybridPreset provides the advanced HTF MACD + ICT Smart Money Hybrid configuration.
// Fuses 15m HTF MACD trend & momentum expansion with 1m liquidity sweeps, displacement, and FVG CE entry.
var MACDICTHybridPreset = StrategyConfig{
	Name:            "Advanced HTF MACD + ICT Hybrid (1:2.0 High Winrate)",
	EMAFast:         12,
	EMASlow:         26,
	RR:              2.0,
	SLPts:           15.0,
	MinDisplacement: 0.65,
	EntryWindowFrom: 9*60 + 20,
	EntryWindowTo:   14*60 + 45,
	UseORBFilter:    true,
	TrailBreakeven:  true,
	BreakevenAtR:    1.2,
	CooldownSeconds: 300,
	OrderType:       "LIMIT",
	Description:     "15m HTF MACD & 200 EMA momentum gatekeeper with 1m Liquidity Sweep, MSS, and FVG Consequent Encroachment (50% CE) entry.",
}
