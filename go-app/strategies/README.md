# Go Strategy Plugin Developer & AI Agent Guide

This directory contains plug-and-play strategy modules for the Marmot High-Speed Go Backtest Engine. Developers and AI Agents can create and register new trading strategy modules by implementing the standard `Strategy` interface.

---

## 1. Strategy Plugin Interface Contract (`interface.go`)

Every strategy plugin MUST implement the `Strategy` interface defined in `interface.go`:

```go
package strategies

type Strategy interface {
    GetName() string
    Execute(input StrategyInput) StrategyResult
}
```

### Data Structures

- **`StrategyInput`**:
  - `Date` (`string`): Trading day in `YYYY-MM-DD` format.
  - `IndexName` (`string`): Target index (e.g. `NIFTY`, `BANKNIFTY`, `FINNIFTY`, `MIDCPNIFTY`).
  - `Candles` (`[]map[string]interface{}`): Slice of minute candle maps (`date`, `open`, `high`, `low`, `close`, `volume`).
  - `OptionCandles` (`map[string][]map[string]interface{}`): Strike-wise option candle data.
  - `Params` (`map[string]interface{}`): Custom user strategy parameters (e.g. `rr_ratio`, `sl_pct`, `target_pct`).

- **`StrategyResult`**:
  - `StrategyName` (`string`): Name identifier.
  - `TotalTrades`, `WinningTrades`, `LosingTrades` (`int`).
  - `WinRate`, `NetPnL`, `MaxDrawdown`, `SharpeRatio`, `ProfitFactor` (`float64`).
  - `Trades` (`[]TradeSignal`): Slice of individual trade execution logs.

---

## 2. Step-by-Step Guide to Add a New Strategy Plugin

### Step 1: Create a New Go File
Create a file named `<your_strategy_name>.go` inside `go-app/strategies/`:

```go
package strategies

type MyNewStrategy struct{}

func NewMyNewStrategy() *MyNewStrategy {
    return &MyNewStrategy{}
}

func (s *MyNewStrategy) GetName() string {
    return "my_new_strategy"
}

func (s *MyNewStrategy) Execute(input StrategyInput) StrategyResult {
    result := StrategyResult{
        StrategyName: "MY_NEW_STRATEGY",
        Trades:       make([]TradeSignal, 0),
    }

    // Your strategy logic here...

    return result
}
```

### Step 2: Register in `registry.go`
Add your new strategy to the `strategyRegistry` map in `go-app/strategies/registry.go`:

```go
var strategyRegistry = map[string]Strategy{
    "ict_smc":         NewICTSMCStrategy(),
    "gamma_blast":     NewGammaBlastStrategy(),
    "candle_3pm":      NewCandle3PMStrategy(),
    "my_new_strategy": NewMyNewStrategy(), // Register here
}
```

### Step 3: Rebuild Go Microservice
Rebuild the container so the Go engine registers the new strategy:
```bash
docker compose build go_app && docker compose up -d go_app
```

---

## 3. Prebuilt Strategies Included

1. **`ict_smc.go`**: ICT / Smart Money Concepts Order Block & Fair Value Gap (FVG) Strategy.
2. **`gamma_blast.go`**: Expiry Day 0DTE Option Gamma Blast Strategy (using dynamic option contract expiry date metadata).
3. **`candle_3pm.go`**: 3:00 PM Breakout Candle Strategy.
