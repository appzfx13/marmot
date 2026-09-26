---
trigger: always_on
---

# Marmot AI Development & Automation Rules

All automated AI agents, subagents, and developers working on the Marmot codebase MUST strictly adhere to the following rules without exception.

---

## 1. Scope, Minimality & Code Simplicity
- **Direct Question Answering (HIGH PRIORITY):** Whenever the user asks a question, ALWAYS reply and answer the question directly and completely first before proposing or executing any code changes.
- **User Approval Required Before Any Code Changes (HIGH PRIORITY):** NEVER modify any file, write code, apply patches, or execute modifying commands without explicitly presenting the proposed plan or change to the user and receiving explicit user confirmation/approval first.
- **Required Changes Only:** Make **only strictly required changes** to fulfill the specific prompt or task. Never perform unsolicited refactoring, code reorganization, or stylistic rewrites on untouched files or methods.
- **Preserve Unrelated Code:** Preserve all existing comments, type annotations, and logic in untouched code sections.
- **Straightforward & Readable Code:** Avoid over-engineering, unnecessary abstractions, or overly complex implementations. Write clear, easily understandable, maintainable code in Python and Go.
- **Dependency Propagation:** When modifying or adding functionality, always update all dependent functions, method call signatures, views, templates, and service layers.
- **Ingress & Tunnel Continuity (PRIORITY 1):** NEVER execute `docker compose down` during routine code modifications, testing, or feature updates. Routine container reloads must strictly use targeted container restarts (e.g. `docker compose restart web go_app`) to keep the public Cloudflare ingress tunnel and live broker webhook URLs continuously active without downtime or URL rotation.

---

## 2. Formatting, Line Length & Spacing Accountability
- **Single-Line Field Definitions:** Format model fields, form fields, and serializer fields as single lines whenever possible (maximum **170 characters** line length).
- **PEP 8 Spacing Standards:** Maintain exact spacing standards in Python:
  - **2 blank lines** between top-level classes and functions.
  - **1 blank line** between methods inside a class.
- **Go Formatting (`gofmt`):** Maintain standard `gofmt` indentation (tabs) and formatting across all Go packages.
- **Space Accountability:** Never introduce trailing whitespace, arbitrary indentation shifts, or unnecessary blank lines.

---

## 3. Module Organization (Choices & Constants)
- **Choices File (`choices.py`):** Keep all model field choices, status enums, and tuple choices exclusively inside `choices.py` within each respective app module (`apps/<app_name>/choices.py`) or centralized in `apps/common/choices.py`.
- **Constants & Messages File (`constants.py`):** Keep all configuration constants, default values, error messages, user notification strings, and system status messages inside `apps/common/constants.py`.

---

## 4. Environment Variables & Settings Safety
- **No Environment Variable Fallbacks:** Do NOT provide silent fallback default values for `.env` variables in `settings.py`. Missing environment variables must raise an explicit error (`KeyError` / `ImproperlyConfigured`) so missing environment configurations are immediately noticed by developers.
- **Docker-First Project Architecture:** Always keep Docker container environment context in mind for file paths, containerized networking (Redis, PostgreSQL hostnames), and background worker containers.

---

## 5. Performance & Database Safety
- **Avoid N+1 Queries Always:** Always optimize database queries using `select_related()` for foreign keys / one-to-one relationships and `prefetch_related()` for many-to-many / reverse foreign keys.
- **Database Safety:** Always create and verify Django migrations (`python manage.py makemigrations`) for schema changes without breaking relational foreign keys.

---

## 6. Docstrings & Import Hygiene
- **Docstring Limits:** Maximum **1-2 lines** per docstring across all functions, methods, classes, and modules (concise, factual, medium-length).
- **Import Hygiene:**
  - Remove all unused imports immediately.
  - Group imports logically:
    1. Standard library imports
    2. Third-party packages (Django, Go modules)
    3. Local application imports

---

## 7. UI, SPA & Design System Architecture
- **Pervasive SPA Experience:** Maintain a Single Page Application (SPA) experience at all times using HTMX dynamic partial rendering, target swapping (`hx-target`, `hx-swap="innerHTML"`, `hx-push-url="true"`), and modals.
- **Page Container Uniformity:** Maintain a strict full-width container layout (`col-12`) across all pages, including Profile Settings and Admin Dashboards.
- **Theme & Design Consistency:** Every UI component must be theme-conscious and adhere to common design system variables (glassmorphic dark/light tokens, cards, and buttons). Style elements must be plug-and-play in shared theme CSS files.
- **Fully Responsive UI:** Ensure optimal responsiveness and proper alignment across mobile, tablet, and desktop viewports.
- **User Profile Field Security:**
  - `username`: Always read-only.
  - `phone_number`: Read-only for standard users.
  - `Verification Badges`: Read-only status badges for standard users.
  - `Broker Credentials`: Cannot be modified by regular users once created (Admin/Developer role required).
  - `Trade Control & Freeze Flags` (`trade_eligibility`, `is_blocked`, `primary_freeze`, `final_freeze`): Always read-only for standard users.
- **Navigation Structure:** The Profile settings link belongs exclusively in the top-right profile dropdown menu and navigation sidebar.
- **Strictly Zero Periodic HTMX Polling for Real-Time Telemetry & Stats:** Never use periodic HTMX interval polling (e.g. `hx-trigger="every 1s/2s/3s"`) for real-time ticker prices, PnL metrics, positions, orders, or streamer progress. All real-time telemetry must strictly use WebSocket Push direct to DOM or event-driven HTMX swaps triggered exclusively by WebSocket events (`hx-trigger="event from:body"`).

---

## 8. Modular Strategy & Broker Adapter Architecture
- **Plug-and-Play Strategy Engine:** Backtesting and trading strategies must follow modular, plug-and-play interfaces.
- **Plug-and-Play Broker Adapters:** Broker integrations (Dhan, Fyers, etc.) must use isolated plug-and-play adapter classes.
- **Dual-Engine Integration:**
  - **Django:** Manages relational entities, authentication, HTMX views, REST APIs, and dispatches background tasks via Redis Pub/Sub (`marmot:tasks:control`).
  - **Go:** Handles high-throughput streaming, WebSockets (`ws/hub.go`), Parquet reading/writing, and compute-intensive backtesting worker pools (`workers/`).
- **Data Parquet Storage:** Historical option datasets must always adhere to the date-partitioned structure under `/app/backup/{user_id}/{task_id}/`.

---

## 9. Go Microservice Engine Standards (`go-app/`)
- **Formatting & Style:** Enforce standard `gofmt` (tab indentation) and `goimports` formatting on all `.go` files.
- **Import Grouping:** Group imports into standard library, third-party packages, and internal local packages.
- **Explicit Error Handling:** Never ignore returned errors (`err`). Check and handle or log every error explicitly.
- **Concurrency & Goroutine Safety:**
  - Use `context.Context` for cancellation and timeout propagation across worker pools.
  - Protect shared state with `sync.RWMutex` or atomic operations.
  - Ensure goroutines terminate cleanly using `sync.WaitGroup` to avoid goroutine memory leaks.
- **Modular Strategy Presets & Rule Configuration Workflow:**
  - Keep hardcoded Go strategy presets modularized into dedicated files under `go-app/strategies/` (e.g. `preset_momentum.go`, `preset_orb.go`, `preset_scalp.go`, `preset_ict.go`) exposing clean `StrategyConfig` structs.
  - Register presets in `StrategyPresets` map inside `go-app/strategies/registry.go` keyed by the rule type string.
  - When introducing a genuinely new strategy type: (1) add choice to `apps/backtest/choices.py`, (2) create or extend `go-app/strategies/preset_<type>.go`, (3) wire into `StrategyPresets` in `registry.go`.
- **High-Throughput Streaming & Parquet:**
  - Parquet dataset reader/writers (`go-app/parquet/`) must follow date-partitioned storage paths (`/app/backup/{user_id}/{task_id}/`).
  - WebSockets hub (`go-app/ws/hub.go`) must handle broadcast channels safely without blocking worker threads.

---

## 10. Backtesting, Dynamic Lot Sizes & Brokerage Accounting
- **Dynamic Lot Sizing:** Historical index option trade quantities must always be resolved dynamically via date-aware lookups (`get_historical_lot_size(index_name, date)`) to accurately reflect historical exchange revisions (e.g. NIFTY 75 → 50 → 25; BANKNIFTY 25 → 15 → 30).
- **Expiry Schedule Accuracy:** Backtest and strategy evaluators must account for exchange expiry schedules (`get_index_expiry_info(index_name, date)`) including weekly vs monthly expiry days and regulatory single-weekly index shifts.
- **Full Charges & Brokerage Accounting:** Every backtest execution and trade log must calculate gross PnL, brokerage, STT/CTT, exchange charges, SEBI fees, stamp duty, and GST using `calculate_trade_charges()`.
- **Utilized Capital Metrics:** Backtest reports and UI dashboards must report max utilized capital, average utilized capital, capital utilization %, and ROI on utilized capital alongside total capital ROI.
- **Zero Synthetic Price Floors & Pure Historical Streaming:** Never inject arbitrary price floors (e.g. `math.Max(25.0, ...)`), fake Brownian walk seed constants, or fallback LTPs into the Dhan emulator, option chain streamers, or Terminal UI charts. Deep OTM options and live Terminal charts must reflect true historical Parquet data, mathematical Black-Scholes/extrinsic decay, or true Broker REST API/WebSocket data. If data is absent, display `—` (unavailable) or leave charts blank rather than falsifying or randomizing values. Under no circumstances should dummy data be used in production interfaces.
- **Event-Driven Virtual Clock for High-Speed Simulation:** All strategy signal generators, indicators, opening range discovery (ORB), time-stops, and trade cooldowns MUST evaluate against the market tick's timestamp (`tick.Timestamp`) rather than system wall-clock time (`time.Now()`). This guarantees that 1X, 5X, 10X, or event-driven accelerated playback produces 100% identical trading signals without distorting strategy logic.

---

## 11. Structured RCA, Feature Planning & Approval Protocol
- **Step-by-Step Bug Fix Workflow (Mandatory):**
  1. **Find RCA:** Perform root cause analysis and explain the bug using simple, easily understandable concepts.
  2. **Pros / Cons Fix Options Table:** Present proposed fix options in a comparison table detailing Pros, Cons, and Recommended Better Approach.
  3. **Stop & Request Start Approval:** STOP and ask the user to select the preferred fix and explicitly grant approval ("proceed to start") before executing any code changes.
- **Step-by-Step Feature Enhancement Workflow (Mandatory):**
  1. **Dependency Audit:** Thoroughly check all dependent models, service layers, Go microservice handlers, APIs, and UI templates.
  2. **Prepare Implementation Plan:** Draft a structured `implementation_plan.md` artifact detailing proposed architectural changes and verification steps.
  3. **Stop & Request Start Approval:** Present the plan, discuss design choices, and wait for explicit user confirmation ("proceed to start") before modifying code.
- **RCA - Fix - Approach Summary Table Required:** After completing approved work, AI agents MUST provide a structured summary table containing Root Cause Analysis (RCA), Fix Applied, and Architectural Approach in the final response.

---

## 12. Mandatory Browser Control & Playwright Verification
- **End-to-End Visual & Network Testing (MANDATORY):** All automated AI agents and developers modifying frontend UI templates, HTMX swaps, live option chains, WebSocket consumers, forms, or admin dashboards MUST test and verify changes using Playwright and the Antigravity browser subagent / browser control.
- **Verification Criteria:**
  1. Navigate to the affected page(s) and authenticate if required.
  2. Monitor network traffic in the browser context to verify zero redundant HTTP polling and confirm HTTP status 200/101.
  3. Inspect DOM elements to verify real-time data updates, responsive layout alignment, and visual styling.
  4. Capture and review screenshots to visually validate the UI before concluding any task.
