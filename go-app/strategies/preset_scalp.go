package strategies

// MicroScalpPreset provides tight 8pt SL institutional micro-scalp with 1:3 RR.
var MicroScalpPreset = StrategyConfig{
	Name:            "Institutional Micro-Scalp 1:3",
	EMAFast:         5,
	EMASlow:         13,
	RR:              3.0,
	SLPts:           8.0,
	MinDisplacement: 0.55,
	EntryWindowFrom: 9*60 + 20,
	EntryWindowTo:   14*60 + 30,
	UseORBFilter:    false,
	TrailBreakeven:  true,
	BreakevenAtR:    1.0,
	CooldownSeconds: 180,
	OrderType:       "MARKET",
	Description:     "EMA 5/13 fast scalp with tight 8pt SL and 1:3 RR. Trailing BE at 1R. No ORB filter.",
}

// HFTScalpPreset provides ultra-fast EMA 3/8 micro-scalp with high winrate trailing breakeven.
var HFTScalpPreset = StrategyConfig{
	Name:            "High-Frequency Micro-Scalp (HFT)",
	EMAFast:         3,
	EMASlow:         8,
	RR:              2.0,
	SLPts:           8.0,
	MinDisplacement: 0.50,
	EntryWindowFrom: 9*60 + 20,
	EntryWindowTo:   15*60 + 0,
	UseORBFilter:    false,
	TrailBreakeven:  true,
	BreakevenAtR:    0.8,
	CooldownSeconds: 60,
	OrderType:       "MARKET",
	Description:     "Ultra-fast EMA 3/8 institutional micro-scalp with tight 8pt SL, 1:2.0 RR, and aggressive 0.8R trailing breakeven for high winrate.",
}
