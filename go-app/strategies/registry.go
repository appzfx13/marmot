package strategies

import "strings"

// strategyRegistry holds all registered plug-and-play strategy instances.
var strategyRegistry = map[string]Strategy{
	"ict_smc":     NewICTSMCStrategy(),
	"gamma_blast": NewGammaBlastStrategy(),
	"candle_3pm":  NewCandle3PMStrategy(),
}

// GetStrategy resolves a plug-and-play strategy instance by its strategy_name.
func GetStrategy(name string) (Strategy, bool) {
	key := strings.ToLower(strings.TrimSpace(name))
	strat, ok := strategyRegistry[key]
	return strat, ok
}

// ListRegisteredStrategies returns a slice of all available strategy names.
func ListRegisteredStrategies() []string {
	names := make([]string, 0, len(strategyRegistry))
	for name := range strategyRegistry {
		names = append(names, name)
	}
	return names
}
