package workers

import (
	"testing"
	"time"
)

func TestGenerateIndexExpiries(t *testing.T) {
	ist, _ := time.LoadLocation("Asia/Kolkata")

	// Test 1: NIFTY for 2026-10-08 (Thursday) to 2026-10-09 (Friday)
	// Must return both 2026-10-08 and 2026-10-15
	expiries := generateIndexExpiries("NIFTY", "2026-10-08", "2026-10-09", ist)
	if len(expiries) != 2 {
		t.Fatalf("expected 2 expiries for 2026-10-08 to 2026-10-09, got %d: %v", len(expiries), expiries)
	}

	exp1 := expiries[0].Format("2006-01-02")
	exp2 := expiries[1].Format("2006-01-02")

	if exp1 != "2026-10-08" || exp2 != "2026-10-15" {
		t.Fatalf("expected [2026-10-08, 2026-10-15], got [%s, %s]", exp1, exp2)
	}

	// Test 2: Mid-week trade dates without an expiry (Monday to Tuesday: 2026-10-05 to 2026-10-06)
	// Must resolve upcoming Thursday 2026-10-08
	midweekExpiries := generateIndexExpiries("NIFTY", "2026-10-05", "2026-10-06", ist)
	if len(midweekExpiries) != 1 {
		t.Fatalf("expected 1 expiry for midweek dates, got %d: %v", len(midweekExpiries), midweekExpiries)
	}
	if midweekExpiries[0].Format("2006-01-02") != "2026-10-08" {
		t.Fatalf("expected upcoming Thursday 2026-10-08, got %s", midweekExpiries[0].Format("2006-01-02"))
	}
}
