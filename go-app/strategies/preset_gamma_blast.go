package strategies

// GammaBlastPreset provides high-precision afternoon gamma blast scalping on expiry days (2:15 PM - 3:15 PM IST).
var GammaBlastPreset = StrategyConfig{
	Name:             "Expiry Gamma Blast 1:3.5 (Hero to Zero)",
	EMAFast:          3,
	EMASlow:          9,
	RR:               3.5,
	SLPts:            8.0,
	MinDisplacement:  0.55,
	EntryWindowFrom:  13*60 + 30, // 13:30 IST (1:30 PM - post 13:30 IST)
	EntryWindowTo:    15*60 + 15, // 15:15 IST (3:15 PM)
	UseORBFilter:     false,      // Afternoon momentum breakout ignores opening morning range
	RequireExpiryDay: true,       // Strictly executes on exchange expiry days only
	TrailBreakeven:   true,
	BreakevenAtR:     1.0,
	CooldownSeconds:  120, // 2-min fast reaction cooldown
	OrderType:        "MARKET",
	Description:      "Expiry day 14:15-15:15 IST gamma blast micro-scalper. EMA 3/9 fast crossover with 70%+ displacement, 8pt tight SL, and 1:3.5 high RR target.",
}
