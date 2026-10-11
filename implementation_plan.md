# Implementation Plan - Backtest Configuration Optimizer ("Find Config")

Implement a high-speed, military-finance-grade Hyperparameter Optimizer ("Find Config") that evaluates combinations of Stop Loss, Risk-to-Reward, Trailing SL, and Retest Layering directly in Go memory in ~2 seconds, enriches the top candidates with Gemini AI regime synthesis, and enables 1-click application in the Backtest Edit modal.

---

## User Review Required

> [!IMPORTANT]
> **Proposed Search Space & Performance Budget:**
> - **Search Space (72 Combinations):**
>   - **Stop Loss Points:** `[10.0, 15.0, 20.0, 25.0, 30.0]` (5 steps)
>   - **Risk-to-Reward Ratio (1:X):** `[1.5, 2.0, 2.5, 3.0]` (4 steps)
>   - **Trailing Stop Loss:** `[Off, On (1.0R), On (1.2R), On (1.5R)]` (4 steps)
>   - **Retest Layering:** `[Enabled, Disabled]` (2 steps)
> - **Latency Budget:** Under 3.0 seconds total (Go in-memory parallel worker pool + single 1-shot Gemini summary).
> - **Zero Disruption to Active Backtest Engine:** Targeted restarts only (`docker restart go_service django_app`), no `docker compose down`.

---

## Proposed Changes

### 1. Go Microservice Engine (`go-app/`)

#### [NEW] [go-app/api/optimizer_handler.go](file:///e:/Workspace/Projects/MARMOT/marmot/go-app/api/optimizer_handler.go)
- Create `HandleBacktestOptimize(dbService, config)` HTTP handler mounted at `POST /api/backtest/optimize`.
- Reads `dataset.parquet` (and co-located VIX / Macro if enabled) once into memory.
- Generates the 72-combination parameter grid.
- Dispatches combinations across parallel worker goroutines (`runtime.NumCPU()`).
- Executes `strat.Execute(input)` for each combination over historical days.
- Calculates Net PnL, Win Rate %, Profit Factor, Max Drawdown %, and Expectancy Score:
  $$\text{Score} = \text{Net PnL} \times \left(1 - \frac{\text{Max DD}}{100}\right) \times \text{Win Rate}$$
- Sorts and returns the Top 5 ranked candidates and metrics as JSON.

#### [go-app/main.go](file:///e:/Workspace/Projects/MARMOT/marmot/go-app/main.go)
- Register `http.HandleFunc("/api/backtest/optimize", ...)` in the Go HTTP server.

---

### 2. Django Service & Views (`apps/backtest/`)

#### [apps/backtest/views.py](file:///e:/Workspace/Projects/MARMOT/marmot/apps/backtest/views.py)
- Create `BacktestFindOptimalConfigView(LoginRequiredMixin, View)`:
  - Fetches `BacktestTask` by `pk`.
  - Dispatches POST request to `http://go_service:8082/api/backtest/optimize` with task parameters.
  - Passes Top 3 candidates to Gemini AI (via `google-genai` / `gemini_service`) to generate a 2-sentence rationale on why the winning parameter set suited historical market volatility.
  - Returns rendered partial `admins/partials/backtest_optimal_config_results.html` for HTMX target `#optimalConfigResultsContainer`.

#### [apps/backtest/urls.py](file:///e:/Workspace/Projects/MARMOT/marmot/apps/backtest/urls.py)
- Add route: `path('<int:pk>/find-optimal-config/', BacktestFindOptimalConfigView.as_view(), name='backtest_find_optimal_config')`.

---

### 3. UI Templates & HTMX Components

#### [NEW] [templates/admins/partials/backtest_optimal_config_results.html](file:///e:/Workspace/Projects/MARMOT/marmot/templates/admins/partials/backtest_optimal_config_results.html)
- Clean, executive-grade Leaderboard card:
  - **Rank #1 Winner Badge:** Net PnL, Win Rate %, R:R, SL pts, Max Drawdown %, Profit Factor.
  - **Gemini Strategic Rationale Card:** Context on why this parameter set outperformed.
  - **Runner-Up Comparison Table:** Ranks #2 through #5.
  - **`[Apply Winning Config ⚡]` button:** Calls vanilla JavaScript to populate modal inputs with 1 click.

#### [templates/admins/partials/backtest_edit_modal.html](file:///e:/Workspace/Projects/MARMOT/marmot/templates/admins/partials/backtest_edit_modal.html)
- In the modal footer (directly before `"Save & Regenerate Backtest"`):
  - Add `<button type="button" class="btn btn-outline-warning rounded-pill ...">⚡ Find Best Config</button>` with `hx-post="{% url 'backtest:backtest_find_optimal_config' backtest.pk %}"`, `hx-target="#optimalConfigResultsContainer"`, and indicator spinner.
- Add `#optimalConfigResultsContainer` container above the footer.
- Add JS helper `applyOptimalConfig(sl, rr, enableTrail, trailTrigger, enableRetest)` to automatically fill form fields when user selects any ranked candidate.

---

## Verification Plan

### Automated Tests
1. **Go Unit Test:** Create `go-app/api/optimizer_handler_test.go` to test grid generator and scoring calculation on synthetic tick data.
   - Command: `docker exec go_service go test -v ./api/...`
2. **Django View Test:** Test `BacktestFindOptimalConfigView` via Django test client or curl.
   - Command: `docker exec django_app python manage.py test apps.backtest`

### End-to-End Visual & Playwright Browser Verification (Rule 12)
1. Use Antigravity browser subagent to navigate to Backtest #24 edit modal (`/backtest/24/` -> Edit Parameters).
2. Click `[⚡ Find Best Config]`.
3. Verify:
   - Loading spinner displays smoothly.
   - Results container loads the Leaderboard and Gemini AI rationale within 3 seconds.
   - Click `[Apply Winning Config ⚡]` and verify form inputs (`stop_loss_points`, `rr_ratio`, `trailing_sl`) are auto-filled correctly.
   - Click `"Save & Regenerate Backtest"` and verify the new run triggers without errors.
4. Capture and review screenshots to visually validate the UI before concluding.
