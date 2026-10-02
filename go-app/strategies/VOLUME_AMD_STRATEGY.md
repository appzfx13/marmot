# Volume + AMD Pattern Trading Strategy Documentation

## 1. Strategy Overview

The **Volume + AMD (Accumulation, Manipulation, Distribution)** strategy combines volume order-flow absorption with institutional Smart Money liquidity sweeps. It identifies high-probability turning points by tracking false breakouts (manipulation) outside tight ranges, followed by explosive trend expansion (distribution).

- **Strategy Code Key**: `volume_amd`
- **Execution Engine**: Marmot Go Quantitative Rule Engine (`go-app/strategies/quant_engine.go`)
- **Market Type**: Index F&O (`INDEX_FO` — NIFTY, BANKNIFTY, SENSEX, FINNIFTY) & CME Futures
- **Execution Mode**: 100% Automated via WebSocket & Strike Sweep (ATM±3 Midpoint Limit Orders)

---

## 2. Core Market Phases

```
                [ Phase 2: Manipulation (The Sweep) ]
                       ▲ False Breakout / Stop Run
                       │ (High Volume Spike + Long Rejection Wick)
       ┌───────────────┴───────────────┐  <-- Upper Accumulation Boundary
       │                               │
       │   Phase 1: Accumulation       │  Range Consolidation (Liquidity Pool Build)
       │                               │
       └───────────────┬───────────────┘  <-- Lower Accumulation Boundary
                       │ (Spring / Liquidity Grab + Wick Rejection)
                       ▼
                                       ════════════════════════════════►
                                       Phase 3: Distribution (True Move)
                                       Displacement, BOS & Target 1:2.5
```

### Phase 1: Accumulation (The Range)
- **Concept**: Price consolidates within a tight, sideways volatility-compressed range, building retail buy-stop liquidity above and sell-stop liquidity below.
- **Engine Logic**: Tracks the rolling 15-period consolidation boundaries (`accHigh`, `accLow`) or the initial Opening Range (09:15–09:30 IST).
- **Execution**: No trades are entered during pure consolidation.

### Phase 2: Manipulation (The Sweep)
- **Concept**: Institutional market participants aggressively push prices past the accumulation boundary to trigger retail stop-losses and trap breakout traders.
- **Volume Absorption**: A significant volume surge ($\ge 1.4\times$ the 20-period Volume SMA) prints at the extreme of the breakout, reflecting institutional limit order absorption.
- **Rejection Wick**: Price rapidly rejects and closes **back inside** the accumulation zone, printing a prominent rejection shadow ($\ge 25\%$ of candle range).

### Phase 3: Distribution (The Entry & True Move)
- **Concept**: With liquidity swept and trapped traders offside, price aggressively reverses into the true directional expansion.
- **Trigger**:
  - **Bullish (Spring / Buy CE)**: Price sweeps below `accLow`, forms a long lower wick ($\ge 25\%$), and closes green back above `accLow` (or 2-bar BOS displacement).
  - **Bearish (Upthrust / Buy PE)**: Price sweeps above `accHigh`, forms a long upper wick ($\ge 25\%$), and closes red back below `accHigh` (or 2-bar BOS displacement).
- **Strike Sweep**: Go engine sweeps ATM±3 strikes, selects highest OI & liquidity contract, and issues a midpoint limit order `(Bid + Ask) / 2`.

---

## 3. Default Strategy Parameters

These default parameters are stored in `preset_volume_amd.go` and seeded into Django's `BacktestRule` and `LiveStrategy` tables:

| Parameter Key | Default Value | Data Type | Description |
| :--- | :---: | :---: | :--- |
| `strategy_name` | `"volume_amd"` | `string` | Unique strategy identifier |
| `name` | `"Volume + AMD Pattern (1:2.5 Limit Midpoint)"` | `string` | Human-readable preset display name |
| `rr_ratio` | `2.5` | `float` | Risk-to-Reward ratio (1:2.5 target projection) |
| `sl_pts` | `12.0` | `float` | Option stop loss in premium points (NIFTY: 12 pts; BANKNIFTY: 30 pts) |
| `min_displacement` | `0.50` | `float` | Minimum body-to-range displacement ratio ($50\%$) |
| `min_wick_ratio` | `0.25` | `float` | Minimum rejection wick length relative to total candle range ($25\%$) |
| `volume_surge_multiplier`| `1.4` | `float` | Relative volume threshold vs 20-SMA baseline ($1.4\times$) |
| `entry_window_from` | `565` | `integer` | Entry start window: **09:25 AM IST** ($9 \times 60 + 25$) |
| `entry_window_to` | `900` | `integer` | Entry end window: **15:00 PM IST** ($15 \times 60 + 00$) |
| `use_orb_filter` | `false` | `boolean` | Uses independent rolling accumulation box rather than strict ORB |
| `trail_breakeven` | `true` | `boolean` | Automatically trails SL to entry price once trade reaches $1.5\text{R}$ |
| `breakeven_at_r` | `1.5` | `float` | Profit milestone in R-multiples to trigger breakeven stop loss |
| `cooldown_seconds` | `300` | `integer` | Mandatory 5-minute trade cooldown between consecutive signals |
| `order_type` | `"LIMIT"` | `string` | Mid-price limit order execution via Strike Sweep (`(Bid + Ask)/2`) |
| `lot_size` | `65` | `integer` | Dynamic exchange contract lot size (NIFTY: 65; BANKNIFTY: 30) |

### JSON Parameter Schema (Django `BacktestRule.parameters`):
```json
{
  "ema_fast": 9,
  "ema_slow": 21,
  "entry_window_from": 565,
  "entry_window_to": 900,
  "sl_pts": 12.0,
  "rr_ratio": 2.5,
  "use_orb_filter": false,
  "min_displacement": 0.50,
  "trail_breakeven": true,
  "breakeven_at_r": 1.5,
  "cooldown_seconds": 300,
  "order_type": "LIMIT"
}
```

---

## 4. Timeframe & Resolution Guidelines

- **Recommended Backtest Resolution**: **5-Second (`5S`)**
  - FYERS rejects `1S` historical queries (HTTP 422) but natively supports `5S`.
  - Eliminates micro-tick quote flickering and zero-volume artifacts.
  - Aggregates multi-tick order flow for clean rejection wick identification.
- **Recommended Live Chart View**: **1-Minute (`1M`)** or **3-Minute (`3M`)**
  - Spot signals evaluate on rolling 1-minute aggregated bars from incoming sub-second ticks.
  - Option SL/TP and strike sweep evaluate on sub-second WebSocket ticks.

---

## 5. Risk Management & Invalidation Rules

1. **Stop Loss (Wick-Anchored)**:
   - The stop loss is placed beyond the extreme tip of the manipulation wick $+ 2$ points buffer.
   - For option contracts, the calibrated SL is 12 points for NIFTY ($\approx 24$ index spot points) and 30 points for BANKNIFTY ($\approx 60$ index spot points).
2. **Trailing Stop to Breakeven**:
   - Once the trade achieves $+1.5\text{R}$ gain (e.g. $+18$ option points on NIFTY), the engine automatically shifts the stop loss to Entry Price $+ 1.0$ point, ensuring risk-free distribution capture.
3. **Mid-Day Chop Elimination**:
   - Zero trades are accepted between 11:30 AM and 13:00 PM if consolidation volatility drops below institutional ATR thresholds.

---

## 6. How to Deploy & Backtest

### Running Backtest via Web UI:
1. Navigate to `/users/backtest/create/` or `/admins/dashboard/backtests/`.
2. Select **Index**: `NIFTY` or `BANKNIFTY`.
3. Select **Strategy Preset**: `Volume + AMD Pattern (1:2.5 Limit Midpoint)`.
4. Choose a 5-second historical dataset (e.g. Task #32 / #33) and click **Run Backtest**.

### Seeding Strategy in Database:
```bash
# Seed BacktestRule and LiveStrategy table entries
docker exec django_app python scripts/seed_volume_amd.py

# Or via Django management command
docker exec django_app python manage.py seed_strategy_presets
```
