package services

import (
	"math"
)

// GreekMetrics holds computed BSM values.
type GreekMetrics struct {
	Price float64 `json:"price"`
	IV    float64 `json:"iv"`
	Delta float64 `json:"delta"`
	Gamma float64 `json:"gamma"`
	Theta float64 `json:"theta"`
	Vega  float64 `json:"vega"`
	Bid   float64 `json:"bid"`
	Ask   float64 `json:"ask"`
}

func normCDF(x float64) float64 {
	return (1.0 + math.Erf(x/math.Sqrt2)) / 2.0
}

func normPDF(x float64) float64 {
	return math.Exp(-0.5*x*x) / math.Sqrt(2.0*math.Pi)
}

// BSMPriceAndGreeks evaluates closed-form Black-Scholes price and first/second order Greeks.
// r: risk-free rate (e.g. 0.07 for 7% MIBOR/repo rate)
// T: time to expiry in years (e.g. 4.0 / 365.0)
func BSMPriceAndGreeks(S, K, T, r, sigma float64, isCall bool) GreekMetrics {
	if S <= 0 || K <= 0 {
		return GreekMetrics{}
	}

	if T <= 0.00002 { // < ~10 minutes to expiry
		intrinsic := 0.0
		delta := 0.0
		if isCall {
			if S > K {
				intrinsic = S - K
				delta = 1.0
			}
		} else {
			if K > S {
				intrinsic = K - S
				delta = -1.0
			}
		}
		return GreekMetrics{
			Price: intrinsic,
			IV:    sigma,
			Delta: delta,
			Gamma: 0.0,
			Theta: 0.0,
			Vega:  0.0,
		}
	}

	if sigma <= 0.0001 {
		sigma = 0.0001
	}

	sqrtT := math.Sqrt(T)
	d1 := (math.Log(S/K) + (r+0.5*sigma*sigma)*T) / (sigma * sqrtT)
	d2 := d1 - sigma*sqrtT

	pdf1 := normPDF(d1)
	cdf1 := normCDF(d1)
	cdf2 := normCDF(d2)

	gamma := pdf1 / (S * sigma * sqrtT)
	vega := (S * sqrtT * pdf1) / 100.0 // Change in ₹ per 1% change in vol

	var price, delta, theta float64
	discK := K * math.Exp(-r*T)

	if isCall {
		price = S*cdf1 - discK*cdf2
		delta = cdf1
		// Calendar-day theta (/ 365.0)
		theta = (-(S*pdf1*sigma)/(2.0*sqrtT) - r*discK*cdf2) / 365.0
	} else {
		price = discK*normCDF(-d2) - S*normCDF(-d1)
		delta = cdf1 - 1.0
		theta = (-(S*pdf1*sigma)/(2.0*sqrtT) + r*discK*normCDF(-d2)) / 365.0
	}

	return GreekMetrics{
		Price: price,
		IV:    sigma,
		Delta: delta,
		Gamma: gamma,
		Theta: theta,
		Vega:  vega,
	}
}

// SolveIV uses Newton-Raphson to solve for the Implied Volatility that matches targetPrice.
func SolveIV(S, K, T, r, targetPrice float64, isCall bool) float64 {
	if targetPrice <= 0.05 || S <= 0 || K <= 0 || T <= 0.00002 {
		return 0.15 // default 15% IV baseline
	}

	// Intrinsic value bound check
	intrinsic := 0.0
	if isCall {
		if S > K {
			intrinsic = S - K
		}
	} else {
		if K > S {
			intrinsic = K - S
		}
	}
	if targetPrice < intrinsic {
		targetPrice = intrinsic + 0.05
	}

	sigma := 0.20 // 20% initial guess
	for i := 0; i < 25; i++ {
		metrics := BSMPriceAndGreeks(S, K, T, r, sigma, isCall)
		diff := metrics.Price - targetPrice
		if math.Abs(diff) < 0.01 {
			return sigma
		}

		sqrtT := math.Sqrt(T)
		d1 := (math.Log(S/K) + (r+0.5*sigma*sigma)*T) / (sigma * sqrtT)
		vegaRaw := S * sqrtT * normPDF(d1)

		if vegaRaw < 1e-4 {
			break
		}

		step := diff / vegaRaw
		sigma -= step

		if sigma < 0.01 {
			sigma = 0.01
		} else if sigma > 3.0 {
			sigma = 3.0
			break
		}
	}

	return sigma
}

// ComputeCompleteOptionMetrics solves IV and computes all Greeks and simulated Bid/Ask spreads.
func ComputeCompleteOptionMetrics(S, K, T, r, marketPrice float64, isCall bool, volume int64) GreekMetrics {
	sigma := SolveIV(S, K, T, r, marketPrice, isCall)
	metrics := BSMPriceAndGreeks(S, K, T, r, sigma, isCall)
	metrics.IV = sigma * 100.0 // Return percentage (e.g. 15.5%)

	// Realistic Liquidity & Bid/Ask Spreads for Backtesting
	// Wider spread for low volume/deep OTM, tighter spread for liquid ATM
	spreadPct := 0.003 // 0.3% base spread
	if volume < 5000 {
		spreadPct = 0.015 // 1.5% spread for illiquid strikes
	} else if volume < 50000 {
		spreadPct = 0.008
	}

	halfSpread := (marketPrice * spreadPct) / 2.0
	if halfSpread < 0.05 {
		halfSpread = 0.05 // Minimum exchange tick size ₹0.05
	}

	metrics.Bid = math.Max(0.05, marketPrice-halfSpread)
	metrics.Ask = marketPrice + halfSpread

	return metrics
}
