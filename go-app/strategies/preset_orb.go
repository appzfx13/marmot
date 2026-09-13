package strategies

// ORBBreakoutPreset provides opening range breakout preset with confirmed displacement above 60%.
var ORBBreakoutPreset = StrategyConfig{
	Name:            "ORB Breakout 1:2",
	EMAFast:         9,
	EMASlow:         21,
	RR:              2.0,
	SLPts:           20.0,
	MinDisplacement: 0.60,
	EntryWindowFrom: 9*60 + 30,
	EntryWindowTo:   12 * 60,
	UseORBFilter:    true,
	TrailBreakeven:  false,
	BreakevenAtR:    0,
	CooldownSeconds: 600,
	OrderType:       "MARKET",
	Description:     "ORB breakout only before noon. Wider SL with confirmed displacement above 60%.",
}
