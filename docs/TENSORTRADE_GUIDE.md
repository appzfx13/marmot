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
└────────────────────────────────────────────────────────┘
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
print(f"Net PnL:  ₹{results['net_pnl']}")
print(f"Sharpe:   {results['sharpe_ratio']}")
print(f"Total Trades: {results['total_trades']}")
```

---

## 5. Summary of Created Components

- **RL Adapter Engine**: [`apps/backtest/rl_engine.py`](file:///e:/Workspace/Projects/MARMOT/marmot/apps/backtest/rl_engine.py)
- **Strategy Choice**: Registered `TENSORTRADE_RL` in [`apps/common/choices.py`](file:///e:/Workspace/Projects/MARMOT/marmot/apps/common/choices.py)
- **Service Integration**: Updated [`apps/backtest/services.py`](file:///e:/Workspace/Projects/MARMOT/marmot/apps/backtest/services.py)
- **Dependencies**: Added `tensortrade-ng`, `gymnasium`, `stable-baselines3` to [`requirements.txt`](file:///e:/Workspace/Projects/MARMOT/marmot/requirements.txt)
