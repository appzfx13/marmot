package strategies

// MomentumScalpPreset provides the default 1:2.5 EMA 9/21 momentum scalp configuration.
var MomentumScalpPreset = StrategyConfig{
	Name:            "Momentum Scalp 1:2.5",
	EMAFast:         9,
	EMASlow:         21,
	RR:              2.5,
	SLPts:           12.0,
	MinDisplacement: 0.50,
	EntryWindowFrom: 9*60 + 20,
	EntryWindowTo:   15 * 60,
	UseORBFilter:    true,
	TrailBreakeven:  true,
	BreakevenAtR:    1.2,
	CooldownSeconds: 300,
	OrderType:       "MARKET",
	Description:     "EMA 9/21 momentum crossover with ORB midpoint filter. 1:2.5 RR, trailing breakeven at 1.2R.",
}

// IntradayMomentumPreset provides standard intraday momentum scalp configuration with square-off at 14:45.
var IntradayMomentumPreset = StrategyConfig{
	Name:            "Intraday Momentum 1:2.5",
	EMAFast:         9,
	EMASlow:         21,
	RR:              2.5,
	SLPts:           12.0,
	MinDisplacement: 0.50,
	EntryWindowFrom: 9*60 + 20,
	EntryWindowTo:   14*60 + 45,
	UseORBFilter:    true,
	TrailBreakeven:  true,
	BreakevenAtR:    1.2,
	CooldownSeconds: 300,
	OrderType:       "MARKET",
	Description:     "Standard intraday momentum scalp. Square-off before 14:45.",
}

// MorningTrendPreset provides first-hour momentum capture setup.
var MorningTrendPreset = StrategyConfig{
	Name:            "Morning Trend 1:2",
	EMAFast:         9,
	EMASlow:         21,
	RR:              2.0,
	SLPts:           10.0,
	MinDisplacement: 0.55,
	EntryWindowFrom: 9*60 + 20,
	EntryWindowTo:   11 * 60,
	UseORBFilter:    true,
	TrailBreakeven:  false,
	BreakevenAtR:    0,
	CooldownSeconds: 600,
	OrderType:       "MARKET",
	Description:     "First-hour momentum capture only. Tight SL 10pts, 1:2 RR.",
}

// MomentumGuardrailPreset provides wider displacement threshold with risk guardrail.
var MomentumGuardrailPreset = StrategyConfig{
	Name:            "Professional Momentum Guardrail 1:2.5",
	EMAFast:         9,
	EMASlow:         21,
	RR:              2.5,
	SLPts:           15.0,
	MinDisplacement: 0.60,
	EntryWindowFrom: 9*60 + 30,
	EntryWindowTo:   14*60 + 30,
	UseORBFilter:    true,
	TrailBreakeven:  true,
	BreakevenAtR:    1.5,
	CooldownSeconds: 360,
	OrderType:       "MARKET",
	Description:     "Guardrail version: wider displacement threshold, later window close, trail at 1.5R.",
}
