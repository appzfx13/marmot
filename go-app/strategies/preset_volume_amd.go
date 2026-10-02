package strategies

// VolumeAMDPreset implements the Volume + AMD (Accumulation, Manipulation, Distribution) Pattern.
// High-volume liquidity sweep at accumulation boundaries triggers 1:2.5 distribution entry.
var VolumeAMDPreset = StrategyConfig{
	Name:            "Volume + AMD Pattern (1:2.5 Limit Midpoint)",
	EMAFast:         9,
	EMASlow:         21,
	RR:              2.5,
	SLPts:           12.0,
	MinDisplacement: 0.50,
	EntryWindowFrom: 9*60 + 25, // 09:25 AM IST (after initial accumulation setup)
	EntryWindowTo:   15 * 60,   // 15:00 PM IST
	UseORBFilter:    false,
	TrailBreakeven:  true,
	BreakevenAtR:    1.5,
	CooldownSeconds: 300,
	OrderType:       "LIMIT",
	Description:     "Volume + AMD liquidity sweep strategy. High volume absorption wick at accumulation extremes triggers 1:2.5 distribution entry.",
}
