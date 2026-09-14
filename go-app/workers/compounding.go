package workers

import (
	"math"
	"strings"
)

// RiskProfile represents the user/task trading appetite mode.
type RiskProfile string

const (
	RiskProfileUltra      RiskProfile = "ULTRA"
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
	CompoundingCalm              CompoundingProfile = "CALM"               // Calm: Conservative, Drawdown Throttled, 25% max-cap
	CompoundingModerate          CompoundingProfile = "MODERATE"           // Moderate: Balanced, Milestone Step-Up, 50% max-cap
	CompoundingAggressive        CompoundingProfile = "AGGRESSIVE"         // Aggressive: Kelly Fractional, 70% max-cap
	CompoundingBeast             CompoundingProfile = "BEAST"              // Beast: High Velocity, Rapid Multiplier, 85% max-cap
	CompoundingUltra             CompoundingProfile = "ULTRA"              // Ultra: Max Velocity, Full Reinvestment, 100% max-cap
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
	case "ULTRA":
		return RiskProfileUltra
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
	case maxLotsCap >= 75 || maxRiskPct >= 7.0:
		return RiskProfileUltra
	case maxLotsCap >= 50 || maxRiskPct >= 5.0:
		return RiskProfileBeast
	case maxLotsCap >= 25 || maxRiskPct >= 3.5:
		return RiskProfileExtreme
	case maxLotsCap >= 15 || maxRiskPct >= 2.5:
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
			case "CALM":
				profile = CompoundingCalm
			case "MODERATE":
				profile = CompoundingModerate
			case "AGGRESSIVE":
				profile = CompoundingAggressive
			case "BEAST":
				profile = CompoundingBeast
			case "ULTRA":
				profile = CompoundingUltra
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
				profile = CompoundingModerate
			}
		} else {
			profile = CompoundingModerate
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
	case CompoundingCalm:
		// Calm Profile: Conservative growth with continuous drawdown dampening
		// 1. Scales lot size with capital growth dampened by peak-drawdown
		ddPct := 0.0
		if c.PeakCapital > 0 && c.CurrentCapital < c.PeakCapital {
			ddPct = (c.PeakCapital - c.CurrentCapital) / c.PeakCapital
		}
		retentionRatio := math.Max(0.10, 1.0-(ddPct*1.5)) // 1.5x penalty on drawdown
		scaledLots := float64(c.BaseLots) * capitalRatio * retentionRatio
		lots = int(math.Max(1, math.Floor(scaledLots)))

		// Hard Calm limit: 25% of MaxLotsCap
		calmCap := math.Max(1.0, math.Floor(float64(c.MaxLotsCap)*0.25))
		if float64(lots) > calmCap {
			lots = int(calmCap)
		}

	case CompoundingModerate, CompoundingStepUp:
		// Moderate Profile: Balanced Milestone Step-Up (every profitStep milestone gains 1 lot)
		netProfit := c.CurrentCapital - c.InitialCapital
		if netProfit > 0 && c.CompoundingProfitStep > 0 {
			stepIncrements := int(math.Floor(netProfit / c.CompoundingProfitStep))
			lots = c.BaseLots + stepIncrements
		}
		// Moderate limit: 50% of MaxLotsCap
		moderateCap := math.Max(float64(c.BaseLots), math.Floor(float64(c.MaxLotsCap)*0.50))
		if float64(lots) > moderateCap {
			lots = int(moderateCap)
		}

	case CompoundingAggressive, CompoundingFixedFraction:
		// Aggressive Profile: Dynamic Kelly Fractional Risk per trade
		if estimatedPremium > 0 && c.LotSize > 0 {
			riskPct := math.Max(c.MaxRiskPerTradePct, 3.0) // baseline 3% for Aggressive
			allowedRiskCapital := c.CurrentCapital * (riskPct / 100.0)
			maxUtilizedCapital := c.CurrentCapital * (c.MaxCapitalUtilPct / 100.0)
			costPerLot := estimatedPremium * float64(c.LotSize)

			lotsByUtil := int(math.Floor(maxUtilizedCapital / costPerLot))
			riskPerLot := costPerLot * (riskPct / 100.0)
			if riskPerLot <= 0 {
				riskPerLot = costPerLot * 0.25
			}
			lotsByRisk := int(math.Floor(allowedRiskCapital / riskPerLot))
			calculatedLots := int(math.Min(float64(lotsByUtil), float64(lotsByRisk)))
			if calculatedLots > 0 {
				lots = calculatedLots
			}
		}
		// Aggressive limit: 70% of MaxLotsCap
		aggCap := math.Max(float64(c.BaseLots), math.Floor(float64(c.MaxLotsCap)*0.70))
		if float64(lots) > aggCap {
			lots = int(aggCap)
		}

	case CompoundingBeast:
		// Beast Profile: High-Velocity Exponential Compounding
		// Base lots grow directly with capital ratio, with bonus allocation when on winning runs
		rawLots := float64(c.BaseLots) * math.Pow(capitalRatio, 1.15)
		lots = int(math.Max(1, math.Floor(rawLots)))

		// Beast limit: 85% of MaxLotsCap
		beastCap := math.Max(float64(c.BaseLots), math.Floor(float64(c.MaxLotsCap)*0.85))
		if float64(lots) > beastCap {
			lots = int(beastCap)
		}

	case CompoundingUltra, CompoundingFull:
		// Ultra Profile: Max Velocity, 100% Capital Reinvestment to Hard Ceiling
		rawLots := float64(c.BaseLots) * capitalRatio
		lots = int(math.Max(1, math.Floor(rawLots)))

		// Ultra limit: Full 100% of MaxLotsCap
		if c.MaxLotsCap > 0 && lots > c.MaxLotsCap {
			lots = c.MaxLotsCap
		}

	case CompoundingEOD:
		// Reinvest proportional to current capital
		lots = int(math.Floor(float64(c.BaseLots) * capitalRatio))

	case CompoundingDrawdownThrottled:
		if c.PeakCapital > 0 {
			ddPct := (c.PeakCapital - c.CurrentCapital) / c.PeakCapital
			if ddPct > 0 {
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
