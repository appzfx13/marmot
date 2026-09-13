package workers

import (
	"testing"
)

func TestResolveRiskProfile(t *testing.T) {
	tests := []struct {
		name        string
		profileStr  string
		maxLotsCap  int
		maxRiskPct  float64
		expected    RiskProfile
	}{
		{"Explicit Beast", "beast", 10, 2.0, RiskProfileBeast},
		{"Explicit Extreme", "EXTREME", 10, 2.0, RiskProfileExtreme},
		{"Dynamic Beast via Lots", "", 55, 2.0, RiskProfileBeast},
		{"Dynamic Beast via Risk", "", 10, 8.5, RiskProfileBeast},
		{"Dynamic Extreme via Lots", "", 28, 2.0, RiskProfileExtreme},
		{"Dynamic Extreme via Risk", "", 10, 5.5, RiskProfileExtreme},
		{"Dynamic Aggressive via Lots", "", 18, 2.0, RiskProfileAggressive},
		{"Dynamic Aggressive via Risk", "", 10, 3.8, RiskProfileAggressive},
		{"Dynamic Calm", "", 5, 1.2, RiskProfileCalm},
		{"Dynamic Moderate Default", "", 10, 2.0, RiskProfileModerate},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := ResolveRiskProfile(tt.profileStr, tt.maxLotsCap, tt.maxRiskPct)
			if got != tt.expected {
				t.Errorf("ResolveRiskProfile(%q, %d, %f) = %v, expected %v",
					tt.profileStr, tt.maxLotsCap, tt.maxRiskPct, got, tt.expected)
			}
		})
	}
}

func TestCompoundingEngine(t *testing.T) {
	params := map[string]interface{}{
		"lots_count":              1,
		"max_lots_cap":            20,
		"enable_ai_compounding":   true,
		"compounding_profile":     "STEP_UP",
		"compounding_profit_step": 25000.0,
		"risk_profile":            "BEAST",
	}

	engine := NewCompoundingEngine(100000.0, params)
	if engine.Profile != CompoundingStepUp {
		t.Fatalf("Expected CompoundingStepUp, got %v", engine.Profile)
	}
	if engine.RiskProfile != RiskProfileBeast {
		t.Fatalf("Expected RiskProfileBeast, got %v", engine.RiskProfile)
	}

	// Initial lots should be 1
	lots := engine.CalculateLotSize(100.0)
	if lots != 1 {
		t.Errorf("Expected 1 lot initially, got %d", lots)
	}

	// Add 30,000 PnL -> should step up by 1 lot
	engine.UpdatePnL(30000.0)
	lots = engine.CalculateLotSize(100.0)
	if lots != 2 {
		t.Errorf("Expected 2 lots after 30k profit step, got %d", lots)
	}

	// Add another 30,000 PnL (total 60k) -> should step up to 3 lots
	engine.UpdatePnL(30000.0)
	lots = engine.CalculateLotSize(100.0)
	if lots != 3 {
		t.Errorf("Expected 3 lots after 60k profit step, got %d", lots)
	}
}
