package strategies

// ICTSMCPreset provides ICT displacement with limit order retest entry.
var ICTSMCPreset = StrategyConfig{
	Name:            "ICT Smart Money 1:2 (Limit Retest)",
	EMAFast:         9,
	EMASlow:         21,
	RR:              2.0,
	SLPts:           15.0,
	MinDisplacement: 0.65,
	EntryWindowFrom: 9*60 + 20,
	EntryWindowTo:   15 * 60,
	UseORBFilter:    true,
	TrailBreakeven:  true,
	BreakevenAtR:    1.5,
	CooldownSeconds: 300,
	OrderType:       "LIMIT",
	Description:     "ICT displacement 65%+ with limit retest entry. 1:2 RR, trail at 1.5R.",
}
