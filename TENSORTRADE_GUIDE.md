# Marmot TensorTrade Deep Reinforcement Learning (RL) Guide

This guide explains how to use **TensorTrade** (`tensortrade-ng`) with Marmot's date-partitioned Apache Parquet backup datasets for training and backtesting Deep Reinforcement Learning (RL) trading agents.

---

## 1. Overview & Architecture

Marmot integrates TensorTrade as a modular **Plug-and-Play Strategy Engine** (`TENSORTRADE_RL`). 

```
┌────────────────────────────────────────────────────────┐
│              Marmot HTMX SPA Portal / UI               │
└───────────────────────────┬────────────────────────────┘
                            │ 1. Configure & Run RL Backtest
                            ▼
┌────────────────────────────────────────────────────────┐
│        Django Backtest Engine (apps/backtest/)         │
└───────────────────────────┬────────────────────────────┘
                            │ 2. Ingest Parquet Backup File
                            ▼
┌────────────────────────────────────────────────────────┐
│        TensorTrade RL Engine (rl_engine.py)            │
│  - Dataset: /app/backup/{user_id}/{task_id}/           │
│  - Environment: DataFeed (OHLCV, Volume, OI, IV)       │
│  - Policy Agent: PPO / A2C / DQN                       │
└───────────────────────────┬────────────────────────────┘
                            │ 3. Output Trades & Metrics
                            ▼
┌────────────────────────────────────────────────────────┐
│  TradingView Chart Actions + Win Rate & Sharpe Report  │
└───────────────────────────┘
```

---

## 2. Parquet Backup File Compatibility

TensorTrade reads Marmot's binary Apache Parquet backup files directly without any conversion required.

### **Dataset File Paths**:
- **Single Consolidated Dataset**: `/app/backup/{user_id}/{task_id}/dataset.parquet`
- **Date-Partitioned Datasets**: `/app/backup/{user_id}/{task_id}/year=YYYY/month=MM/*.parquet`

### **Supported Parquet Data Schema**:
Marmot's Parquet dataset schema maps 1-to-1 into TensorTrade state observations:
- `timestamp` / `datetime`: Timestamps for step alignment.
- `index_name`: Target asset (e.g. `NIFTY`, `BANKNIFTY`).
- `open`, `high`, `low`, `close`: Candle OHLC prices.
- `volume`: Trading volume.
- `oi`: Open Interest (for Options/Futures).
- `iv`: Implied Volatility (for Options).
- `spot_price`: Underlying Index Spot level.

---

## 3. How to Run TensorTrade RL in Marmot

### **Via Marmot User Portal**:
1. Open **Backtest Engine** in Marmot (`/users/backtest/`).
2. Select an existing **Parquet Backup Task** from the backup list.
3. Choose Strategy: **TensorTrade RL (Deep Reinforcement Learning)**.
4. Set Hyperparameters:
   - **Algorithm**: `PPO` (Proximal Policy Optimization) / `A2C` / `DQN`
   - **Reward Scheme**: `SharpeRatio` / `RiskAdjusted` / `NetPnL`
   - **Training Timesteps**: `10,000`
   - **Stop Loss %**: `0.5%`
5. Click **Run Backtest**.
6. Marmot executes the RL agent over the Parquet dataset, saves the trained model weights to `/app/backup/{user_id}/{task_id}/rl_agent_model.zip`, and renders the trade signals directly on the TradingView chart!

---

## 4. Python API Usage Code Example

```python
import pandas as pd
from apps.backtest.rl_engine import TensorTradeRLEngine

# 1. Path to Marmot Parquet Backup Directory
backup_dir = "/app/backup/1/42/"

# 2. Run TensorTrade RL Engine over Parquet dataset
results = TensorTradeRLEngine.run_rl_backtest(
    backup_dir=backup_dir,
    params={
        "index_name": "NIFTY",
        "algorithm": "PPO",
        "reward_metric": "sharpe",
        "total_timesteps": 10000,
        "initial_capital": 100000.0,
        "stop_loss_pct": 0.5
    }
)

# 3. Inspect Strategy Results
print(f"Strategy: {results['strategy_name']}")
print(f"Win Rate: {results['win_rate']}%")
print(f"Gross PnL: ₹{results['gross_pnl']}")
print(f"Net PnL:   ₹{results['net_pnl']}")
print(f"Brokerage: ₹{results['total_brokerage']}")
print(f"Total Charges: ₹{results['total_charges']}")
print(f"Max Utilized Capital: ₹{results['max_utilized_capital']}")
print(f"ROI on Utilized Cap: {results['roi_on_utilized_capital']}%")
print(f"Sharpe:    {results['sharpe_ratio']}")
print(f"Total Trades: {results['total_trades']}")
```

---

## 5. Dynamic Lot Sizing & Regulatory Timelines (2020 – Present)

The RL Backtest Engine dynamically determines historical contract sizes and expiry schedules for any candle date from **2020 to Present**:

| Index | Date Range | Regulatory Lot Size | Expiry Schedule | Circular Ref |
| :--- | :--- | :--- | :--- | :--- |
| **NIFTY** | 2020-01-01 to 2021-06-30 | **75** | Thursday (Weekly & Monthly) | Standard |
| **NIFTY** | 2021-07-01 to 2024-04-25 | **50** | Thursday (Weekly & Monthly) | NSE/FAOP/47786 |
| **NIFTY** | 2024-04-26 to Present | **25** | Thursday (Weekly & Monthly) | NSE/FAOP/61328 |
| **BANKNIFTY** | 2020-01-01 to 2020-07-30 | **20** | Thursday (Weekly & Monthly) | Historical standard |
| **BANKNIFTY** | 2020-07-31 to 2023-07-13 | **25** | Thursday (Weekly & Monthly) | NSE/FAOP/44358 |
| **BANKNIFTY** | 2023-07-14 to 2024-11-19 | **15** | Wednesday (Weekly) / Last Thu (Monthly) | NSE/FAOP/56177 |
| **BANKNIFTY** | 2024-11-20 to Present | **30** | Last Thursday (Monthly only) | NSE/FAOP/64515 |
| **FINNIFTY** | 2021-01-11 to 2022-12-31 | **40** | Tuesday (Weekly & Monthly) | Product Launch |
| **FINNIFTY** | 2023-01-01 to 2024-11-19 | **25** | Tuesday (Weekly & Monthly) | Lot Revision |
| **FINNIFTY** | 2024-11-20 to Present | **65** | Tuesday (Weekly & Monthly) | SEBI Contract Revision |
| **MIDCPNIFTY** | 2022-01-24 to 2024-11-19 | **75** | Wednesday (pre-Aug 2023) / Monday | Launch / Aug Shift |
| **MIDCPNIFTY** | 2024-11-20 to Present | **50** | Monday (Weekly & Monthly) | SEBI Contract Revision |
| **SENSEX** | 2023-05-15 to 2024-11-19 | **10** | Friday (Weekly & Monthly) | BSE Relaunch |
| **SENSEX** | 2024-11-20 to Present | **20** | Friday (Weekly & Monthly) | BSE Revision |
| **BANKEX** | 2023-05-15 to 2024-11-19 | **15** | Monday (Weekly & Monthly) | BSE Relaunch |
| **BANKEX** | 2024-11-20 to Present | **30** | Monthly only | BSE Revision |

---

## 6. Brokerage & Charges Calculation Logic

Every executed trade computes standard Indian statutory taxes and brokerage:
- **Brokerage**: Flat ₹20 per executed order (₹40 round-trip).
- **STT (Securities Transaction Tax)**: 0.1% on Option sell turnover.
- **Exchange Turnover Charges (NSE)**: 0.05% of turnover.
- **SEBI Charges**: ₹10 per crore (0.000001).
- **Stamp Duty**: 0.003% on buy turnover.
- **GST**: 18% on `(Brokerage + Exchange Charges + SEBI Charges)`.

---

## 7. Summary of Components

- **RL Adapter Engine**: [`apps/backtest/rl_engine.py`](file:///e:/Workspace/Projects/MARMOT/marmot/apps/backtest/rl_engine.py)
- **Lot Size & Charges Helper**: [`apps/common/constants.py`](file:///e:/Workspace/Projects/MARMOT/marmot/apps/common/constants.py)
- **Strategy Choice**: Registered `TENSORTRADE_RL` in [`apps/common/choices.py`](file:///e:/Workspace/Projects/MARMOT/marmot/apps/common/choices.py)
- **Service Integration**: Updated [`apps/backtest/services.py`](file:///e:/Workspace/Projects/MARMOT/marmot/apps/backtest/services.py)
- **Dependencies**: Added `tensortrade-ng`, `gymnasium`, `stable-baselines3` to [`requirements.txt`](file:///e:/Workspace/Projects/MARMOT/marmot/requirements.txt)
