package strategies

import "strings"

// StrategyConfig defines a named, hardcoded Go strategy preset activated by a BacktestRule.rule_type.
type StrategyConfig struct {
	Name            string
	EMAFast         int
	EMASlow         int
	RR              float64
	SLPts           float64
	MinDisplacement float64
	EntryWindowFrom int // minutes from midnight (e.g. 9*60+20 = 560)
	EntryWindowTo   int // minutes from midnight (e.g. 15*60+0 = 900)
	UseORBFilter     bool
	RequireExpiryDay bool
	TrailBreakeven   bool
	BreakevenAtR     float64 // trail SL to entry when profit >= X * initial risk
	CooldownSeconds  int
	OrderType        string // "MARKET" or "LIMIT"
	Description      string
}

var StrategyPresets = map[string]StrategyConfig{
	"momentum_scalp":     MomentumScalpPreset,
	"orb_breakout":       ORBBreakoutPreset,
	"algo_micro_scalp":   MicroScalpPreset,
	"hft_scalp":          HFTScalpPreset,
	"ict_smc_matrix":     ICTSMCPreset,
	"gamma_blast":        GammaBlastPreset,
	"intraday":           IntradayMomentumPreset,
	"morning_trend":      MorningTrendPreset,
	"momentum_guardrail": MomentumGuardrailPreset,
	"macd_crossover":     MACDCrossoverPreset,
	"macd_ict_hybrid":    MACDICTHybridPreset,
}

// GetStrategyPreset returns a StrategyConfig by rule_type key (case-insensitive).
// Falls back to the "momentum_scalp" default if no match is found.
func GetStrategyPreset(ruleType string) StrategyConfig {
	key := strings.ToLower(strings.TrimSpace(ruleType))
	if cfg, ok := StrategyPresets[key]; ok {
		return cfg
	}
	return StrategyPresets["momentum_scalp"]
}

// strategyRegistry holds all registered plug-and-play strategy instances.
var strategyRegistry = map[string]Strategy{
	"quant_engine":    NewQuantEngineStrategy("quant_engine"),
	"orb_momentum":    NewQuantEngineStrategy("orb_momentum"),
	"ict_smc":         NewQuantEngineStrategy("ict_smc"),
	"hft_scalp":       NewQuantEngineStrategy("hft_scalp"),
	"macd_ict_hybrid": NewQuantEngineStrategy("macd_ict_hybrid"),
}

// GetStrategy resolves a plug-and-play strategy instance by its strategy_name.
// If the key is not in strategyRegistry, it falls back to a dynamically instantiated QuantEngineStrategy.
func GetStrategy(name string) (Strategy, bool) {
	key := strings.ToLower(strings.TrimSpace(name))
	if key == "" {
		key = "quant_engine"
	}
	strat, ok := strategyRegistry[key]
	if ok {
		return strat, true
	}
	return NewQuantEngineStrategy(key), true
}


// ListRegisteredStrategies returns a slice of all available strategy names.
func ListRegisteredStrategies() []string {
	names := make([]string, 0, len(strategyRegistry))
	for name := range strategyRegistry {
		names = append(names, name)
	}
	return names
}
