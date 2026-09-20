package config

import "time"

// FYERS API Constants
const (
	FyersBaseHistoryURL    = "https://api-t1.fyers.in/data/history"
	FyersExpiredHistoryURL = "https://api-t1.fyers.in/data/history/fno/expired/historical-data"

	// Resolution Identifiers
	Resolution5S   = "5S"
	Resolution1Min = "1"

	// Black-Scholes & Option Calculation Constants
	DefaultRiskFreeRate = 0.07
	MinTimeFormatFloor  = 0.00002
	DefaultOptionOI     = 100000

	// Default Parameters
	DefaultWorkerCount = 4
	DefaultStrikeCount = 5

	// Index ATM Fallbacks
	DefaultBankNiftyATM = 51000.0
	DefaultFinNiftyATM  = 24000.0
	DefaultSensexATM    = 82000.0
	DefaultNiftyATM     = 23500.0

	// Network & HTTP Transport Constants
	HTTPClientTimeout       = 35 * time.Second
	HTTPMaxIdleConns        = 100
	HTTPMaxIdleConnsPerHost = 20
	HTTPIdleConnTimeout     = 90 * time.Second
	RateLimiterInterval     = 150 * time.Millisecond
)
