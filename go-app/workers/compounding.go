package workers

import (
	"math"
	"strings"
)

// RiskProfile represents the user/task trading appetite mode.
type RiskProfile string

const (
	RiskProfileBeast      RiskProfile = "BEAST"
	RiskProfileExtreme    RiskProfile = "EXTREME"
	RiskProfileAggressive RiskProfile = "AGGRESSIVE"
	RiskProfileModerate   RiskProfile = "MODERATE"
	RiskProfileCalm       RiskProfile = "CALM"
)

// CompoundingProfile defines the capital reinvestment mechanism.
type CompoundingProfile string

const (
	CompoundingFixed             CompoundingProfile = "FIXED"              // No compounding: fixed lot size
	CompoundingFull              CompoundingProfile = "FULL"               // Reinvest all net profits immediately
	CompoundingEOD               CompoundingProfile = "EOD"                // Reinvest once daily after market close
	CompoundingFixedFraction     CompoundingProfile = "FIXED_FRACTION"     // Kelly/Fixed fractional risk per trade
	CompoundingDrawdownThrottled CompoundingProfile = "DRAWDOWN_THROTTLED" // Throttle lot size as drawdown increases
	CompoundingStepUp            CompoundingProfile = "STEP_UP"            // Add lots when profit hits milestone batch step
)

// ResolveRiskProfile matches Marmot Django logic:
// Checks params["risk_profile"], else computes from max_lots_cap and max_risk_per_trade_pct.
func ResolveRiskProfile(profileStr string, maxLotsCap int, maxRiskPct float64) RiskProfile {
	cleaned := strings.ToUpper(strings.TrimSpace(profileStr))
	switch cleaned {
	case "BEAST":
		return RiskProfileBeast
	case "EXTREME":
		return RiskProfileExtreme
	case "AGGRESSIVE":
		return RiskProfileAggressive
	case "CALM":
		return RiskProfileCalm
	case "MODERATE":
		return RiskProfileModerate
	}

	// Fallback dynamic threshold evaluation
	switch {
	case maxLotsCap >= 50 || maxRiskPct >= 8.0:
		return RiskProfileBeast
	case maxLotsCap >= 25 || maxRiskPct >= 5.0:
		return RiskProfileExtreme
	case maxLotsCap >= 15 || maxRiskPct >= 3.5:
		return RiskProfileAggressive
	case maxLotsCap <= 5 && maxRiskPct <= 1.5:
		return RiskProfileCalm
	default:
		return RiskProfileModerate
	}
}

// CompoundingConfig holds configuration for sizing and capital updates.
type CompoundingConfig struct {
	Profile                CompoundingProfile
	RiskProfile            RiskProfile
	InitialCapital         float64
	CurrentCapital         float64
	PeakCapital            float64
	BaseLots               int
	MaxLotsCap             int
	LotSize                int
	MaxRiskPerTradePct     float64
	MaxCapitalUtilPct      float64
	CompoundingBatchTrades int
	CompoundingProfitStep  float64
	EnableAICompounding    bool
	TradeCount             int
}

// NewCompoundingEngine initializes a CompoundingConfig from task parameters.
func NewCompoundingEngine(initialCapital float64, params map[string]interface{}) *CompoundingConfig {
	if initialCapital <= 0 {
		initialCapital = 100000.0
	}

	baseLots := 1
	if bl, ok := params["lots_count"].(float64); ok && bl > 0 {
		baseLots = int(bl)
	} else if blInt, ok := params["lots_count"].(int); ok && blInt > 0 {
		baseLots = blInt
	}

	maxLotsCap := 10
	if ml, ok := params["max_lots_cap"].(float64); ok && ml > 0 {
		maxLotsCap = int(ml)
	} else if mlInt, ok := params["max_lots_cap"].(int); ok && mlInt > 0 {
		maxLotsCap = mlInt
	}

	maxRiskPct := 2.0
	if mr, ok := params["max_risk_per_trade_pct"].(float64); ok && mr > 0 {
		maxRiskPct = mr
	}

	maxCapUtil := 60.0
	if cu, ok := params["max_capital_utilization_pct"].(float64); ok && cu > 0 {
		maxCapUtil = cu
	}

	lotSize := 65
	if ls, ok := params["lot_size"].(float64); ok && ls > 0 {
		lotSize = int(ls)
	} else if lsInt, ok := params["lot_size"].(int); ok && lsInt > 0 {
		lotSize = lsInt
	}

	var riskStr string
	if rp, ok := params["risk_profile"].(string); ok {
		riskStr = rp
	}
	riskProfile := ResolveRiskProfile(riskStr, maxLotsCap, maxRiskPct)

	enableCompounding := false
	if ec, ok := params["enable_ai_compounding"].(bool); ok {
		enableCompounding = ec
	}

	batchTrades := 30
	if bt, ok := params["compounding_batch_trades"].(float64); ok && bt > 0 {
		batchTrades = int(bt)
	} else if btInt, ok := params["compounding_batch_trades"].(int); ok && btInt > 0 {
		batchTrades = btInt
	}

	// Profit step defaults to 25% of initial capital if not specified
	profitStep := initialCapital * 0.25
	if ps, ok := params["compounding_profit_step"].(float64); ok && ps > 0 {
		profitStep = ps
	} else if psPct, ok := params["compounding_profit_step_pct"].(float64); ok && psPct > 0 {
		profitStep = initialCapital * (psPct / 100.0)
	}

	profile := CompoundingFixed
	if enableCompounding {
		if cpStr, ok := params["compounding_profile"].(string); ok && cpStr != "" {
			switch strings.ToUpper(strings.TrimSpace(cpStr)) {
			case "FULL":
				profile = CompoundingFull
			case "EOD":
				profile = CompoundingEOD
			case "FIXED_FRACTION", "KELLY":
				profile = CompoundingFixedFraction
			case "DRAWDOWN_THROTTLED", "THROTTLED":
				profile = CompoundingDrawdownThrottled
			case "STEP_UP", "BATCH":
				profile = CompoundingStepUp
			default:
				profile = CompoundingStepUp
			}
		} else {
			profile = CompoundingStepUp
		}
	}

	return &CompoundingConfig{
		Profile:                profile,
		RiskProfile:            riskProfile,
		InitialCapital:         initialCapital,
		CurrentCapital:         initialCapital,
		PeakCapital:            initialCapital,
		BaseLots:               baseLots,
		MaxLotsCap:             maxLotsCap,
		LotSize:                lotSize,
		MaxRiskPerTradePct:     maxRiskPct,
		MaxCapitalUtilPct:      maxCapUtil,
		CompoundingBatchTrades: batchTrades,
		CompoundingProfitStep:  profitStep,
		EnableAICompounding:    enableCompounding,
		TradeCount:             0,
	}
}

// CalculateLotSize calculates the trade lot count based on compounding profile, current capital, and risk parameters strictly using percentages.
func (c *CompoundingConfig) CalculateLotSize(estimatedPremium float64) int {
	if !c.EnableAICompounding || c.Profile == CompoundingFixed {
		return c.BaseLots
	}

	lots := c.BaseLots
	capitalRatio := c.CurrentCapital / c.InitialCapital
	if capitalRatio <= 0 {
		return 1
	}

	switch c.Profile {
	case CompoundingFull:
		// Sizing grows strictly proportional to percentage capital growth
		lots = int(math.Floor(float64(c.BaseLots) * capitalRatio))

	case CompoundingStepUp:
		// Step up lots based on percentage milestones
		netProfit := c.CurrentCapital - c.InitialCapital
		if netProfit > 0 && c.CompoundingProfitStep > 0 {
			stepIncrements := int(math.Floor(netProfit / c.CompoundingProfitStep))
			lots = c.BaseLots + stepIncrements
		}

	case CompoundingFixedFraction:
		// Dynamic Risk Percentage model:
		// Max allowed risk = CurrentCapital * (MaxRiskPerTradePct / 100)
		// Max capital committed = CurrentCapital * (MaxCapitalUtilPct / 100)
		if estimatedPremium > 0 && c.LotSize > 0 {
			allowedRiskCapital := c.CurrentCapital * (c.MaxRiskPerTradePct / 100.0)
			maxUtilizedCapital := c.CurrentCapital * (c.MaxCapitalUtilPct / 100.0)
			costPerLot := estimatedPremium * float64(c.LotSize)

			// Max lots allowed by capital utilization percentage
			lotsByUtil := int(math.Floor(maxUtilizedCapital / costPerLot))

			// Max lots allowed by risk percentage (assuming standard 25% option premium stoploss risk)
			riskPerLot := costPerLot * (c.MaxRiskPerTradePct / 100.0)
			if riskPerLot <= 0 {
				riskPerLot = costPerLot * 0.25
			}
			lotsByRisk := int(math.Floor(allowedRiskCapital / riskPerLot))

			calculatedLots := int(math.Min(float64(lotsByUtil), float64(lotsByRisk)))
			if calculatedLots > 0 {
				lots = calculatedLots
			}
		}

	case CompoundingDrawdownThrottled:
		// Continuous percentage-based drawdown dampening:
		// Sizing scales down smoothly with the percentage drawdown from peak capital
		if c.PeakCapital > 0 {
			ddPct := (c.PeakCapital - c.CurrentCapital) / c.PeakCapital
			if ddPct > 0 {
				// Retention ratio: 1.0 - ddPct (e.g. 10% DD retains 90% lot sizing capacity)
				retentionRatio := math.Max(0.10, 1.0-ddPct)
				scaledLots := float64(c.BaseLots) * capitalRatio * retentionRatio
				lots = int(math.Max(1, math.Floor(scaledLots)))
			} else {
				lots = int(math.Floor(float64(c.BaseLots) * capitalRatio))
			}
		}
	default:
		lots = c.BaseLots
	}

	// Apply RiskProfile percentage caps strictly based on MaxLotsCap
	maxCap := float64(c.MaxLotsCap)
	base := float64(c.BaseLots)

	switch c.RiskProfile {
	case RiskProfileBeast:
		// 100% of MaxLotsCap
		lots = int(math.Min(float64(lots), maxCap))
	case RiskProfileExtreme:
		// 85% of MaxLotsCap
		lots = int(math.Min(float64(lots), math.Max(base, math.Floor(maxCap*0.85))))
	case RiskProfileAggressive:
		// 70% of MaxLotsCap
		lots = int(math.Min(float64(lots), math.Max(base, math.Floor(maxCap*0.70))))
	case RiskProfileModerate:
		// 50% of MaxLotsCap
		lots = int(math.Min(float64(lots), math.Max(base, math.Floor(maxCap*0.50))))
	case RiskProfileCalm:
		// 25% of MaxLotsCap
		lots = int(math.Min(float64(lots), math.Max(1.0, math.Floor(maxCap*0.25))))
	default:
		lots = int(math.Min(float64(lots), math.Max(base, math.Floor(maxCap*0.50))))
	}

	if lots < 1 {
		lots = 1
	}
	if c.MaxLotsCap > 0 && lots > c.MaxLotsCap {
		lots = c.MaxLotsCap
	}

	return lots
}

// UpdatePnL records trade result and updates running capital, peak capital, and trade count.
func (c *CompoundingConfig) UpdatePnL(pnl float64) {
	c.TradeCount++
	c.CurrentCapital += pnl
	if c.CurrentCapital > c.PeakCapital {
		c.PeakCapital = c.CurrentCapital
	}
}
