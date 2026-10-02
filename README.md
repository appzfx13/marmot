# Marmot Enterprise Trading & Backtesting Platform

[![Go Version](https://img.shields.io/badge/Go-1.22+-00ADD8?style=flat&logo=go)](https://golang.org)
[![Python Version](https://img.shields.io/badge/Python-3.12+-3776AB?style=flat&logo=python)](https://python.org)
[![Django Version](https://img.shields.io/badge/Django-5.x-092E20?style=flat&logo=django)](https://djangoproject.com)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?style=flat&logo=docker)](https://docker.com)
[![TradingView](https://img.shields.io/badge/Charts-Lightweight--Charts-2962FF?style=flat)](https://tradingview.com)

---

## 1. Executive Summary & Vision

**Marmot** is an institutional-grade algorithmic trading, quantitative research, and ultra-high-performance backtesting platform engineered specifically for **Indian Equity Derivatives (NSE/BSE F&O)** and **Global Forex**.

### Core Value Proposition
- **High-Throughput Parallel Backtesting:** Eliminates analytical bottlenecks by executing multi-year intraday options strategies across hundreds of millions of ticks and 1-minute bars in seconds using a compiled Go multi-core worker engine.
- **Dynamic Parameter Optimization (Grid & GA):** Employs Go-based multi-threaded Grid Search and Genetic Algorithms (Smart Evolution) to automatically backtest tens of thousands of strategy configurations and isolate the absolute most profitable settings.
- **Continuous Contract Simulation:** Resolves historical options trading anomalies by binding position tracking directly to the exact underlying strike contract throughout its trade lifecycle, eliminating rolling ATM discontinuities and synthetic price jumps.
- **Institutional Market Simulation:** Models dynamic bid-ask spreads, order-size slippage, exchange queue latencies, and the full Indian regulatory tax matrix (Brokerage, STT, Exchange turnover, Stamp duty, GST, and SEBI charges).
- **Dual-Engine Architecture:** Unites Django 5.x (domain modeling, ORM, HTMX Single Page Application, and REST APIs) with Go 1.22+ (low-latency WebSockets, zero-copy Apache Parquet processing, and parallel worker pools).
- **TensorTrade Reinforcement Learning (RL):** Features an advanced PPO engine equipped with dynamic intraday momentum guardrails, 15-minute Opening Range Breakout (ORB) filters, anti-theta time-stops, and a two-tier stop-loss framework.

---

## 2. System Architecture

Marmot deploys a dual-engine architecture communicating asynchronously via **PostgreSQL 16+** and **Redis 7+ Pub/Sub & Caching**.

```mermaid
graph TD
    Client[Web / Mobile / TradingView LightCharts] -->|HTTP / HTMX SPA| Django[Django 5.x Domain Engine]
    Client -->|WebSocket Telemetry| GoApp[Go 1.22+ WebSocket Hub]
    
    Django -->|Domain Services & Auth| CoreLogic{Domain Service Layer}
    CoreLogic <--> PSQL[(PostgreSQL 16+ Relational DB)]
    CoreLogic <--> Redis((Redis 7+ IPC & Cache))
    
    Django -->|Pub/Sub: marmot:tasks:control| Redis
    Redis -->|Task Dispatch| GoWorkers[Go Multi-Core Worker Pools]
    
    GoWorkers -->|ZSTD Zero-Copy Reader/Writer| Datasets[(Date-Partitioned Parquet Files)]
    GoWorkers -->|Live Progress Broadcast| Redis
    GoWorkers -->|Strategy Genetic Optimizer| Redis
    Redis -->|Relay Stream| GoApp
    
    CoreLogic <-->|Broker REST & Webhooks| DhanHQ[Dhan HQ / Fyers Broker Adapters]
    CoreLogic <-->|RL Policy & Signals| RLEngine[TensorTrade PPO RL Engine]
```

### Technology Stack
- **Backend Domain Engine:** Python 3.12+ (Django 5.x)
- **High-Concurrency Microservices:** Go 1.22+ (Goroutines, atomic operations, sync pools)
- **Data Serialization & Compression:** Apache Parquet (ZSTD & Snappy compression)
- **Message Broker & IPC:** Redis 7+ (Pub/Sub task control and atomic progress caches)
- **Primary Relational Store:** PostgreSQL 16+
- **Frontend & UI:** Server-rendered Django Templates + HTMX (Dynamic SPA) + Bootstrap 5 + TradingView LightweightCharts
- **Containerization:** Multi-container Docker Compose architecture

---

## 3. Core Subsystems & Functional Modules

```text
marmot/
├── apps/
│   ├── admins/           # Admin operations, telemetry dashboards, and audit logs
│   ├── api/              # RESTful endpoints for mobile and headless API access
│   ├── backtest/         # Backtest orchestration, RL engine, chart views, and models
│   ├── common/           # Shared mixins, choices, constants, and utilities
│   ├── market/           # Market data structures, option chains, and quote proxies
│   ├── masters/          # Exchange master contracts, security tokens, and holiday calendars
│   ├── notifications/    # Multi-channel notifications (Webhooks, Email, System alerts)
│   ├── postback/         # Broker webhook postback ingestion and order reconciler
│   ├── trade_config/     # Risk limits, capital guards, and freeze configurations
│   ├── trade_core/       # Plug-and-play broker adapters (Dhan, Fyers, Paper Trading)
│   └── users/            # Custom User model, RBAC, and permissions
├── backup/               # Local date-partitioned Apache Parquet datasets
├── go-app/               # Compiled Go 1.22+ Microservice Engine
│   ├── config/           # Environment configuration and connection pools
│   ├── models/           # Parquet schemas and Redis IPC command payloads
│   ├── services/         # DB connection, Parquet reader/writer, and chart handlers
│   ├── strategies/       # Algorithmic strategies (ICT/SMC, Gamma Blast, 3PM Breakout)
│   ├── workers/          # Parallel backtest, data backup, and Genetic Optimizer worker pools
│   ├── ws/               # High-concurrency WebSocket Hub (`hub.go`)
│   └── main.go           # Go microservice entry point
└── templates/            # HTMX dynamic templates and responsive modal layouts
```

---

## 4. Reinforcement Learning (RL) & Quantitative Engine

Located at `apps/backtest/rl_engine.py`, the Marmot RL trading engine integrates **TensorTrade** and **Proximal Policy Optimization (PPO)** for algorithmic option buying and selling.

### Continuous Fixed-Strike Contract Tracking
- **The Problem:** Traditional options backtesting frequently looks up synthetic rolling ATM strike tags at every minute. In trending markets, this causes artificial position hops from one strike to another, creating synthetic gap-ups/gap-downs.
- **The Marmot Solution:** When the RL agent or strategy initiates an entry, the engine records the exact underlying strike contract (`strike_val = 24700`) and relative option strike tag. Throughout the trade's forward trajectory, the engine continuously tracks and resolves candles for that specific strike until formal exit, guaranteeing 100% realistic PnL accounting.

### Two-Tier Stop Loss Architecture
- **Initial Stop Loss (`initial_stop_loss_price`):** Immutable entry risk anchor used to calculate pure Risk-to-Reward (RR) ratios (1:1.75 or 1:2.5) and target prices. Eliminates inverted risk zones on visual charts.
- **Trailing Stop Loss (`trailing_stop_loss_price`):** Dynamic trailing mechanism protecting accumulated gains. Once price gains exceed +10 points, the trailing stop automatically moves to breakeven (+2 points), preventing winning trades from turning into losses.

### Unified Professional Intraday Momentum Guardrails
Seeded via `python manage.py seed_backtest_rules`, this rule enforces disciplined execution:
1. **15-Minute Opening Range (ORB):** Prevents blind 09:15 entries by establishing the high and low range between 09:15 and 09:30.
2. **EMA 9/21 Trend Confirmation:** Enforces bullish continuation (Fast EMA > Slow EMA) for Long CE entries and bearish continuation for Long PE entries.
3. **45-Minute Anti-Theta Time-Stop:** Automatically closes stagnant long option positions after 45 minutes to protect capital against severe intraday theta decay.
4. **Dynamic Lot Sizing & Expiry Awareness:** Automatically adjusts position sizing based on historical exchange lot revisions.

---

## 5. Visual Telemetry & Analysis UI

Marmot features an interactive, dark-themed **TradingView LightweightCharts** modal interface integrated via HTMX partial rendering:

- **Spot-Based Vectorized Strike Extraction:** Directly queries date-partitioned Parquet files to retrieve minute-by-minute candles for the specific option contract traded.
- **UTC-to-IST Market Timescale:** Native timestamp conversion ensures seamless alignment with Indian market trading hours (09:15 to 15:30 IST).
- **Crosshair OHLCV Telemetry:** Instantaneous tooltip updates detailing Open, High, Low, Close, Volume, and candlestick percentage changes.
- **Floating Risk & Telemetry HUD:** Displays real-time entry price, exit price, initial stop loss, trailing stop loss, target price, and net PnL points.
- **Multi-Drawer Performance Metrics:** Responsive 3-column drawer breakdown showing trade duration, gross PnL, charges, net ROI, and capital efficiency.

---

## 6. Exchange Accounting & Regulatory Compliance

Every trade executed or simulated on Marmot adheres to Indian exchange regulations and statutory taxation:

### Dynamic Date-Aware Lot Sizes
Implemented in `get_historical_lot_size(index_name, date)`:
- **NIFTY:** 75 (pre-2021) $\rightarrow$ 50 (2021–Apr 2024) $\rightarrow$ 25 (May–Nov 2024) $\rightarrow$ 75 (Nov 2024–Dec 2025) $\rightarrow$ 65 (Jan 2026+)
- **BANKNIFTY:** 25 (pre-2023) $\rightarrow$ 15 (2023–2024) $\rightarrow$ 30 (post-Nov 2024)
- **FINNIFTY / MIDCPNIFTY / SENSEX / BANKEX:** Dynamically resolved per historical regulatory mandate.

### Indian Statutory Tax Matrix (`calculate_trade_charges`)
- **Brokerage:** ₹20 flat per executed order.
- **Securities Transaction Tax (STT):** 0.125% on option sell turnover.
- **Exchange Turnover Charges:** 0.05% of trade premium turnover.
- **Goods and Services Tax (GST):** 18% on (Brokerage + Exchange Charges + SEBI Fees).
- **Stamp Duty:** 0.003% on option buy turnover.
- **SEBI Turnover Charges:** ₹10 per crore of turnover.

### Utilized Capital Metrics
In addition to Total Account ROI, Marmot measures and reports:
- **Max Utilized Capital:** Peak margin allocated across all open positions.
- **Average Utilized Capital:** Time-weighted capital deployed.
- **Capital Utilization %:** Percentage of total available capital actively at risk.
- **ROI on Utilized Capital:** Realistic return efficiency reflecting actual capital employed.

---

## 7. Institutional Governance & Operational Risk Controls

- **Multi-Tier Freeze Architecture:** Granular flags (`primary_freeze`, `final_freeze`) protect institutional capital against anomalous volatility, network disconnects, or rogue execution loops.
- **User Profile Field Security:** Strict read-only enforcement for `username`, `phone_number`, verification badges, broker credentials (write-once), and trade eligibility flags.
- **Full-Width Layout Uniformity:** Consistent full-width container standard (`col-12`) applied across all administration, analytics, and settings views.

---

## 8. Quick Start & Docker Deployment

### Prerequisites
- Docker Engine 24.0+ and Docker Compose v2+
- Valid broker credentials (e.g., Dhan HQ Client ID and Access Token)

### Multi-Container Startup
```bash
# 1. Clone the repository and configure environment variables
cp .env.example .env

# 2. Build and launch all microservices in detached mode
docker compose up -d --build

# 3. Apply database migrations
docker compose exec django_app python manage.py migrate

# 4. Seed unified quantitative strategy rules
docker compose exec django_app python manage.py seed_backtest_rules

# 5. Create an administrator account
docker compose exec django_app python manage.py createsuperuser
```

### Active Endpoints
| Component | Endpoint | Description |
| :--- | :--- | :--- |
| **Django Application** | `http://localhost:8000` | Web UI, HTMX SPA, and REST APIs |
| **Go WebSocket Hub** | `ws://localhost:8080/ws` | High-frequency telemetry stream |
| **Adminer Database UI** | `http://localhost:8081` | Direct PostgreSQL database administration |

---

## 9. Redis IPC Command Payload Specifications

Django communicates with Go background workers by publishing JSON payloads to Redis channel `marmot:tasks:control`:

### Data Backup Trigger (`START_BACKUP`)
```json
{
  "command": "START_BACKUP",
  "task_id": "b128f731-9043-4ce2-bdf2-f81d5854721a",
  "params": {
    "user_id": "1",
    "index_name": "NIFTY",
    "security_id": "13",
    "start_date": "2024-01-01",
    "end_date": "2024-12-31",
    "strike_count": 10,
    "dhan_client_id": "1000000000",
    "dhan_access_token": "eyJhbGciOi..."
  }
}
```

### High-Performance Backtest Trigger (`START_BACKTEST`)
```json
{
  "command": "START_BACKTEST",
  "task_id": "96b6f4e2-45e8-46d5-8f6b-12d8a4365319",
  "params": {
    "user_id": "1",
    "backup_task_id": "b128f731-9043-4ce2-bdf2-f81d5854721a",
    "strategy_name": "momentum_guardrail",
    "index_name": "NIFTY",
    "start_date": "2024-01-01",
    "end_date": "2024-12-31"
  }
}
```

### Dynamic Strategy Optimizer (`START_OPTIMIZER`)
```json
{
  "command": "START_OPTIMIZER",
  "task_id": "4e1a6c11-92f3-4d2c-80a1-432d64a2b161",
  "params": {
    "user_id": "1",
    "method": "genetic",
    "target_metric": "total_profit",
    "indicators": {
      "rsi": {"min": 20, "max": 40},
      "ema": {"min": 5, "max": 200}
    }
  }
}
```

---

## 10. Future Development Vision & Strategic Roadmap

Marmot is architected to evolve into a complete institutional quantitative fund engine. The upcoming strategic phases include:

```mermaid
timeline
    title Strategic Development Roadmap
    section Phase 1: Low-Latency Execution
        Go DMA Gateway : Direct Dhan/Fyers WebSocket order routing
        Sub-Millisecond Risk Checks : Atomic margin and position validation
    section Phase 2: Distributed RL
        Multi-Agent RL Clusters : Distributed PPO/A2C training across Ray & Go
        Continuous Policy Learning : Live walk-forward reinforcement learning
    section Phase 3: Market Microstructure
        Order Flow Imbalance (OFI) : L2/L3 order book pressure analytics
        Gamma Exposure (GEX) Heatmaps : Institutional option dealer gamma tracking
    section Phase 4: Smart Order Routing
        Cross-Broker SOR : Multi-broker capital and margin allocation
        Automated Portfolio Hedging : Delta-neutral option writing & tail-risk protection
```

### Phase 1: Low-Latency Go Execution Gateway
- **Direct Broker WebSockets:** Implement a compiled Go OMS (Order Management System) establishing low-latency binary/JSON WebSocket connections to Dhan HQ and Fyers.
- **Sub-Millisecond Pre-Trade Risk:** Perform pre-trade margin calculations, position sizing, and freeze validations in Go before dispatching orders to broker gateways.

### Phase 2: Distributed Multi-Agent RL Training Clustering
- **Ray + Go Parquet Streaming Integration:** Scale TensorTrade RL training across multi-node clusters reading date-partitioned Parquet datasets in parallel.
- **Continuous Walk-Forward Adaptation:** Transition from static historical backtesting to continuous walk-forward model adaptation with automated policy validation.

### Phase 3: Market Microstructure & Order Flow Analytics
- **Order Flow Imbalance (OFI) & VPOC:** Ingest Level 2/3 market depth to calculate real-time order flow imbalances, Volume Point of Control (VPOC), and Value Area High/Low (VAH/VAL).
- **Dealer Gamma Exposure (GEX) Profiling:** Track cumulative strike open interest and dealer gamma positioning to anticipate explosive gamma squeezes and pinning on expiry days.

### Phase 4: Smart Order Routing (SOR) & Dynamic Portfolio Hedging
- **Multi-Broker Allocation:** Intelligently route order slices across multiple broker accounts based on margin availability, execution speed, and fill rates.
- **Autonomous Delta-Neutral Hedging:** Combine automated algorithmic option writing with dynamic underlying futures hedging and systematic tail-risk option buying.


[![Architecture diagram of appzfx13/marmot](https://gitdiagram.com/appzfx13/marmot/diagram.png)](https://gitdiagram.com/appzfx13/marmot?utm_source=readme&utm_medium=picture)

%% Generated by https://gitdiagram.com/appzfx13/marmot
flowchart TD

subgraph group_web["User and Django"]
  node_django["Django Domain Engine<br/>[urls.py]"]
  node_api["REST API<br/>[views.py]"]
  node_users[("Users and Access<br/>[models.py]")]
end

subgraph group_research["Research and Data"]
  node_backtest["Backtest Orchestration<br/>[services.py]"]
  node_vector["Trade Analytics"]
  node_rl["PPO Reinforcement Learning"]
  node_datasets[("Historical Datasets")]
  node_market["Market Data Services<br/>[services.py]"]
  node_macroai["AI Macro Service<br/>[gemini_service.py]"]
  node_marketfeed["Live Market Feed"]
end

subgraph group_execution["Trading Operations"]
  node_tradeconfig[("Risk and Trade Config<br/>[models.py]")]
  node_brokerfactory["Broker Adapter Factory<br/>[factory.py]"]
  node_dhan["Dhan Adapter<br/>[dhan.py]"]
  node_fyers["Fyers Adapter<br/>[fyers.py]"]
  node_postback["Order Reconciliation<br/>[services.py]"]
end

subgraph group_platform["Shared Platform"]
  node_postbacklog[("Postback Records<br/>[models.py]")]
  node_notifications["Notifications<br/>[email.py]"]
  node_postgres[("PostgreSQL")]
  node_redis[("Redis IPC and Cache")]
end

subgraph group_realtime["Go Runtime"]
  node_strategies["Strategy Engine<br/>[quant_engine.go]"]
  node_optimizer["Strategy Optimization<br/>[optimizer_job.go]"]
  node_workers["Go Worker Pools<br/>[manager.go]"]
  node_parquet["Parquet Processing<br/>[reader.go]"]
  node_ws["WebSocket Hub<br/>[hub.go]"]
end

node_client(("Web / Mobile Client"))
node_telemetry(("Live Telemetry Client"))
node_brokers["Dhan / Fyers Brokers"]
node_tensortrade["TensorTrade PPO"]

node_client -->|"HTTP / HTMX"| node_django
node_client -->|"WebSocket telemetry"| node_ws
node_django -.->|"routes requests"| node_api
node_django -.->|"orchestrates backtests"| node_backtest
node_django -->|"domain persistence"| node_postgres
node_django -->|"publishes tasks"| node_redis
node_django -->|"auth and domain"| node_users
node_backtest -->|"dispatches jobs"| node_workers
node_workers -.->|"runs strategies"| node_strategies
node_workers -->|"runs optimization"| node_optimizer
node_workers -->|"reads and writes"| node_parquet
node_parquet -->|"processes datasets"| node_datasets
node_workers -->|"broadcasts progress"| node_redis
node_market -->|"fetches macro data"| node_macroai
node_market -->|"publishes task status"| node_redis
node_brokers -->|"Sub-10ms WebSockets"| node_ws
node_ws -->|"Caches quotes & chains"| node_redis
node_marketfeed -->|"Reads cached quotes (<1ms)"| node_redis
node_tradeconfig -->|"stores configuration"| node_postgres
node_brokerfactory -->|"selects adapter"| node_dhan
node_brokerfactory -->|"selects adapter"| node_fyers
node_brokers -->|"sends order events"| node_postback
node_postback -->|"records events"| node_postbacklog
node_postback -.->|"publishes order events"| node_redis
node_postbacklog -->|"persists records"| node_postgres
node_backtest -.->|"summarizes trades"| node_vector
node_backtest -->|"supports RL research"| node_rl
node_rl -->|"integrates PPO"| node_tensortrade
node_redis -->|"dispatches tasks (Streams)"| node_workers
node_redis -->|"relays progress"| node_ws
node_ws -->|"streams updates"| node_telemetry
node_django -.->|"sends alerts"| node_notifications

click node_django "https://github.com/appzfx13/marmot/blob/main/marmot/urls.py"
click node_api "https://github.com/appzfx13/marmot/blob/main/apps/api/views.py"
click node_users "https://github.com/appzfx13/marmot/blob/main/apps/users/models.py"
click node_backtest "https://github.com/appzfx13/marmot/blob/main/apps/backtest/services.py"
click node_vector "https://github.com/appzfx13/marmot/blob/main/apps/backtest/trade_vector_engine.py"
click node_rl "https://github.com/appzfx13/marmot/tree/main/apps/backtest"
click node_strategies "https://github.com/appzfx13/marmot/blob/main/go-app/strategies/quant_engine.go"
click node_optimizer "https://github.com/appzfx13/marmot/blob/main/go-app/workers/optimizer_job.go"
click node_workers "https://github.com/appzfx13/marmot/blob/main/go-app/workers/manager.go"
click node_parquet "https://github.com/appzfx13/marmot/blob/main/go-app/parquet/reader.go"
click node_market "https://github.com/appzfx13/marmot/blob/main/apps/market/services.py"
click node_macroai "https://github.com/appzfx13/marmot/blob/main/apps/common/services/gemini_service.py"
click node_marketfeed "https://github.com/appzfx13/marmot/blob/main/apps/common/services/live_feed_service.py"
click node_tradeconfig "https://github.com/appzfx13/marmot/blob/main/apps/trade_config/models.py"
click node_brokerfactory "https://github.com/appzfx13/marmot/blob/main/apps/trade_core/brokers/factory.py"
click node_dhan "https://github.com/appzfx13/marmot/blob/main/apps/trade_core/brokers/dhan.py"
click node_fyers "https://github.com/appzfx13/marmot/blob/main/apps/trade_core/brokers/fyers.py"
click node_postback "https://github.com/appzfx13/marmot/blob/main/apps/postback/services.py"
click node_postbacklog "https://github.com/appzfx13/marmot/blob/main/apps/common/models.py"
click node_notifications "https://github.com/appzfx13/marmot/blob/main/apps/notifications/services/email.py"
click node_ws "https://github.com/appzfx13/marmot/blob/main/go-app/ws/hub.go"

classDef toneNeutral fill:#f8fafc,stroke:#334155,stroke-width:1.5px,color:#0f172a
classDef toneBlue fill:#dbeafe,stroke:#2563eb,stroke-width:1.5px,color:#172554
classDef toneAmber fill:#fef3c7,stroke:#d97706,stroke-width:1.5px,color:#78350f
classDef toneMint fill:#dcfce7,stroke:#16a34a,stroke-width:1.5px,color:#14532d
classDef toneRose fill:#ffe4e6,stroke:#e11d48,stroke-width:1.5px,color:#881337
classDef toneIndigo fill:#e0e7ff,stroke:#4f46e5,stroke-width:1.5px,color:#312e81
classDef toneTeal fill:#ccfbf1,stroke:#0f766e,stroke-width:1.5px,color:#134e4a
class node_django,node_api,node_users,node_client,node_telemetry toneBlue
class node_backtest,node_vector,node_rl,node_datasets,node_market,node_macroai,node_marketfeed toneAmber
class node_tradeconfig,node_brokerfactory,node_dhan,node_fyers,node_postback toneMint
class node_postbacklog,node_notifications,node_postgres,node_redis toneRose
class node_strategies,node_optimizer,node_workers,node_parquet,node_ws,node_brokers,node_tensortrade toneIndigo