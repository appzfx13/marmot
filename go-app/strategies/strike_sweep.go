package strategies

import (
	"fmt"
	"math"
	"strings"
)

// StrikeCandidate holds the result for one swept option strike.
type StrikeCandidate struct {
	Key           string  // Options map key e.g. "23650 CALL"
	TradingSymbol string  // Full broker symbol e.g. "NIFTY 24OCT25 23650 CE"
	LimitPrice    float64 // Optimal limit entry price
	Premium       float64 // Option close / LTP
	Volume        int64   // Volume
	OI            int64   // Open Interest
	Bid           float64 // Best Bid
	Ask           float64 // Best Ask
	SpreadPct     float64 // Bid-Ask spread as % of premium
	Liquidity     int64   // Effective liquidity score (Volume + OI in live, Volume in backtest)
	Offset        int     // Strike offset from ATM (0=ATM, 1=ATM+1, etc.)
}

// premiumWindowForIndex returns the ideal option premium range [min, max] for an index.
// Strikes outside this window are filtered as junk (too cheap OTM) or too expensive (deep ITM).
func premiumWindowForIndex(indexName string) (float64, float64) {
	switch strings.ToUpper(indexName) {
	case "BANKNIFTY", "SENSEX", "BANKEX":
		return 80.0, 600.0
	case "FINNIFTY":
		return 40.0, 400.0
	case "MIDCPNIFTY":
		return 20.0, 200.0
	default: // NIFTY, GIFTNIFTY
		return 40.0, 350.0
	}
}

// limitPriceForSnap computes the optimal limit entry price.
// Live mode: true mid-price (Bid+Ask)/2. Backtest fallback: Close×0.995.
func limitPriceForSnap(snap OptionSnap) float64 {
	if snap.Bid > 0 && snap.Ask > 0 {
		return math.Round(((snap.Bid+snap.Ask)/2.0)*100) / 100
	}
	return math.Round(snap.Close*0.995*100) / 100
}

// SweepStrikesForBestEntry sweeps ATM±3 option strikes and returns the best entry candidate.
//
// Selection logic (Adaptive 4-step):
//  1. HARD GATE 1 — discard strikes outside the ideal premium window
//  2. HARD GATE 2 (Live) — discard strikes with wide bid-ask spread (> 5% of premium)
//  3. RANK        — pick highest liquidity (Volume + OI in live mode; Volume in backtest)
//  4. TIEBREAK    — prefer strike closest to ATM (lower absolute offset)
//
// Returns nil if no valid candidate found — caller falls back to ATM at market price.
func SweepStrikesForBestEntry(
	options map[string]OptionSnap,
	atmStrike int,
	optType string, // "CALL" or "PUT"
	strikeStep int,
	indexName string,
	activeExpiry string,
) *StrikeCandidate {
	if len(options) == 0 || strikeStep <= 0 {
		return nil
	}

	pMin, pMax := premiumWindowForIndex(indexName)
	var best *StrikeCandidate

	for offset := -3; offset <= 3; offset++ {
		strike := atmStrike + (offset * strikeStep)

		// Resolve snap — prefer numeric key, fall back to ATM-relative alias
		numKey := fmt.Sprintf("%d %s", strike, optType)
		snap, ok := options[numKey]
		if !ok || snap.Close <= 0 {
			var relKey string
			switch {
			case offset == 0:
				relKey = "ATM " + optType
			case offset > 0:
				relKey = fmt.Sprintf("ATM+%d %s", offset, optType)
			default:
				relKey = fmt.Sprintf("ATM-%d %s", -offset, optType)
			}
			snap, ok = options[relKey]
			if !ok || snap.Close <= 0 {
				continue
			}
			numKey = relKey
		}

		// Step 1: Hard gate — premium window
		if snap.Close < pMin || snap.Close > pMax {
			continue
		}

		// Step 2: Hard gate (Live mode) — skip illiquid strikes with spread > 5%
		var spreadPct float64
		if snap.Bid > 0 && snap.Ask > 0 && snap.Ask >= snap.Bid {
			spread := snap.Ask - snap.Bid
			spreadPct = spread / snap.Close
			if spreadPct > 0.05 {
				continue
			}
		}

		lp := limitPriceForSnap(snap)
		if lp <= 0 {
			continue
		}

		tradingSymbol := fmt.Sprintf("%s %d %s", indexName, strike, optType)
		if activeExpiry != "" {
			tradingSymbol = fmt.Sprintf("%s %s %d %s", indexName, activeExpiry, strike, optType)
		}

		// Composite liquidity: in live mode Volume + OI; in backtest pure Volume
		liquidity := snap.Volume
		if snap.OI > 0 {
			liquidity += snap.OI
		}

		candidate := &StrikeCandidate{
			Key:           numKey,
			TradingSymbol: tradingSymbol,
			LimitPrice:    lp,
			Premium:       snap.Close,
			Volume:        snap.Volume,
			OI:            snap.OI,
			Bid:           snap.Bid,
			Ask:           snap.Ask,
			SpreadPct:     spreadPct,
			Liquidity:     liquidity,
			Offset:        offset,
		}

		if best == nil {
			best = candidate
			continue
		}

		// Step 3: Rank by Liquidity (Volume + OI in live, Volume in backtest)
		if candidate.Liquidity > best.Liquidity {
			best = candidate
			continue
		}

		// Step 4: Tiebreak by ATM proximity (lower absolute offset = better)
		if candidate.Liquidity == best.Liquidity && abs(candidate.Offset) < abs(best.Offset) {
			best = candidate
		}
	}

	return best
}

// abs returns the absolute value of an integer.
func abs(x int) int {
	if x < 0 {
		return -x
	}
	return x
}
