---
trigger: always_on
---

# Marmot AI Development & Automation Rules

All automated AI agents, subagents, and developers working on the Marmot codebase MUST strictly adhere to the following rules without exception.

---

## 1. Scope, Minimality & Code Simplicity
- **Required Changes Only:** Make **only strictly required changes** to fulfill the specific prompt or task. Never perform unsolicited refactoring, code reorganization, or stylistic rewrites on untouched files or methods.
- **Preserve Unrelated Code:** Preserve all existing comments, type annotations, and logic in untouched code sections.
- **Straightforward & Readable Code:** Avoid over-engineering, unnecessary abstractions, or overly complex implementations. Write clear, easily understandable, maintainable code in Python and Go.
- **Dependency Propagation:** When modifying or adding functionality, always update all dependent functions, method call signatures, views, templates, and service layers.

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
- **Modular Strategy Interfaces:** Strategies under `go-app/strategies/` must implement a unified plug-and-play `Strategy` interface.
- **High-Throughput Streaming & Parquet:**
  - Parquet dataset reader/writers (`go-app/parquet/`) must follow date-partitioned storage paths (`/app/backup/{user_id}/{task_id}/`).
  - WebSockets hub (`go-app/ws/hub.go`) must handle broadcast channels safely without blocking worker threads.

---

## 10. Backtesting, Dynamic Lot Sizes & Brokerage Accounting
- **Dynamic Lot Sizing:** Historical index option trade quantities must always be resolved dynamically via date-aware lookups (`get_historical_lot_size(index_name, date)`) to accurately reflect historical exchange revisions (e.g. NIFTY 75 → 50 → 25; BANKNIFTY 25 → 15 → 30).
- **Expiry Schedule Accuracy:** Backtest and strategy evaluators must account for exchange expiry schedules (`get_index_expiry_info(index_name, date)`) including weekly vs monthly expiry days and regulatory single-weekly index shifts.
- **Full Charges & Brokerage Accounting:** Every backtest execution and trade log must calculate gross PnL, brokerage, STT/CTT, exchange charges, SEBI fees, stamp duty, and GST using `calculate_trade_charges()`.
- **Utilized Capital Metrics:** Backtest reports and UI dashboards must report max utilized capital, average utilized capital, capital utilization %, and ROI on utilized capital alongside total capital ROI.