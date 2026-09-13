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
