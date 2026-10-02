package parquet

import (
	"testing"
)

func TestLoadVixSnapshots(t *testing.T) {
	filePath := "/app/backup/1/6/vix_15m_INDIAVIX.parquet"
	minMap, dayMap, err := LoadVixSnapshots(filePath)
	if err != nil {
		t.Skipf("Skipping test, vix file not found: %v", err)
		return
	}

	if len(dayMap) == 0 {
		t.Fatalf("Expected days in VIX map, got 0")
	}

	t.Logf("Loaded VIX: %d minute/hour keys, %d day keys", len(minMap), len(dayMap))
	for d, val := range dayMap {
		t.Logf("Sample day: %s => VIX %.2f", d, val)
		break
	}
}
