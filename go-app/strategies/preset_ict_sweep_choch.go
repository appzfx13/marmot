package strategies

// ICTSweepCHoCHPreset provides ICT liquidity sweep detection (BSL/SSL)
// followed by Change of Character (CHoCH / MSS) and limit retest entry.
// Strictly Intraday Only (09:20 - 14:45 IST, squareoff before 15:25, zero overnight carry).
var ICTSweepCHoCHPreset = StrategyConfig{
	Name:                 "ICT Liquidity Sweep + CHoCH Retest",
	EMAFast:              9,
	EMASlow:              21,
	RR:                   2.5,
	SLPts:                12.0,
	MinDisplacement:      0.45,
	EntryWindowFrom:      9*60 + 20, // 09:20 IST
	EntryWindowTo:        14*60 + 45, // 14:45 IST (Strictly Intraday Only)
	UseORBFilter:         false,
	TrailBreakeven:       true,
	BreakevenAtR:         1.0,
	TSL2_At_R:            1.8,
	TSL2_Lock_R:          1.0,
	CooldownSeconds:      120,
	OrderType:            "LIMIT",
	Description:          "ICT Liquidity Sweep (BSL/SSL) followed by CHoCH market structure shift and limit order retest entry with optional multi-layer scaling. Strictly Intraday.",
	EnableRetestLayering: false,
	LayerCount:           3,
	RetestPercentages:    []float64{25.0, 50.0, 75.0},
	LayerLots:            []int{1, 1, 1},
}
