package handlers

import (
	"encoding/json"
	"fmt"
	"html/template"
	"net/http"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"dhan-emulator/engine"
	"dhan-emulator/models"
	"dhan-emulator/streamer"
)

// Handler sets up all HTTP and WebSocket endpoints for DHAN-EMULATOR.
type Handler struct {
	engine   *engine.MatchingEngine
	chaos    *engine.ChaosManager
	streamer *streamer.ParquetStreamer
	tmpl     *template.Template
}

// NewHandler constructs a new Handler.
func NewHandler(eng *engine.MatchingEngine, chaos *engine.ChaosManager, st *streamer.ParquetStreamer, tmplPath string) (*Handler, error) {
	var tmpl *template.Template
	if tmplPath != "" {
		funcMap := template.FuncMap{
			"plus": func(a, b float64) float64 { return a + b },
		}
		t, err := template.New(filepath.Base(tmplPath)).Funcs(funcMap).ParseFiles(tmplPath)
		if err == nil {
			tmpl = t
		}
	}
	return &Handler{
		engine:   eng,
		chaos:    chaos,
		streamer: st,
		tmpl:     tmpl,
	}, nil
}

// RegisterRoutes registers all REST, WebSocket, and HTMX routes on the given mux.
func (h *Handler) RegisterRoutes(mux *http.ServeMux) {
	// Root index and legacy /mock/dashboard redirect to unified Django Gateway Emulator
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/" || r.URL.Path == "/mock/dashboard" || r.URL.Path == "/mock/dashboard/" {
			redirectURL := "http://localhost:8050/admins/dashboard/gateway-emulator/"
			if strings.Contains(r.Host, "trycloudflare.com") || strings.Contains(r.Host, "ngrok") {
				redirectURL = "/admins/dashboard/gateway-emulator/"
			}
			http.Redirect(w, r, redirectURL, http.StatusMovedPermanently)
			return
		}
		http.NotFound(w, r)
	})

	// Favicon (prevent 404 in browser console)
	mux.HandleFunc("/favicon.ico", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNoContent)
	})

	// Health check
	mux.HandleFunc("/health", h.handleHealth)
	mux.HandleFunc("/mock/health", h.handleHealth)

	// Market feed WebSocket
	mux.HandleFunc("/mock/v2/marketfeed/ws", h.streamer.HandleWebSocket)
	mux.HandleFunc("/v2/marketfeed/ws", h.streamer.HandleWebSocket)

	// Dashboard UI & HTMX endpoints
	mux.HandleFunc("/mock/dashboard", h.handleDashboard)
	mux.HandleFunc("/mock/dashboard/funds", h.handleDashboardFunds)
	mux.HandleFunc("/mock/dashboard/orders", h.handleDashboardOrders)
	mux.HandleFunc("/mock/dashboard/positions", h.handleDashboardPositions)
	mux.HandleFunc("/mock/dashboard/tickers", h.handleDashboardTickers)
	mux.HandleFunc("/mock/dashboard/streamer", h.handleDashboardStreamer)
	mux.HandleFunc("/mock/dashboard/progress", h.handleDashboardProgress)
	mux.HandleFunc("/mock/dashboard/controls", h.handleDashboardControls)
	mux.HandleFunc("/mock/dashboard/streamer-widget", h.handleDashboardStreamerWidget)
	mux.HandleFunc("/mock/dashboard/option-chain", h.handleDashboardOptionChain)
	mux.HandleFunc("/mock/dashboard/summary", h.handleDashboardSummary)

	// Account Management & HTMX Modals
	mux.HandleFunc("/mock/accounts/dropdown", h.handleAccountDropdown)
	mux.HandleFunc("/mock/accounts/select", h.handleAccountSelect)
	mux.HandleFunc("/mock/accounts/modal/create", h.handleAccountModalCreate)
	mux.HandleFunc("/mock/accounts/create", h.handleAccountCreate)
	mux.HandleFunc("/mock/accounts/modal/list", h.handleAccountModalList)
	mux.HandleFunc("/mock/accounts/modal/detail", h.handleAccountModalDetail)
	mux.HandleFunc("/mock/accounts/modal/edit", h.handleAccountModalEdit)
	mux.HandleFunc("/mock/accounts/update", h.handleAccountUpdate)
	mux.HandleFunc("/mock/accounts/modal/delete-confirm", h.handleAccountModalDeleteConfirm)
	mux.HandleFunc("/mock/accounts/delete", h.handleAccountDelete)

	mux.HandleFunc("/mock/api/funds/adjust", h.handleAdjustFunds)
	mux.HandleFunc("/mock/api/chaos", h.handleUpdateChaos)
	mux.HandleFunc("/mock/api/streamer/toggle", h.handleStreamerToggle)
	mux.HandleFunc("/mock/api/streamer/stop", h.handleStreamerStop)
	mux.HandleFunc("/mock/api/streamer/restart", h.handleStreamerRestart)
	mux.HandleFunc("/mock/api/streamer/speed", h.handleStreamerSpeed)
	mux.HandleFunc("/mock/api/streamer/select", h.handleStreamerSelect)
	mux.HandleFunc("/mock/api/streamer/files", h.handleStreamerFiles)
	mux.HandleFunc("/mock/api/streamer/status", h.handleStreamerStatus)
	mux.HandleFunc("/mock/streamer/status", h.handleStreamerStatus)
	mux.HandleFunc("/mock/api/kill-switch", h.handleKillSwitch)
	mux.HandleFunc("/mock/api/session/clear", h.handleClearSession)
	mux.HandleFunc("/mock/api/tick", h.handleManualTick)

	// Dhan REST API v2 Handlers (supporting both /v2/ and /mock/v2/ prefixes)
	mux.HandleFunc("/mock/v2/orders", h.handleOrders)
	mux.HandleFunc("/v2/orders", h.handleOrders)
	mux.HandleFunc("/mock/v2/orders/", h.handleOrderByID)
	mux.HandleFunc("/v2/orders/", h.handleOrderByID)

	mux.HandleFunc("/mock/v2/fundlimit", h.handleFundLimit)
	mux.HandleFunc("/v2/fundlimit", h.handleFundLimit)

	mux.HandleFunc("/mock/v2/positions", h.handlePositions)
	mux.HandleFunc("/v2/positions", h.handlePositions)

	mux.HandleFunc("/mock/v2/holdings", h.handleHoldings)
	mux.HandleFunc("/v2/holdings", h.handleHoldings)

	// Active Mock Account Telemetry Endpoint (for Marmot Live Mock Dashboard synchronization)
	mux.HandleFunc("/mock/v2/active-account", h.handleActiveAccount)
	mux.HandleFunc("/mock/api/active-account", h.handleActiveAccount)

	// Market Option Chain Endpoint (Compatible with Marmot Live HUD & Heatmap)
	mux.HandleFunc("/mock/v2/optionchain", h.handleOptionChain)
	mux.HandleFunc("/v2/optionchain", h.handleOptionChain)
}

// handleActiveAccount returns JSON details of the currently selected active mock account.
func (h *Handler) handleActiveAccount(w http.ResponseWriter, r *http.Request) {
	activeID := h.engine.GetActiveAccountID()
	acc, ok := h.engine.GetAccount(activeID)
	name := "Primary Algorithmic Trading"
	broker := "Dhan"
	var availBal, sodLimit, utilMargin float64 = 100000.0, 100000.0, 0.0
	if ok && acc != nil {
		name = acc.AccountName
		broker = acc.Broker
		availBal = acc.AvailableBalance
		sodLimit = acc.SodLimit
		utilMargin = acc.UtilizedMargin
	}
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Access-Control-Allow-Origin", "*")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"success":           true,
		"active_account_id": activeID,
		"account_name":      name,
		"broker":            broker,
		"available_balance": availBal,
		"sod_limit":         sodLimit,
		"utilized_margin":   utilMargin,
	})
}

func (h *Handler) handleOptionChain(w http.ResponseWriter, r *http.Request) {
	index := r.URL.Query().Get("index")
	if index == "" {
		index = "NIFTY"
	}
	resp := h.streamer.GetOptionChain(index)
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Access-Control-Allow-Origin", "*")
	json.NewEncoder(w).Encode(resp)
}

func (h *Handler) handleHealth(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "ok", "service": "dhan-emulator"})
}

// handleOrders routes POST /orders (place) and GET /orders (list).
func (h *Handler) handleOrders(w http.ResponseWriter, r *http.Request) {
	clientID := r.Header.Get("client-id")
	if clientID == "" {
		clientID = h.engine.GetActiveAccountID()
	}

	switch r.Method {
	case http.MethodPost:
		var req models.OrderRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			http.Error(w, fmt.Sprintf("invalid payload: %v", err), http.StatusBadRequest)
			return
		}
		if req.DhanClientID == "" {
			req.DhanClientID = clientID
		}

		resp, err := h.engine.PlaceOrder(req)
		if err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(resp)

	case http.MethodGet:
		orders := h.engine.GetOrders(clientID)
		if len(orders) == 0 {
			orders = h.engine.GetAllOrders()
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(orders)

	default:
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
	}
}

// handleOrderByID routes GET, PUT, DELETE for /orders/{orderId}.
func (h *Handler) handleOrderByID(w http.ResponseWriter, r *http.Request) {
	parts := strings.Split(strings.Trim(r.URL.Path, "/"), "/")
	orderID := parts[len(parts)-1]
	clientID := r.Header.Get("client-id")
	if clientID == "" {
		clientID = "1000000001"
	}

	switch r.Method {
	case http.MethodGet:
		orders := h.engine.GetOrders(clientID)
		for _, o := range orders {
			if o.OrderID == orderID {
				w.Header().Set("Content-Type", "application/json")
				json.NewEncoder(w).Encode(o)
				return
			}
		}
		http.Error(w, `{"status":"error","errorMessage":"Order not found"}`, http.StatusNotFound)

	case http.MethodPut:
		var modReq struct {
			Price        float64 `json:"price"`
			TriggerPrice float64 `json:"triggerPrice"`
			Quantity     int     `json:"quantity"`
		}
		if err := json.NewDecoder(r.Body).Decode(&modReq); err != nil {
			http.Error(w, "invalid payload", http.StatusBadRequest)
			return
		}
		err := h.engine.ModifyOrder(clientID, orderID, modReq.Price, modReq.TriggerPrice, modReq.Quantity)
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]string{"orderId": orderID, "orderStatus": "PENDING"})

	case http.MethodDelete:
		err := h.engine.CancelOrder(clientID, orderID)
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]string{"orderId": orderID, "orderStatus": "CANCELLED"})

	default:
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
	}
}

// handleFundLimit returns virtual balance limits.
func (h *Handler) handleFundLimit(w http.ResponseWriter, r *http.Request) {
	clientID := r.Header.Get("client-id")
	if clientID == "" {
		clientID = "1000000001"
	}
	resp := h.engine.GetFundLimit(clientID)
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(resp)
}

// handlePositions returns positions with real-time Parquet MTM.
func (h *Handler) handlePositions(w http.ResponseWriter, r *http.Request) {
	clientID := r.Header.Get("client-id")
	if clientID == "" {
		clientID = "1000000001"
	}
	positions := h.engine.GetPositions(clientID)
	if len(positions) == 0 {
		positions = h.engine.GetAllPositions()
	}
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(positions)
}

// handleHoldings returns holdings.
func (h *Handler) handleHoldings(w http.ResponseWriter, r *http.Request) {
	clientID := r.Header.Get("client-id")
	if clientID == "" {
		clientID = "1000000001"
	}
	holdings := h.engine.GetHoldings(clientID)
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(holdings)
}

// resolveClientID extracts the active client ID from query param, cookie, or engine default.
func (h *Handler) resolveClientID(r *http.Request) string {
	if id := r.URL.Query().Get("account"); id != "" {
		if _, ok := h.engine.GetAccount(id); ok {
			return id
		}
	}
	if cookie, err := r.Cookie("marmot_mock_client_id"); err == nil && cookie.Value != "" {
		if _, ok := h.engine.GetAccount(cookie.Value); ok {
			return cookie.Value
		}
	}
	return h.engine.GetActiveAccountID()
}

// handleDashboard redirects legacy dashboard requests to the unified Django Gateway Emulator.
func (h *Handler) handleDashboard(w http.ResponseWriter, r *http.Request) {
	redirectURL := "http://localhost:8050/admins/dashboard/gateway-emulator/"
	if strings.Contains(r.Host, "trycloudflare.com") || strings.Contains(r.Host, "ngrok") {
		redirectURL = "/admins/dashboard/gateway-emulator/"
	}
	http.Redirect(w, r, redirectURL, http.StatusMovedPermanently)
}

// handleDashboardFunds renders the fund partial for HTMX polling.
func (h *Handler) handleDashboardFunds(w http.ResponseWriter, r *http.Request) {
	clientID := h.resolveClientID(r)
	funds := h.engine.GetFundLimit(clientID)
	fmt.Fprintf(w, `<div class="d-flex justify-content-between align-items-baseline mb-1"><span class="fs-4 fw-bold text-success font-monospace">₹%.2f</span><span class="badge bg-success bg-opacity-20 text-success border border-success border-opacity-25 font-monospace">AVAILABLE</span></div><div class="small text-secondary d-flex justify-content-between"><span>SOD Limit: ₹%.2f</span><span>Utilized: ₹%.2f</span></div>`,
		funds.AvailabelBalance, funds.SodLimit, funds.UtilizedAmount)
}

// handleDashboardProgress renders live replay progress bar and calendar date for HTMX polling.
func (h *Handler) handleDashboardProgress(w http.ResponseWriter, r *http.Request) {
	curRow, totRows, pct, curDt, curDate := h.streamer.GetProgress()
	isPlaying, speed, currentFile, ticks := h.streamer.GetStatus()
	isCompleted := h.streamer.IsCompleted()

	statusBadge := `<span id="emulator-progress-badge" class="badge bg-secondary bg-opacity-25 text-white-50 border border-white border-opacity-15 rounded-pill px-3 py-1 fs-xs fw-bold font-monospace shadow-sm"><i class="bi bi-pause-circle me-1"></i> FEED PAUSED (STANDBY)</span>`
	if isCompleted {
		pct = 100.0
		curRow = totRows
		statusBadge = `<span id="emulator-progress-badge" class="badge bg-info bg-opacity-20 text-info border border-info border-opacity-30 rounded-pill px-3 py-1 fs-xs fw-bold font-monospace shadow-sm"><i class="bi bi-check2-circle me-1"></i> REPLAY COMPLETED (100%)</span>`
		w.Header().Set("HX-Trigger", "replayCompleted")
	} else if isPlaying {
		statusBadge = `<span id="emulator-progress-badge" class="badge bg-success bg-opacity-20 text-success border border-success border-opacity-30 rounded-pill px-3 py-1 fs-xs fw-bold font-monospace d-inline-flex align-items-center gap-1.5 shadow-sm"><span class="spinner-grow spinner-grow-sm text-success" role="status" style="width: 0.45rem; height: 0.45rem;"></span><span>STREAMING TICK FEED</span></span>`
	}

	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	fmt.Fprintf(w, `
	<div class="d-flex flex-column gap-2.5">
		<div class="d-flex align-items-center justify-content-between flex-wrap gap-2">
			<div class="d-flex align-items-center gap-2 flex-wrap">
				%s
				<span class="badge bg-dark border border-white border-opacity-10 text-warning px-2.5 py-1 font-monospace smaller shadow-sm">
					<i class="bi bi-calendar3 me-1.5"></i> <span id="emulator-progress-date">%s</span>
				</span>
				<span class="badge bg-dark border border-white border-opacity-10 text-info px-2.5 py-1 font-monospace smaller shadow-sm">
					<i class="bi bi-clock me-1.5"></i> <span id="emulator-progress-time">%s IST</span>
				</span>
			</div>
			<div class="d-flex align-items-center gap-3 font-monospace smaller text-secondary flex-wrap">
				<span>Dataset: <strong id="emulator-progress-dataset" class="text-white">%s</strong></span>
				<span class="opacity-25">|</span>
				<span>Rows: <strong id="emulator-progress-rows" class="text-white">%d / %d</strong></span>
				<span class="opacity-25">|</span>
				<span>Progress: <strong id="emulator-progress-pct" class="text-success">%.1f%%</strong></span>
				<span class="opacity-25">|</span>
				<span>Speed: <strong id="emulator-progress-speed" class="text-warning">%dx</strong></span>
				<span class="opacity-25">|</span>
				<span>Ticks: <strong id="emulator-progress-ticks" class="text-white">%d</strong></span>
			</div>
		</div>
		<div class="progress rounded-pill bg-dark border border-white border-opacity-10" style="height: 8px;">
			<div id="emulator-progress-bar" class="progress-bar progress-bar-striped progress-bar-animated bg-success" role="progressbar" style="width: %.2f%%; background-color: var(--brand-lime, #fafafa) !important;" aria-valuenow="%.1f" aria-valuemin="0" aria-valuemax="100"></div>
		</div>
	</div>`, statusBadge, curDate, curDt, currentFile, curRow, totRows, pct, speed, ticks, pct, pct)
}

// handleDashboardControls renders the separate, uncongested replay controller card.
func (h *Handler) handleDashboardControls(w http.ResponseWriter, r *http.Request) {
	isPlaying, speed, currentFile, _ := h.streamer.GetStatus()
	isCompleted := h.streamer.IsCompleted()
	curRow, _, _, _, _ := h.streamer.GetProgress()
	files := h.streamer.ListParquetDetails()

	var currentInfo streamer.ParquetFileInfo
	for _, f := range files {
		if f.RelativePath == currentFile {
			currentInfo = f
			break
		}
	}
	if currentInfo.IndexName == "" {
		currentInfo.IndexName = "NIFTY"
	}

	toggleBtn := `<button class="btn btn-success text-dark fw-bold btn-sm rounded-pill px-4 py-2 shadow-sm d-inline-flex align-items-center gap-2" hx-post="/mock/api/streamer/toggle" hx-target="#streamer-controls-wrapper" hx-swap="outerHTML"><i class="bi bi-play-fill fs-5"></i> <span>Start Replay</span></button>`
	if isCompleted {
		toggleBtn = `<button class="btn btn-success text-dark fw-bold btn-sm rounded-pill px-4 py-2 shadow-sm d-inline-flex align-items-center gap-2" hx-post="/mock/api/streamer/restart" hx-target="#streamer-controls-wrapper" hx-swap="outerHTML"><i class="bi bi-arrow-repeat fs-5"></i> <span>Replay Again</span></button>`
	} else if isPlaying {
		toggleBtn = `<button class="btn btn-warning text-dark fw-bold btn-sm rounded-pill px-4 py-2 shadow-sm d-inline-flex align-items-center gap-2" hx-post="/mock/api/streamer/toggle" hx-target="#streamer-controls-wrapper" hx-swap="outerHTML"><i class="bi bi-pause-fill fs-5"></i> <span>Pause Replay</span></button>`
	} else if curRow > 0 {
		toggleBtn = `<button class="btn btn-info text-dark fw-bold btn-sm rounded-pill px-4 py-2 shadow-sm d-inline-flex align-items-center gap-2" hx-post="/mock/api/streamer/toggle" hx-target="#streamer-controls-wrapper" hx-swap="outerHTML"><i class="bi bi-play-circle-fill fs-5"></i> <span>Resume Replay</span></button><button class="btn btn-outline-success fw-bold btn-sm rounded-pill px-3 py-2 shadow-sm d-inline-flex align-items-center gap-1.5 ms-1.5" hx-post="/mock/api/streamer/restart" hx-target="#streamer-controls-wrapper" hx-swap="outerHTML" title="Restart from Row 0"><i class="bi bi-arrow-repeat"></i> <span>Restart</span></button>`
	}
	stopBtn := `<button class="btn btn-outline-danger fw-bold btn-sm rounded-pill px-3 py-2 shadow-sm d-inline-flex align-items-center gap-1.5 ms-1.5" hx-post="/mock/api/streamer/stop" hx-target="#streamer-controls-wrapper" hx-swap="outerHTML" title="Stop & Halt Simulation"><i class="bi bi-stop-circle-fill"></i> <span>STOP</span></button>`
	controlsActionGroup := fmt.Sprintf(`<div class="d-inline-flex align-items-center gap-1">%s%s</div>`, toggleBtn, stopBtn)

	var dropdownItems strings.Builder
	if len(files) == 0 {
		dropdownItems.WriteString(`<li><span class="dropdown-item text-muted">Synthetic Brownian Walk (Default)</span></li>`)
	} else {
		for _, f := range files {
			activeClass := ""
			borderStyle := "transparent"
			bgStyle := "transparent"
			checkIcon := ""
			if f.RelativePath == currentFile {
				activeClass = "active-parquet-item"
				borderStyle = "rgba(56, 189, 248, 0.4)"
				bgStyle = "rgba(56, 189, 248, 0.12)"
				checkIcon = `<i class="bi bi-check-circle-fill text-info fs-6 flex-shrink-0 ms-2"></i>`
			}
			calSpan := ""
			if f.DateRange != "" {
				calSpan = fmt.Sprintf(`<span class="text-white-50"><i class="bi bi-calendar3 me-1 text-warning"></i>%s</span> <span>&bull;</span> `, f.DateRange)
			}

			dropdownItems.WriteString(fmt.Sprintf(`
			<li>
				<a class="dropdown-item rounded-2 py-2 px-2.5 mb-1 d-flex align-items-center justify-content-between font-monospace text-wrap %s"
				   href="javascript:void(0);"
				   hx-post="/mock/api/streamer/select?file=%s"
				   hx-target="#streamer-controls-wrapper"
				   hx-swap="outerHTML"
				   style="font-size: 0.76rem; border: 1px solid %s; background: %s; cursor: pointer;">
					<div class="d-flex flex-column gap-1 me-2 overflow-hidden text-start">
						<div class="d-flex align-items-center gap-1.5 flex-wrap">
							<span class="badge rounded-pill px-1.5 py-0.5 smaller fw-bold" style="background: rgba(56, 189, 248, 0.15); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.3);">
								%s
							</span>
							<strong class="text-white text-truncate">%s</strong>
							<span class="badge bg-secondary bg-opacity-30 text-white-50 smaller px-1.5 py-0.5">
								%s
							</span>
						</div>
						<div class="d-flex align-items-center gap-2 smaller text-muted">
							%s<span>%.1f MB</span>
						</div>
					</div>
					%s
				</a>
			</li>`, activeClass, f.RelativePath, borderStyle, bgStyle, f.IndexName, f.RelativePath, f.TypeLabel, calSpan, f.SizeMB, checkIcon))
		}
	}

	dateBadge := ""
	if currentInfo.DateRange != "" {
		dateBadge = fmt.Sprintf(`<span class="badge bg-secondary bg-opacity-25 text-white-50 font-monospace smaller px-1.5 py-0.5 d-none d-sm-inline-block"><i class="bi bi-calendar3 me-1 text-warning"></i>%s</span>`, currentInfo.DateRange)
	}

	dropdownHtml := fmt.Sprintf(`
	<div class="dropdown custom-parquet-dropdown w-100">
		<button class="btn dropdown-toggle w-100 text-start d-flex align-items-center justify-content-between px-3 py-2 rounded-3 font-monospace"
				type="button" 
				id="parquetDropdownBtn"
				data-bs-toggle="dropdown" 
				data-bs-display="static"
				aria-expanded="false"
				style="background: #141416; color: #fafafa; font-size: 0.78rem; min-height: 42px; border: 1px solid rgba(255, 255, 255, 0.08); outline: none;">
			<div class="d-flex align-items-center gap-2 overflow-hidden me-2">
				<span class="badge rounded-pill px-2 py-0.5 smaller fw-bold flex-shrink-0" style="color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.3); background: rgba(56, 189, 248, 0.12);">
					%s
				</span>
				<span class="text-truncate fw-semibold text-white">%s</span>
				%s
			</div>
			<i class="bi bi-chevron-down text-white-50 flex-shrink-0 ms-2"></i>
		</button>
		<ul class="dropdown-menu dropdown-menu-dark w-100 shadow-lg p-1.5 custom-scroll"
			aria-labelledby="parquetDropdownBtn"
			style="background: #121215; backdrop-filter: blur(20px); border-radius: 10px; border: 1px solid rgba(255, 255, 255, 0.08); max-height: 360px; overflow-y: auto; z-index: 1060;">
			%s
		</ul>
	</div>`, currentInfo.IndexName, currentFile, dateBadge, dropdownItems.String())

	speeds := []int{1, 5, 10, 25, 50, 100, 250}
	var speedPills strings.Builder
	for _, sp := range speeds {
		active := ""
		if sp == speed {
			active = "active"
		}
		label := fmt.Sprintf("%dx", sp)
		if sp == 250 {
			label = "250x"
		}
		speedPills.WriteString(fmt.Sprintf(`<button class="btn speed-pill rounded-pill %s" hx-post="/mock/api/streamer/speed?val=%d" hx-target="#streamer-controls-wrapper" hx-swap="outerHTML">%s</button>`, active, sp, label))
	}

	engineBadge := `<span class="badge bg-secondary bg-opacity-25 text-white-50 border border-white border-opacity-15 rounded-pill px-2.5 py-1 smaller font-monospace">STANDBY</span>`
	if isCompleted {
		engineBadge = `<span class="badge bg-info bg-opacity-20 text-info border border-info border-opacity-30 rounded-pill px-2.5 py-1 smaller font-monospace"><i class="bi bi-check-circle-fill me-1" style="font-size: 0.45rem;"></i> REPLAY COMPLETED</span>`
	} else if isPlaying {
		engineBadge = `<span class="badge bg-success bg-opacity-20 text-success border border-success border-opacity-30 rounded-pill px-2.5 py-1 smaller font-monospace"><i class="bi bi-circle-fill me-1" style="font-size: 0.45rem;"></i> ENGINE ACTIVE</span>`
	}

	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	fmt.Fprintf(w, `
	<div class="card glass-card p-3 mb-0 border-secondary border-opacity-20 shadow-sm" id="streamer-controls-wrapper" style="position: relative; z-index: 50;">
		<div class="d-flex align-items-center justify-content-between mb-3 pb-2 border-bottom border-secondary border-opacity-20">
			<div class="d-flex align-items-center gap-2">
				<div class="rounded-circle d-flex align-items-center justify-content-center shadow-sm" style="width: 32px; height: 32px; background: rgba(255, 255, 255, 0.08); color: #fafafa; border: 1px solid rgba(255, 255, 255, 0.12);">
					<i class="bi bi-sliders"></i>
				</div>
				<h6 class="mb-0 fw-bold theme-text-main" style="font-size: 0.95rem;">Parquet Replay Controller</h6>
			</div>
			%s
		</div>
		<div class="row g-3 align-items-end">
			<div class="col-12 col-lg-5">
				<label class="text-secondary smaller fw-bold d-block mb-1 text-uppercase" style="font-size: 0.68rem; letter-spacing: 0.5px;">
					<i class="bi bi-file-earmark-binary-fill me-1 text-warning"></i>Parquet Dataset File
				</label>
				%s
			</div>
			<div class="col-12 col-sm-5 col-lg-3 text-start text-sm-center">
				<label class="text-secondary smaller fw-bold d-block mb-1 text-uppercase" style="font-size: 0.68rem; letter-spacing: 0.5px;">Playback State</label>
				%s
			</div>
			<div class="col-12 col-sm-7 col-lg-4 text-start text-sm-end">
				<label class="text-secondary smaller fw-bold d-block mb-1 text-uppercase" style="font-size: 0.68rem; letter-spacing: 0.5px;">Replay Speed</label>
				<div class="d-flex flex-wrap gap-1 justify-content-start justify-content-sm-end" role="group">
					%s
				</div>
			</div>
		</div>
	</div>`, engineBadge, dropdownHtml, controlsActionGroup, speedPills.String())
}

// handleDashboardOptionChain renders the complete option chain HTML partial matching Marmot's live_mini_option_chain_card.html
func (h *Handler) handleDashboardOptionChain(w http.ResponseWriter, r *http.Request) {
	index := r.URL.Query().Get("index")
	if index == "" {
		index = "NIFTY"
	}
	index = strings.ToUpper(strings.TrimSpace(index))
	chain := h.streamer.GetOptionChain(index)

	availableIndexes := []string{"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX"}
	var idxOptions strings.Builder
	for _, idx := range availableIndexes {
		sel := ""
		if idx == index {
			sel = "selected"
		}
		idxOptions.WriteString(fmt.Sprintf(`<option value="%s" %s>%s</option>`, idx, sel, idx))
	}

	badgeChangeClass := "bg-success bg-opacity-20 text-success"
	if !chain.IsPositive {
		badgeChangeClass = "bg-danger bg-opacity-20 text-danger"
	}

	var rowsHtml strings.Builder
	for _, row := range chain.Strikes {
		outerClass := ""
		if !row.IsActiveWindow {
			outerClass = "option-chain-outer-strike d-none"
		}
		atmRowClass := ""
		atmRowStyle := ""
		atmBadge := ""
		strikeColor := "text-white"
		if row.IsATM {
			atmRowClass = "table-active option-chain-atm-row"
			atmRowStyle = `style="background: rgba(255, 255, 255, 0.06) !important; border-top: 1px solid rgba(255, 255, 255, 0.2) !important; border-bottom: 1px solid rgba(255, 255, 255, 0.2) !important;"`
			atmBadge = `<span class="badge bg-dark border border-warning text-warning rounded-pill px-1.5 py-0.5 smaller ms-1">ATM</span>`
			strikeColor = "text-warning"
		}

		ceChgClass := "text-success"
		ceChgPrefix := "+"
		if row.CE_Change < 0 {
			ceChgClass = "text-danger"
			ceChgPrefix = ""
		}
		peChgClass := "text-success"
		peChgPrefix := "+"
		if row.PE_Change < 0 {
			peChgClass = "text-danger"
			peChgPrefix = ""
		}

		ceCell := fmt.Sprintf(`<span class="text-white fw-bold px-1 rounded" id="oc-ltp-ce-%.0f">₹%.2f</span> <span class="smaller %s ms-1">%s%.1f</span>`, row.Strike, row.CE_LTP, ceChgClass, ceChgPrefix, row.CE_Change)
		if row.CE_LTP <= 0 {
			ceCell = fmt.Sprintf(`<span class="text-muted fw-normal px-1" id="oc-ltp-ce-%.0f">&mdash;</span>`, row.Strike)
		}

		peCell := fmt.Sprintf(`<span class="text-white fw-bold px-1 rounded" id="oc-ltp-pe-%.0f">₹%.2f</span> <span class="smaller %s ms-1">%s%.1f</span>`, row.Strike, row.PE_LTP, peChgClass, peChgPrefix, row.PE_Change)
		if row.PE_LTP <= 0 {
			peCell = fmt.Sprintf(`<span class="text-muted fw-normal px-1" id="oc-ltp-pe-%.0f">&mdash;</span>`, row.Strike)
		}

		rowsHtml.WriteString(fmt.Sprintf(`
		<tr class="%s %s" %s>
			<td class="font-monospace text-muted smaller py-2.5" id="oc-oi-ce-%.0f">%s</td>
			<td class="font-monospace text-end pe-3 border-end py-2.5" style="border-color: var(--border-color, rgba(255,255,255,0.08)) !important;">
				%s
			</td>
			<td class="font-monospace fw-bold py-2.5 %s" style="font-size: 0.82rem; background: rgba(255,255,255,0.02);">
				₹%.0f%s
			</td>
			<td class="font-monospace text-start ps-3 border-start py-2.5" style="border-color: var(--border-color, rgba(255,255,255,0.08)) !important;">
				%s
			</td>
			<td class="font-monospace text-muted smaller py-2.5" id="oc-oi-pe-%.0f">%s</td>
		</tr>`, outerClass, atmRowClass, atmRowStyle, row.Strike, row.CE_OI, ceCell,
			strikeColor, row.Strike, atmBadge, peCell, row.Strike, row.PE_OI))
	}

	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	fmt.Fprintf(w, `
	<div class="card shadow-sm overflow-hidden mb-0 p-0 glass-card">
		<div class="card-header bg-transparent py-3 px-4 border-bottom border-secondary border-opacity-20 d-flex flex-column flex-lg-row align-items-lg-center justify-content-between gap-3">
			<div class="d-flex align-items-center gap-3">
				<div class="rounded-circle d-flex align-items-center justify-content-center shadow-sm flex-shrink-0" style="width: 40px; height: 40px; background: rgba(255, 255, 255, 0.08); color: #fafafa; border: 1px solid rgba(255, 255, 255, 0.12);">
					<i class="bi bi-diagram-3-fill fs-5"></i>
				</div>
				<div>
					<div class="d-flex align-items-center gap-2 flex-wrap">
						<h5 class="fw-bold theme-text-main mb-0" style="font-size: 1.05rem;">%s Option Chain</h5>
						<span class="badge bg-success bg-opacity-20 text-success border border-success border-opacity-30 rounded-pill px-2.5 py-1 fs-xs fw-bold d-inline-flex align-items-center gap-1.5 shadow-sm">
							<span class="spinner-grow spinner-grow-sm text-success" role="status" style="width: 0.45rem; height: 0.45rem;"></span>
							<span>DHAN EMULATOR CONNECTED (:8088)</span>
						</span>
						<span class="badge bg-dark border border-warning border-opacity-35 rounded-pill px-2.5 py-1 text-warning font-monospace smaller d-inline-flex align-items-center gap-1 shadow-sm">
							<i class="bi bi-lightning-charge-fill text-warning"></i>
							<span>1.8ms LATENCY</span>
						</span>
						<span class="badge bg-dark border border-info border-opacity-35 rounded-pill px-2.5 py-1 text-info font-monospace smaller d-inline-flex align-items-center gap-1 shadow-sm">
							<i class="bi bi-cpu text-info"></i>
							<span>%s</span>
						</span>
					</div>
					<small class="theme-text-muted" style="font-size: 0.74rem;">±3 Strikes Active Window &bull; Real-time ATM Heatmap &bull; Synchronized Replay Feed</small>
				</div>
			</div>
			<div class="d-flex align-items-center gap-2.5 flex-wrap">
				<button type="button" id="btn-toggle-option-chain-strikes" class="btn btn-sm rounded-pill px-3 py-1 font-monospace fw-bold shadow-sm d-inline-flex align-items-center gap-1.5" style="border: 1px solid rgba(255, 255, 255, 0.15); background: rgba(255, 255, 255, 0.05); color: #ffffff; font-size: 0.74rem; cursor: pointer;" onclick="window.toggleOptionChainStrikesView && window.toggleOptionChainStrikesView()">
					<i class="bi bi-arrows-angle-expand" id="option-chain-expand-icon" style="color: #38bdf8;"></i>
					<span id="option-chain-expand-text">Expand (%d Strikes)</span>
				</button>
				<div class="d-flex align-items-center gap-2">
					<label class="smaller fw-bold text-muted text-uppercase d-none d-sm-inline mb-0" style="font-size: 0.74rem;">
						<i class="bi bi-database-fill-check me-1 text-warning"></i>Index:
					</label>
					<select name="index" class="form-select form-select-sm rounded-pill px-3 py-1.5 fw-bold font-monospace shadow-sm" style="background: #18181b; color: #fafafa; border: 1px solid rgba(255, 255, 255, 0.15); min-width: 150px; cursor: pointer;" hx-get="/mock/dashboard/option-chain" hx-target="#live-option-chain-container" hx-trigger="change">
						%s
					</select>
				</div>
				<button type="button" class="btn btn-sm btn-outline-secondary rounded-circle d-flex align-items-center justify-content-center shadow-sm" style="width: 34px; height: 34px; border-color: rgba(255,255,255,0.15);" hx-get="/mock/dashboard/option-chain?index=%s" hx-target="#live-option-chain-container" title="Refresh Option Chain">
					<i class="bi bi-arrow-repeat text-white"></i>
				</button>
			</div>
		</div>

		<!-- Pricing HUD -->
		<div class="py-2.5 px-4 border-bottom border-secondary border-opacity-15" style="background: rgba(255, 255, 255, 0.015);">
			<div class="row g-3 align-items-center">
				<div class="col-6 col-sm-6 col-md-3">
					<div class="d-flex flex-column">
						<span class="smaller fw-bold text-uppercase text-muted mb-0.5 d-flex align-items-center gap-1" style="font-size: 0.68rem;">
							<i class="bi bi-activity text-primary"></i>
							<span>Spot &bull; %s</span>
						</span>
						<div class="d-flex align-items-baseline gap-1.5 flex-wrap">
							<span id="emulator-option-chain-spot-ltp" class="fw-bold font-monospace fs-5 text-white">₹%s</span>
							<span id="emulator-option-chain-spot-change" class="badge %s rounded-pill px-1.5 py-0.5 font-monospace fw-bold" style="font-size: 0.65rem;">
								%s (%s)
							</span>
						</div>
						<div class="d-flex align-items-center gap-1 mt-1 flex-wrap">
							<span class="badge bg-secondary bg-opacity-25 text-white-50 font-monospace px-1.5 py-0.5 rounded-pill" style="font-size: 0.62rem;">
								PCR: <strong class="text-white">%.2f</strong>
							</span>
							<span class="badge bg-secondary bg-opacity-25 text-white-50 font-monospace px-1.5 py-0.5 rounded-pill" style="font-size: 0.62rem;">
								VIX: <strong class="text-warning" id="emulator-vix-ltp">%.2f</strong>
							</span>
						</div>
					</div>
				</div>
				<div class="col-6 col-sm-6 col-md-3">
					<span class="smaller fw-bold text-uppercase text-muted mb-0.5 d-block" style="font-size: 0.68rem;">
						<i class="bi bi-arrows-vertical text-warning me-1"></i>Day Range (H / L)
					</span>
					<div class="d-flex align-items-center justify-content-between font-monospace" style="font-size: 0.72rem;">
						<span class="text-muted">H: <strong class="text-success">₹%s</strong></span>
						<span class="text-muted">L: <strong class="text-danger">₹%s</strong></span>
					</div>
					<div class="progress mt-1" style="height: 3px; background: rgba(255, 255, 255, 0.08);">
						<div class="progress-bar bg-success" role="progressbar" style="width: 65%%;"></div>
					</div>
				</div>
				<div class="col-6 col-sm-6 col-md-3">
					<span class="smaller fw-bold text-uppercase text-muted mb-0.5 d-block" style="font-size: 0.68rem;">
						<i class="bi bi-clock-history text-info me-1"></i>Benchmarks
					</span>
					<div class="d-flex align-items-center justify-content-between font-monospace" style="font-size: 0.72rem;">
						<span class="text-muted">O: <strong class="text-white">₹%s</strong></span>
						<span class="text-muted">P: <strong class="text-white-50">₹%s</strong></span>
					</div>
					<div class="smaller text-muted mt-0.5 font-monospace" style="font-size: 0.65rem;">
						Step: <strong class="text-white">±%d pts</strong>
					</div>
				</div>
				<div class="col-6 col-sm-6 col-md-3">
					<div class="d-flex align-items-center justify-content-between">
						<div>
							<span class="smaller fw-bold text-uppercase text-muted mb-0.5 d-block" style="font-size: 0.68rem;">
								<i class="bi bi-bullseye text-danger me-1"></i>ATM
							</span>
							<span class="badge rounded-pill fw-bold font-monospace px-2.5 py-1 text-dark shadow-sm" style="background: #B4F105; font-size: 0.78rem;">
								%s
							</span>
						</div>
						<div class="text-end">
							<div class="d-flex align-items-center justify-content-end gap-1 mb-1">
								<span class="badge bg-info bg-opacity-15 text-info border border-info border-opacity-35 rounded-pill px-2.5 py-1 font-monospace fw-bold shadow-sm" style="font-size: 0.68rem;" id="emulator-option-chain-expiry">
									<i class="bi bi-calendar2-check-fill text-info me-1"></i>EXP: %s
								</span>
							</div>
							<div class="d-flex align-items-center justify-content-end gap-1.5 flex-wrap">
								<span class="badge bg-secondary bg-opacity-25 text-white-50 font-monospace px-1.5 py-0.5 rounded-pill" style="font-size: 0.60rem;">
									%s
								</span>
								<span class="smaller text-muted font-monospace" style="font-size: 0.62rem;">
									%s
								</span>
							</div>
						</div>
					</div>
				</div>
			</div>
		</div>

		<!-- Table -->
		<div class="table-responsive mb-0" style="overflow-x: auto; overflow-y: visible;">
			<table class="table table-custom align-middle mb-0 text-center smaller">
				<thead>
					<tr class="border-bottom" style="border-color: var(--border-color, rgba(255,255,255,0.08)) !important; background: rgba(0,0,0,0.3);">
						<th colspan="2" class="text-success border-end py-2.5" style="border-color: var(--border-color, rgba(255,255,255,0.08)) !important; width: 40%%; background: rgba(34, 197, 94, 0.05);">
							<i class="bi bi-graph-up-arrow me-1.5"></i>CALLS (CE) &bull; BULLISH
						</th>
						<th class="theme-text-main fw-bold py-2.5" style="width: 20%%; background: rgba(255, 255, 255, 0.02);">
							STRIKE
						</th>
						<th colspan="2" class="text-danger border-start py-2.5" style="border-color: var(--border-color, rgba(255,255,255,0.08)) !important; width: 40%%; background: rgba(239, 68, 68, 0.05);">
							PUTS (PE) &bull; BEARISH<i class="bi bi-graph-down-arrow ms-1.5"></i>
						</th>
					</tr>
					<tr class="smaller theme-text-muted border-bottom" style="border-color: var(--border-color, rgba(255,255,255,0.08)) !important; font-size: 0.72rem; background: rgba(0,0,0,0.15);">
						<th class="py-2">OI (Contracts)</th>
						<th class="border-end py-2" style="border-color: var(--border-color, rgba(255,255,255,0.08)) !important;">LTP &amp; Chg</th>
						<th class="py-2">Strike Price</th>
						<th class="border-start py-2" style="border-color: var(--border-color, rgba(255,255,255,0.08)) !important;">LTP &amp; Chg</th>
						<th class="py-2">OI (Contracts)</th>
					</tr>
				</thead>
				<tbody>
					%s
				</tbody>
			</table>
		</div>
	</div>`, chain.SpotSymbol, chain.FeedStatus, chain.TotalStrikes, idxOptions.String(), index, chain.SpotSymbol, chain.SpotLTP, badgeChangeClass, chain.SpotChange, chain.SpotChangePct, chain.PCR, chain.IndiaVIX, chain.HighPrice, chain.LowPrice, chain.OpenPrice, chain.PrevClose, chain.StrikeStep, chain.ATMStrike, chain.ExpiryDate, chain.ExpiryTag, chain.LastUpdated, rowsHtml.String())
}

// handleDashboardStreamerWidget renders real-time streaming data widget (Index Spot + Option Strikes).
func (h *Handler) handleDashboardStreamerWidget(w http.ResponseWriter, r *http.Request) {
	idxTicks, optTicks := h.streamer.GetStreamerWidgetData()
	isPlaying, _, _, _ := h.streamer.GetStatus()

	statusBadge := `<span class="badge bg-secondary bg-opacity-25 text-white-50 border border-white border-opacity-15 smaller font-monospace"><i class="bi bi-pause-circle me-1"></i> FEED PAUSED</span>`
	optBadge := `<span class="badge bg-secondary bg-opacity-25 text-white-50 smaller font-monospace">STANDBY</span>`
	if isPlaying {
		statusBadge = `<span class="badge bg-success bg-opacity-20 text-success border border-success border-opacity-30 smaller font-monospace"><i class="bi bi-circle-fill me-1" style="font-size: 0.45rem;"></i> LIVE FEED</span>`
		optBadge = fmt.Sprintf(`<span class="badge bg-info bg-opacity-20 text-info smaller font-monospace">%d Strikes Stream</span>`, len(optTicks))
	}

	var sb strings.Builder
	sb.WriteString(`<div class="row g-2">`)

	// Index Spot section
	sb.WriteString(fmt.Sprintf(`<div class="col-md-5"><div class="p-2 rounded-3 border border-white border-opacity-10 bg-dark bg-opacity-50"><div class="d-flex align-items-center justify-content-between mb-1 pb-1 border-bottom border-white border-opacity-5"><span class="smaller fw-bold text-uppercase text-secondary">Index Spot Feed</span>%s</div>`, statusBadge))
	if len(idxTicks) == 0 {
		sb.WriteString(`<div class="text-muted smaller py-2 text-center">Waiting for index ticks...</div>`)
	} else {
		for _, t := range idxTicks {
			sb.WriteString(fmt.Sprintf(`
			<div class="d-flex align-items-center justify-content-between py-1 border-bottom border-white border-opacity-5">
				<span class="fw-semibold text-white smaller">%s</span>
				<div class="text-end font-monospace">
					<span class="text-success fw-bold smaller">₹%.2f</span>
					<small class="text-secondary d-block" style="font-size: 0.68rem;">Vol: %d</small>
				</div>
			</div>`, t.TradingSymbol, t.LTP, t.Volume))
		}
	}
	sb.WriteString(`</div></div>`)

	// Option Strikes section
	sb.WriteString(fmt.Sprintf(`<div class="col-md-7"><div class="p-2 rounded-3 border border-white border-opacity-10 bg-dark bg-opacity-50"><div class="d-flex align-items-center justify-content-between mb-1 pb-1 border-bottom border-white border-opacity-5"><span class="smaller fw-bold text-uppercase text-secondary">Streaming Option Strikes (CE & PE)</span>%s</div>`, optBadge))
	if len(optTicks) == 0 {
		sb.WriteString(`<div class="text-muted smaller py-2 text-center">No active option ticks in this dataset window.</div>`)
	} else {
		count := 0
		for _, t := range optTicks {
			count++
			if count > 6 {
				break
			}
			badgeClass := "badge bg-primary bg-opacity-25 text-primary"
			if strings.Contains(strings.ToUpper(t.TradingSymbol), "PE") || strings.Contains(strings.ToUpper(t.TradingSymbol), "PUT") {
				badgeClass = "badge bg-danger bg-opacity-25 text-danger"
			}
			sb.WriteString(fmt.Sprintf(`
			<div class="d-flex align-items-center justify-content-between py-1 border-bottom border-white border-opacity-5">
				<div class="d-flex align-items-center gap-1.5">
					<span class="%s px-1.5 py-0.5 smaller font-monospace">%s</span>
					<span class="text-white smaller fw-semibold">%s</span>
				</div>
				<div class="text-end font-monospace">
					<span class="text-success fw-bold smaller">₹%.2f</span>
					<small class="text-secondary ms-1" style="font-size: 0.68rem;">H: %.1f L: %.1f</small>
				</div>
			</div>`, badgeClass, t.SecurityID, t.TradingSymbol, t.LTP, t.High, t.Low))
		}
	}
	sb.WriteString(`</div></div></div>`)

	fmt.Fprint(w, sb.String())
}

// handleDashboardTickers renders the top ticker tape partial for HTMX polling.
func (h *Handler) handleDashboardTickers(w http.ResponseWriter, r *http.Request) {
	ticks := h.streamer.GetLatestTicks()

	niftyDisplay := "— (STANDBY)"
	niftyClass := "text-secondary"
	if t, ok := ticks["13"]; ok && t.LTP > 0 {
		niftyDisplay = fmt.Sprintf("₹%.2f", t.LTP)
		niftyClass = "text-success"
	} else if t, ok := ticks["NIFTY"]; ok && t.LTP > 0 {
		niftyDisplay = fmt.Sprintf("₹%.2f", t.LTP)
		niftyClass = "text-success"
	}

	vixDisplay := "—"
	vixClass := "text-secondary"
	if t, ok := ticks["INDIAVIX"]; ok && t.LTP > 0 {
		vixDisplay = fmt.Sprintf("%.2f", t.LTP)
		vixClass = "text-danger"
	} else if t, ok := ticks["INDIA VIX"]; ok && t.LTP > 0 {
		vixDisplay = fmt.Sprintf("%.2f", t.LTP)
		vixClass = "text-danger"
	}

	fmt.Fprintf(w, `
	<div class="d-flex align-items-center gap-4 text-nowrap">
		<div class="d-flex align-items-baseline gap-2">
			<span class="badge bg-success bg-opacity-20 text-success rounded-pill px-2 py-0.5 smaller fw-bold font-monospace">FEEDING INDEX</span>
			<span class="fw-bold text-light smaller">NIFTY 50</span>
			<span class="font-monospace fw-bold %s">%s</span>
		</div>
		<div class="vr bg-secondary opacity-25" style="height: 16px;"></div>
		<div class="d-flex align-items-baseline gap-2">
			<span class="badge bg-danger bg-opacity-20 text-danger rounded-pill px-2 py-0.5 smaller fw-bold font-monospace">CONCURRENT VIX</span>
			<span class="fw-bold text-light smaller">INDIA VIX</span>
			<span class="font-monospace fw-bold %s">%s</span>
		</div>
	</div>`, niftyClass, niftyDisplay, vixClass, vixDisplay)
}

// handleDashboardStreamer renders the streamer status partial for HTMX polling.
func (h *Handler) handleDashboardStreamer(w http.ResponseWriter, r *http.Request) {
	h.handleDashboardProgress(w, r)
}

// handleDashboardPositions renders positions partial for HTMX polling.
func (h *Handler) handleDashboardPositions(w http.ResponseWriter, r *http.Request) {
	clientID := h.resolveClientID(r)
	positions := h.engine.GetPositions(clientID)
	if len(positions) == 0 {
		allPositions := h.engine.GetAllPositions()
		if len(allPositions) > 0 {
			positions = allPositions
		}
	}
	if len(positions) == 0 {
		fmt.Fprintf(w, `<div class="p-4 text-center text-secondary small"><i class="bi bi-inbox fs-3 d-block mb-2 text-muted opacity-50"></i>No active positions for Account <span class="text-white fw-bold">%s</span>. Orders placed by Marmot strategies will appear here in real-time.</div>`, clientID)
		return
	}

	var totalRealized, totalUnrealized float64
	var sb strings.Builder
	sb.WriteString(`<table class="table table-dark table-hover align-middle mb-0"><thead class="text-secondary small text-uppercase"><tr><th>Symbol</th><th>Type</th><th>Product</th><th>Net Qty</th><th>Buy Avg</th><th>Sell Avg</th><th>SL</th><th>TP</th><th>Entry Time</th><th>Exit Time</th><th>Realized</th><th>MTM</th><th>Total P&L</th></tr></thead><tbody>`)
	for _, p := range positions {
		totalRealized += p.RealizedProfit
		totalUnrealized += p.UnrealizedProfit
		totalPL := p.RealizedProfit + p.UnrealizedProfit

		plColor := "text-success"
		if totalPL < 0 {
			plColor = "text-danger"
		}
		posTypeBadge := `<span class="badge bg-primary bg-opacity-25 text-primary border border-primary border-opacity-50">LONG</span>`
		if p.PositionType == "SHORT" {
			posTypeBadge = `<span class="badge bg-danger bg-opacity-25 text-danger border border-danger border-opacity-50">SHORT</span>`
		} else if p.PositionType == "CLOSED" {
			posTypeBadge = `<span class="badge bg-secondary bg-opacity-25 text-secondary border border-secondary border-opacity-50">CLOSED</span>`
		}

		slDisplay := "-"
		if p.StopLoss > 0 {
			slDisplay = fmt.Sprintf("₹%.2f", p.StopLoss)
		}
		tpDisplay := "-"
		if p.TakeProfit > 0 {
			tpDisplay = fmt.Sprintf("₹%.2f", p.TakeProfit)
		}
		entryDisplay := p.EntryTime
		if entryDisplay == "" {
			entryDisplay = "-"
		}
		exitDisplay := p.ExitTime
		if exitDisplay == "" {
			exitDisplay = "-"
		}

		sb.WriteString(fmt.Sprintf(`<tr><td class="fw-semibold text-white">%s</td><td>%s</td><td class="small text-secondary">%s</td><td class="font-monospace fw-bold">%d</td><td>₹%.2f</td><td>₹%.2f</td><td class="font-monospace text-danger small">%s</td><td class="font-monospace text-success small">%s</td><td class="small text-secondary font-monospace">%s</td><td class="small text-secondary font-monospace">%s</td><td class="font-monospace">₹%.2f</td><td class="font-monospace %s">₹%.2f</td><td class="font-monospace fw-bold %s">₹%.2f</td></tr>`,
			p.TradingSymbol, posTypeBadge, p.ProductType, p.NetQty, p.BuyAvg, p.SellAvg, slDisplay, tpDisplay, entryDisplay, exitDisplay, p.RealizedProfit, plColor, p.UnrealizedProfit, plColor, totalPL))
	}
	sb.WriteString(`</tbody></table>`)
	fmt.Fprint(w, sb.String())
}

// handleDashboardOrders renders the table rows partial for HTMX polling.
func (h *Handler) handleDashboardOrders(w http.ResponseWriter, r *http.Request) {
	clientID := h.resolveClientID(r)
	orders := h.engine.GetOrders(clientID)
	if len(orders) == 0 {
		orders = h.engine.GetAllOrders()
	}
	if len(orders) == 0 {
		fmt.Fprintf(w, `<table class="table table-dark table-hover align-middle mb-0"><tbody><tr><td colspan="11" class="text-center text-secondary py-4"><i class="bi bi-receipt fs-3 d-block mb-2 text-muted opacity-50"></i>No mock orders recorded yet for Account <span class="text-white fw-bold">%s</span>. Place an order from Marmot to observe execution lifecycle.</td></tr></tbody></table>`, clientID)
		return
	}

	var sb strings.Builder
	sb.WriteString(`<table class="table table-dark table-hover align-middle mb-0"><thead class="text-secondary small text-uppercase"><tr><th>Order ID</th><th>Time</th><th>Symbol</th><th>Side</th><th>Segment</th><th>Type</th><th>Qty / Filled</th><th>Price / Avg</th><th>SL</th><th>TP</th><th>Status</th></tr></thead><tbody>`)
	for _, o := range orders {
		statusBadge := fmt.Sprintf(`<span class="badge badge-%s">%s</span>`, strings.ToLower(o.Status), o.Status)
		sideBadge := `<span class="badge bg-primary bg-opacity-25 text-primary border border-primary border-opacity-50">BUY</span>`
		if o.Order.TransactionType == "SELL" {
			sideBadge = `<span class="badge bg-danger bg-opacity-25 text-danger border border-danger border-opacity-50">SELL</span>`
		}
		sym := o.Order.CorrelationID
		if sym == "" {
			sym = o.Order.SecurityID
		}

		slDisplay := "-"
		if o.StopLoss > 0 {
			slDisplay = fmt.Sprintf("₹%.2f", o.StopLoss)
		}
		tpDisplay := "-"
		if o.TakeProfit > 0 {
			tpDisplay = fmt.Sprintf("₹%.2f", o.TakeProfit)
		}

		sb.WriteString(fmt.Sprintf(`<tr><td class="font-monospace text-info">%s</td><td class="small text-secondary font-monospace">%s</td><td class="fw-semibold text-white">%s</td><td>%s</td><td class="small text-secondary">%s</td><td class="small text-secondary">%s</td><td>%d / %d</td><td>₹%.2f / ₹%.2f</td><td class="small text-danger font-monospace">%s</td><td class="small text-success font-monospace">%s</td><td>%s</td></tr>`,
			o.OrderID, o.CreatedAt.Format("15:04:05"), sym, sideBadge, o.Order.ExchangeSegment, o.Order.OrderType, o.Order.Quantity, o.FilledQty, o.Order.Price, o.FilledPrice, slDisplay, tpDisplay, statusBadge))
	}
	sb.WriteString(`</tbody></table>`)
	fmt.Fprint(w, sb.String())
}

// handleAdjustFunds allows depositing/withdrawing virtual cash.
func (h *Handler) handleAdjustFunds(w http.ResponseWriter, r *http.Request) {
	clientID := h.resolveClientID(r)
	amountStr := r.URL.Query().Get("amount")
	amount, _ := strconv.ParseFloat(amountStr, 64)
	h.engine.DepositWithdraw(clientID, amount)
	h.handleDashboardFunds(w, r)
}

// handleUpdateChaos updates token bucket RPS and drop/delay webhook modes.
func (h *Handler) handleUpdateChaos(w http.ResponseWriter, r *http.Request) {
	r.ParseForm()
	rpsStr := r.FormValue("rps")
	if rps, err := strconv.Atoi(rpsStr); err == nil {
		h.chaos.SetRPS(rps)
	}
	modeStr := r.FormValue("mode")
	if modeStr != "" {
		h.chaos.SetMode(engine.ChaosMode(modeStr))
	}
	w.WriteHeader(http.StatusOK)
}



// handleStreamerToggle toggles market feed playback.
func (h *Handler) handleStreamerToggle(w http.ResponseWriter, r *http.Request) {
	isPlaying, _, _, _ := h.streamer.GetStatus()
	if isPlaying {
		h.streamer.Stop()
	} else {
		h.streamer.Start()
	}
	w.Header().Set("HX-Trigger", "reloadMockOptionChain")
	h.handleDashboardControls(w, r)
}

// handleStreamerStop immediately pauses and halts market feed playback.
func (h *Handler) handleStreamerStop(w http.ResponseWriter, r *http.Request) {
	h.streamer.Stop()
	w.Header().Set("HX-Trigger", `{"reloadMockOptionChain": true, "replayStopped": true}`)
	h.handleDashboardControls(w, r)
}

// handleStreamerRestart resets replay to row 0 and begins streaming.
func (h *Handler) handleStreamerRestart(w http.ResponseWriter, r *http.Request) {
	h.streamer.Restart()
	w.Header().Set("HX-Trigger", `{"reloadMockOptionChain": true, "replayRestarted": true}`)
	h.handleDashboardControls(w, r)
}

// handleStreamerSpeed adjusts tick playback speed.
func (h *Handler) handleStreamerSpeed(w http.ResponseWriter, r *http.Request) {
	valStr := r.URL.Query().Get("val")
	if valStr == "" {
		_ = r.ParseForm()
		valStr = r.FormValue("val")
	}
	if val, err := strconv.Atoi(valStr); err == nil {
		h.streamer.SetSpeed(val)
	}
	if r.Header.Get("Accept") == "application/json" {
		w.Header().Set("Content-Type", "application/json")
		_, speed, _, _ := h.streamer.GetStatus()
		_ = json.NewEncoder(w).Encode(map[string]interface{}{"success": true, "speed": speed})
		return
	}
	h.handleDashboardControls(w, r)
}

// handleStreamerSelect selects a specific parquet dataset.
func (h *Handler) handleStreamerSelect(w http.ResponseWriter, r *http.Request) {
	r.ParseForm()
	file := r.FormValue("file")
	if file == "" {
		file = r.URL.Query().Get("file")
	}
	if file != "" {
		h.streamer.SelectParquetFile(file)
	}

	toastTitle := "Dataset Selected"
	toastType := "info"
	toastMsg := fmt.Sprintf("Replaying %s", file)
	if strings.Contains(file, "48/dataset") || strings.Contains(file, "35/dataset") {
		toastType = "success"
		toastMsg = fmt.Sprintf("Full Bilateral Options feed active (%s)", file)
	} else if strings.Contains(file, "33/dataset") || strings.Contains(file, "60/dataset") {
		toastMsg = fmt.Sprintf("Single-leg options active (%s)", file)
	} else if strings.Contains(file, "macro") {
		toastTitle = "Macro Sentiment Feed"
		toastType = "warning"
		toastMsg = fmt.Sprintf("%s is Macro AI sentiment only (no option strikes)", file)
	}
	w.Header().Set("HX-Trigger", fmt.Sprintf(`{"reloadMockOptionChain": true, "showToast": {"title": "%s", "message": "%s", "type": "%s"}}`, toastTitle, toastMsg, toastType))
	h.handleDashboardControls(w, r)
}

// handleStreamerFiles returns JSON list of available parquet files.
func (h *Handler) handleStreamerFiles(w http.ResponseWriter, r *http.Request) {
	files := h.streamer.ListParquetDetails()
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(files)
}

// handleStreamerStatus returns current operational status and progress metrics in JSON format.
func (h *Handler) handleStreamerStatus(w http.ResponseWriter, r *http.Request) {
	isPlaying, speed, currentFile, ticks := h.streamer.GetStatus()
	curRow, totRows, pct, curDt, curDate := h.streamer.GetProgress()
	isCompleted := h.streamer.IsCompleted()

	curTime := "09:15:00"
	if strings.Contains(curDt, " ") {
		parts := strings.Split(curDt, " ")
		if len(parts) >= 2 {
			curTime = parts[1]
		}
	} else if curDt != "" {
		curTime = curDt
	}

	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Access-Control-Allow-Origin", "*")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"success":        true,
		"is_playing":     isPlaying,
		"current_speed":  speed,
		"speed":          speed,
		"active_file":    currentFile,
		"current_date":   curDate,
		"current_time":   curTime,
		"datetime":       curDt,
		"current_row":    curRow,
		"total_rows":     totRows,
		"progress_pct":   pct,
		"ticks_ingested": ticks,
		"is_completed":   isCompleted,
	})
}

// handleKillSwitch triggers emergency cancellation across all orders.
func (h *Handler) handleKillSwitch(w http.ResponseWriter, r *http.Request) {
	cancelled := h.engine.KillSwitch()
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"status":    "success",
		"cancelled": cancelled,
		"message":   fmt.Sprintf("Cancelled %d pending orders", cancelled),
	})
}


// handleClearSession soft-deletes and resets mock orders and positions for active account.
func (h *Handler) handleClearSession(w http.ResponseWriter, r *http.Request) {
	clientID := h.resolveClientID(r)
	h.engine.ClearAccountSession(clientID)
	w.Header().Set("HX-Trigger", `{"brokerOrderUpdate": true, "showToast": {"title": "Session Cleared", "message": "Mock orders & positions reset to initial state", "type": "info"}}`)
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"status":  "success",
		"message": "Mock session cleared successfully",
	})
}

// handleManualTick ingests a tick directly into the matching engine for testing & manual simulation.
func (h *Handler) handleManualTick(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}
	var tick models.MarketTick
	if err := json.NewDecoder(r.Body).Decode(&tick); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	if tick.Timestamp.IsZero() {
		tick.Timestamp = time.Now()
	}
	h.engine.IngestTick(tick)
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"status": "ok",
		"tick":   tick,
	})
}

// =========================================================================
// ACCOUNT SETUP, SWITCHER & HTMX CRUD MODAL HANDLERS
// =========================================================================

// handleAccountDropdown renders the top navbar account switcher button & dropdown.
func (h *Handler) handleAccountDropdown(w http.ResponseWriter, r *http.Request) {
	accounts := h.engine.GetAllAccounts()
	activeID := h.engine.GetActiveAccountID()
	var activeAcc *engine.ClientAccount
	for _, acc := range accounts {
		if acc.DhanClientID == activeID {
			activeAcc = acc
			break
		}
	}
	if activeAcc == nil && len(accounts) > 0 {
		activeAcc = accounts[0]
		activeID = activeAcc.DhanClientID
	}

	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	var sb strings.Builder

	brokerBadge := "bg-primary"
	brokerName := "Dhan"
	accName := "Primary Trading"
	balance := 500000.0
	if activeAcc != nil {
		brokerName = activeAcc.Broker
		accName = activeAcc.AccountName
		balance = activeAcc.AvailableBalance
		if strings.EqualFold(brokerName, "fyers") {
			brokerBadge = "bg-info"
		} else if strings.Contains(strings.ToLower(brokerName), "zerodha") {
			brokerBadge = "bg-warning"
		}
	}

	sb.WriteString(fmt.Sprintf(`
	<div class="dropdown custom-account-dropdown" id="account-switcher-wrapper">
		<button class="btn btn-sm dropdown-toggle d-inline-flex align-items-center gap-2 px-3 py-1.5 rounded-pill shadow-sm"
				type="button" data-bs-toggle="dropdown" aria-expanded="false"
				style="background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.12); color: #fafafa; font-size: 0.8rem;">
			<span class="badge %s bg-opacity-25 text-white border border-white border-opacity-20 px-2 py-0.5 font-monospace" style="font-size: 0.7rem;">%s</span>
			<span class="fw-semibold font-monospace">%s</span>
			<span class="opacity-50">•</span>
			<span class="text-truncate d-none d-md-inline" style="max-width: 130px;">%s</span>
			<span class="badge bg-success bg-opacity-20 text-success border border-success border-opacity-30 font-monospace ms-1">₹%.0f</span>
			<i class="bi bi-chevron-down opacity-60 ms-0.5" style="font-size: 0.7rem;"></i>
		</button>
		<ul class="dropdown-menu dropdown-menu-dark dropdown-menu-end shadow-lg p-2 rounded-3 border border-white border-opacity-10"
			style="min-width: 330px; background: #121215; backdrop-filter: blur(20px); z-index: 1070;">
			<li class="px-2 py-1.5 text-uppercase small text-secondary fw-bold" style="font-size: 0.68rem; letter-spacing: 0.5px;">
				<i class="bi bi-briefcase me-1"></i> Active Broker Accounts
			</li>
	`, brokerBadge, brokerName, activeID, accName, balance))

	for _, acc := range accounts {
		isActive := acc.DhanClientID == activeID
		activeClass := ""
		checkIcon := ""
		if isActive {
			activeClass = "border-primary bg-primary bg-opacity-10"
			checkIcon = `<i class="bi bi-check-circle-fill text-primary ms-auto"></i>`
		}
		bBadge := "bg-primary"
		if strings.EqualFold(acc.Broker, "fyers") {
			bBadge = "bg-info"
		} else if strings.Contains(strings.ToLower(acc.Broker), "zerodha") {
			bBadge = "bg-warning"
		}

		sb.WriteString(fmt.Sprintf(`
			<li>
				<a class="dropdown-item rounded-2 p-2 mb-1 d-flex align-items-center gap-2.5 text-white %s"
				   href="#"
				   hx-post="/mock/accounts/select?id=%s"
				   hx-target="#account-switcher-wrapper"
				   hx-swap="outerHTML">
					<div class="rounded-circle d-flex align-items-center justify-content-center flex-shrink-0" style="width: 32px; height: 32px; background: rgba(255,255,255,0.06);">
						<i class="bi bi-person-fill text-light opacity-75"></i>
					</div>
					<div class="flex-grow-1 overflow-hidden">
						<div class="d-flex align-items-center gap-1.5">
							<span class="badge %s bg-opacity-25 text-white border border-white border-opacity-15 font-monospace" style="font-size: 0.65rem;">%s</span>
							<span class="font-monospace fw-bold small text-truncate">%s</span>
						</div>
						<div class="smaller text-secondary text-truncate mt-0.5">%s</div>
					</div>
					<div class="text-end font-monospace ms-2">
						<div class="smaller text-success fw-bold">₹%.0f</div>
						<div class="text-secondary" style="font-size: 0.65rem;">%d Orders</div>
					</div>
					%s
				</a>
			</li>
		`, activeClass, acc.DhanClientID, bBadge, acc.Broker, acc.DhanClientID, acc.AccountName, acc.AvailableBalance, len(acc.Orders), checkIcon))
	}

	sb.WriteString(`
			<li><hr class="dropdown-divider my-1 border-white border-opacity-10"></li>
			<li>
				<a class="dropdown-item rounded-2 py-2 px-2.5 text-info d-flex align-items-center gap-2 small fw-semibold"
				   href="#"
				   hx-get="/mock/accounts/modal/create"
				   hx-target="#globalHtmxModalDialog">
					<i class="bi bi-plus-circle-fill fs-6 text-info"></i>
					<span>Add New Broker Account...</span>
				</a>
			</li>
			<li>
				<a class="dropdown-item rounded-2 py-2 px-2.5 text-white-50 d-flex align-items-center gap-2 small"
				   href="#"
				   hx-get="/mock/accounts/modal/list"
				   hx-target="#globalHtmxModalDialog">
					<i class="bi bi-gear-wide-connected fs-6 text-warning"></i>
					<span>Manage Accounts Directory</span>
				</a>
			</li>
		</ul>
	</div>
	`)

	fmt.Fprint(w, sb.String())
}

// handleAccountSelect sets the active account context and updates cookie and triggers.
func (h *Handler) handleAccountSelect(w http.ResponseWriter, r *http.Request) {
	id := r.URL.Query().Get("id")
	if id == "" {
		id = r.FormValue("id")
	}
	var accName string
	if id != "" {
		_ = h.engine.SetActiveAccountID(id)
		if acc, ok := h.engine.GetAccount(id); ok {
			accName = acc.AccountName
		}
		http.SetCookie(w, &http.Cookie{
			Name:     "marmot_mock_client_id",
			Value:    id,
			Path:     "/",
			MaxAge:   86400 * 30,
			HttpOnly: false,
		})
		go h.engine.BroadcastAccountStats(id)
	}
	if accName == "" {
		accName = id
	}
	toastPayload, _ := json.Marshal(map[string]interface{}{
		"accountChanged": true,
		"closeModal":     true,
		"showToast": map[string]interface{}{
			"title":   "Account Selected",
			"message": fmt.Sprintf("Active mock account switched to %s (ID: %s)", accName, id),
			"type":    "success",
		},
	})
	w.Header().Set("HX-Trigger", string(toastPayload))
	h.handleAccountDropdown(w, r)
}

// handleAccountModalCreate renders the modal form for adding a new mock account.
func (h *Handler) handleAccountModalCreate(w http.ResponseWriter, r *http.Request) {
	suggestedID := fmt.Sprintf("100000%04d", len(h.engine.GetAllAccounts())+1)

	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	fmt.Fprintf(w, `
	<div class="modal-content shadow-2xl rounded-4 overflow-hidden"
	     style="background: #0c0c0e; border: 1px solid rgba(255, 255, 255, 0.08); color: #fafafa;">
		<div class="modal-header py-3 px-4 d-flex justify-content-between align-items-center"
		     style="border-bottom: 1px solid rgba(255, 255, 255, 0.06); background: rgba(255, 255, 255, 0.02);">
			<div class="d-flex align-items-center gap-2.5">
				<div class="rounded-circle bg-primary bg-opacity-20 text-primary d-flex align-items-center justify-content-center" style="width: 36px; height: 36px;">
					<i class="bi bi-person-plus-fill fs-5"></i>
				</div>
				<div>
					<h5 class="modal-title fs-6 fw-bold mb-0 text-white">Add Broker Account</h5>
					<small class="text-secondary" style="font-size: 0.72rem;">Set up an isolated multi-broker ledger for simulated trading</small>
				</div>
			</div>
			<button type="button" class="btn-close btn-close-white opacity-50" data-bs-dismiss="modal" aria-label="Close"></button>
		</div>

		<form hx-post="/mock/accounts/create" hx-target="#globalHtmxModalDialog">
			<div class="modal-body p-4 d-flex flex-column gap-3">
				<div class="row g-3">
					<div class="col-md-6">
						<label class="form-label text-secondary small fw-semibold mb-1">Dhan Client ID</label>
						<input type="text" name="client_id" class="form-control font-monospace"
						       style="background: #141416; border: 1px solid rgba(255, 255, 255, 0.09); color: #fafafa;"
						       value="%s" required placeholder="e.g. 1000000003">
					</div>
					<div class="col-md-6">
						<label class="form-label text-secondary small fw-semibold mb-1">Broker Gateway</label>
						<select name="broker" class="form-select"
						        style="background: #141416; border: 1px solid rgba(255, 255, 255, 0.09); color: #fafafa;">
							<option value="Dhan" selected>Dhan (HQ Execution)</option>
							<option value="Fyers">Fyers (Data Feed &amp; API)</option>
							<option value="Zerodha Mock">Zerodha Kite (Mock)</option>
							<option value="Angel One Mock">Angel One SmartAPI (Mock)</option>
						</select>
					</div>
				</div>

				<div>
					<label class="form-label text-secondary small fw-semibold mb-1">Account Display Name</label>
					<input type="text" name="name" class="form-control"
					       style="background: #141416; border: 1px solid rgba(255, 255, 255, 0.09); color: #fafafa;"
					       placeholder="e.g. Momentum Breakout Alpha" required value="Trading Account %s">
				</div>

				<div>
					<label class="form-label text-secondary small fw-semibold mb-1">Initial Virtual Balance (INR)</label>
					<div class="input-group">
						<span class="input-group-text" style="background: #18181b; border: 1px solid rgba(255, 255, 255, 0.09); color: #a1a1aa;">₹</span>
						<input type="number" name="initial_balance" step="10000" min="10000" class="form-control font-monospace"
						       style="background: #141416; border: 1px solid rgba(255, 255, 255, 0.09); color: #fafafa;"
						       value="500000">
					</div>
					<small class="text-secondary" style="font-size: 0.7rem;">Virtual cash limit allocated for intraday margin and option premiums.</small>
				</div>

				<div class="form-check form-switch mt-1">
					<input class="form-check-input" type="checkbox" name="set_active" id="setActiveSwitch" checked value="true">
					<label class="form-check-label text-light small" for="setActiveSwitch">
						Set as Active Account immediately upon creation
					</label>
				</div>
			</div>

			<div class="modal-footer py-3 px-4 d-flex justify-content-between"
			     style="border-top: 1px solid rgba(255, 255, 255, 0.06); background: rgba(255, 255, 255, 0.02);">
				<button type="button" class="btn btn-sm btn-outline-secondary px-3" data-bs-dismiss="modal">Cancel</button>
				<button type="submit" class="btn btn-sm btn-primary px-4 fw-bold d-inline-flex align-items-center gap-1.5">
					<i class="bi bi-check-lg"></i>
					<span>Create Account</span>
				</button>
			</div>
		</form>
	</div>
	`, suggestedID, suggestedID)
}

// handleAccountCreate creates an account, activates it, and triggers dashboard updates.
func (h *Handler) handleAccountCreate(w http.ResponseWriter, r *http.Request) {
	r.ParseForm()
	clientID := strings.TrimSpace(r.FormValue("client_id"))
	name := strings.TrimSpace(r.FormValue("name"))
	broker := strings.TrimSpace(r.FormValue("broker"))
	balanceStr := strings.TrimSpace(r.FormValue("initial_balance"))
	setActive := r.FormValue("set_active") == "true"

	balance, _ := strconv.ParseFloat(balanceStr, 64)
	if balance <= 0 {
		balance = 500000.0
	}

	acc, err := h.engine.CreateAccount(clientID, name, broker, balance)
	if err != nil {
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		fmt.Fprintf(w, `
		<div class="modal-content shadow-2xl rounded-4 overflow-hidden"
		     style="background: #140d0e; border: 1px solid rgba(239, 68, 68, 0.25); color: #fafafa;">
			<div class="modal-body p-4 text-center">
				<i class="bi bi-exclamation-triangle-fill text-danger fs-1 mb-2 d-block"></i>
				<h5 class="fw-bold text-white mb-2">Failed to Create Account</h5>
				<p class="text-secondary small mb-4">%s</p>
				<button class="btn btn-sm btn-outline-secondary px-4" hx-get="/mock/accounts/modal/create" hx-target="#globalHtmxModalDialog">Try Again</button>
			</div>
		</div>
		`, err.Error())
		return
	}

	if setActive {
		_ = h.engine.SetActiveAccountID(acc.DhanClientID)
		http.SetCookie(w, &http.Cookie{
			Name:     "marmot_mock_client_id",
			Value:    acc.DhanClientID,
			Path:     "/",
			MaxAge:   86400 * 30,
			HttpOnly: false,
		})
	}

	toastMsg := fmt.Sprintf("Account %s (%s) created successfully", acc.DhanClientID, acc.AccountName)
	w.Header().Set("HX-Trigger", fmt.Sprintf(`{"accountChanged": true, "closeModal": true, "showToast": {"title": "Account Created", "message": "%s", "type": "success"}}`, toastMsg))
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	fmt.Fprintf(w, `
	<div class="modal-content shadow-2xl rounded-4 overflow-hidden text-center p-4"
	     style="background: #0c0c0e; border: 1px solid rgba(16, 185, 129, 0.25); color: #fafafa;">
		<i class="bi bi-check-circle-fill text-success fs-1 mb-2 d-block"></i>
		<h5 class="fw-bold text-white mb-1">Account Created Successfully</h5>
		<p class="text-secondary small mb-0">Account <strong class="text-info">%s (%s)</strong> is ready for paper simulation.</p>
	</div>
	`, acc.DhanClientID, acc.AccountName)
}

// handleAccountModalList renders the full accounts directory modal table with CRUD actions.
func (h *Handler) handleAccountModalList(w http.ResponseWriter, r *http.Request) {
	accounts := h.engine.GetAllAccounts()
	activeID := h.engine.GetActiveAccountID()

	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	var sb strings.Builder

	sb.WriteString(`
	<div class="modal-content shadow-2xl rounded-4 overflow-hidden w-100"
	     style="background: #0c0c0e; border: 1px solid rgba(255, 255, 255, 0.08); color: #fafafa;">
		<div class="modal-header py-3 px-4 d-flex justify-content-between align-items-center"
		     style="border-bottom: 1px solid rgba(255, 255, 255, 0.06); background: rgba(255, 255, 255, 0.02);">
			<div class="d-flex align-items-center gap-2.5">
				<div class="rounded-circle bg-warning bg-opacity-20 text-warning d-flex align-items-center justify-content-center" style="width: 38px; height: 38px;">
					<i class="bi bi-briefcase-fill fs-5"></i>
				</div>
				<div>
					<h5 class="modal-title fs-6 fw-bold mb-0 text-white">Mock Broker Accounts Directory</h5>
					<small class="text-secondary" style="font-size: 0.74rem;">Manage isolated ledger balances, platform routing, and simulated portfolios</small>
				</div>
			</div>
			<div class="d-flex align-items-center gap-2">
				<button class="btn btn-sm btn-primary px-3 py-1.5 fw-semibold d-inline-flex align-items-center gap-1.5 rounded-pill shadow-sm"
				        hx-get="/mock/accounts/modal/create" hx-target="#globalHtmxModalDialog" style="font-size: 0.78rem;">
					<i class="bi bi-plus-lg"></i>
					<span>Add Account</span>
				</button>
				<button type="button" class="btn-close btn-close-white opacity-50 ms-2" data-bs-dismiss="modal" aria-label="Close"></button>
			</div>
		</div>

		<div class="modal-body p-3 overflow-auto" style="max-height: 520px;">
			<table class="table table-dark table-hover align-middle mb-0" style="font-size: 0.82rem; background: transparent;">
				<thead class="text-secondary text-uppercase smaller" style="border-bottom: 1px solid rgba(255, 255, 255, 0.08);">
					<tr>
						<th style="min-width: 180px;">Account / ID</th>
						<th style="min-width: 100px;">Broker</th>
						<th style="min-width: 140px;">Available Balance</th>
						<th style="min-width: 130px;">SOD / Utilized</th>
						<th style="min-width: 90px;">Positions</th>
						<th style="min-width: 80px;">Orders</th>
						<th style="min-width: 110px;">Status</th>
						<th class="text-end" style="min-width: 200px;">Actions</th>
					</tr>
				</thead>
				<tbody>
	`)

	for _, acc := range accounts {
		isActive := acc.DhanClientID == activeID
		bBadge := "bg-primary"
		if strings.EqualFold(acc.Broker, "fyers") {
			bBadge = "bg-info"
		} else if strings.Contains(strings.ToLower(acc.Broker), "zerodha") {
			bBadge = "bg-warning"
		}

		statusBadge := `<span class="badge bg-secondary bg-opacity-20 text-secondary border border-secondary border-opacity-25 px-2.5 py-1 rounded-pill fw-medium">STANDBY</span>`
		switchBtn := fmt.Sprintf(`
			<button class="btn btn-sm btn-outline-primary px-3 py-1 rounded-pill fw-semibold shadow-sm"
			        hx-post="/mock/accounts/select?id=%s"
			        hx-target="#account-switcher-wrapper"
			        hx-swap="outerHTML"
			        onclick="closeGlobalModal()"
			        style="font-size: 0.75rem;"
			        title="Switch active context">
				<i class="bi bi-box-arrow-in-right me-1"></i>Select
			</button>
		`, acc.DhanClientID)

		if isActive {
			statusBadge = `<span class="badge bg-success bg-opacity-20 text-success border border-success border-opacity-30 px-2.5 py-1 rounded-pill fw-bold"><i class="bi bi-record-fill me-1"></i>ACTIVE</span>`
			switchBtn = `<button class="btn btn-sm btn-success px-3 py-1 rounded-pill fw-bold text-white shadow-sm" disabled style="opacity: 0.95; font-size: 0.75rem;"><i class="bi bi-check2-circle me-1"></i>Active</button>`
		}

		openPos := 0
		for _, p := range acc.Positions {
			if p.NetQty != 0 {
				openPos++
			}
		}

		sb.WriteString(fmt.Sprintf(`
			<tr>
				<td>
					<div class="fw-bold text-white font-monospace" style="font-size: 0.88rem;">%s</div>
					<div class="smaller text-secondary text-truncate" style="max-width: 220px;">%s</div>
				</td>
				<td>
					<span class="badge %s bg-opacity-25 text-white border border-secondary border-opacity-25 font-monospace px-2.5 py-1 rounded-pill" style="font-size: 0.72rem;">%s</span>
				</td>
				<td class="font-monospace text-success fw-bold" style="font-size: 0.9rem;">₹%.2f</td>
				<td class="font-monospace text-secondary smaller">
					<div><span class="text-white-50">SOD:</span> ₹%.0f</div>
					<div><span class="text-white-50">Utl:</span> ₹%.0f</div>
				</td>
				<td class="font-monospace">
					<span class="badge %s rounded-pill px-2.5 py-1">%d</span>
				</td>
				<td class="font-monospace text-secondary">
					<span class="badge bg-secondary bg-opacity-20 text-light rounded-pill px-2 py-0.5">%d</span>
				</td>
				<td>%s</td>
				<td class="text-end">
					<div class="d-inline-flex align-items-center gap-2">
						%s
						<div class="btn-group btn-group-sm shadow-sm" role="group">
							<button class="btn btn-outline-info px-2 py-1"
							        hx-get="/mock/accounts/modal/detail?id=%s"
							        hx-target="#globalHtmxModalDialog"
							        title="View telemetry details">
								<i class="bi bi-info-circle"></i>
							</button>
							<button class="btn btn-outline-warning px-2 py-1"
							        hx-get="/mock/accounts/modal/edit?id=%s"
							        hx-target="#globalHtmxModalDialog"
							        title="Edit details &amp; adjust virtual cash">
								<i class="bi bi-pencil"></i>
							</button>
							<button class="btn btn-outline-danger px-2 py-1"
							        hx-get="/mock/accounts/modal/delete-confirm?id=%s"
							        hx-target="#globalHtmxModalDialog"
							        title="Delete Account">
								<i class="bi bi-trash"></i>
							</button>
						</div>
					</div>
				</td>
			</tr>
		`, acc.DhanClientID, acc.AccountName, bBadge, acc.Broker, acc.AvailableBalance, acc.SodLimit, acc.UtilizedMargin,
			func() string {
				if openPos > 0 {
					return "bg-warning bg-opacity-25 text-warning fw-bold"
				}
				return "bg-secondary bg-opacity-25 text-secondary"
			}(), openPos, len(acc.Orders), statusBadge, switchBtn, acc.DhanClientID, acc.DhanClientID, acc.DhanClientID))
	}

	sb.WriteString(`
				</tbody>
			</table>
		</div>

		<div class="modal-footer py-2.5 px-4 d-flex justify-content-between"
		     style="border-top: 1px solid rgba(255, 255, 255, 0.06); background: rgba(255, 255, 255, 0.02);">
			<span class="smaller text-secondary font-monospace">Total Accounts Configured: ` + strconv.Itoa(len(accounts)) + `</span>
			<button type="button" class="btn btn-sm btn-outline-secondary px-3" data-bs-dismiss="modal">Close</button>
		</div>
	</div>
	`)

	fmt.Fprint(w, sb.String())
}

// handleAccountModalDetail renders detailed telemetry for an account.
func (h *Handler) handleAccountModalDetail(w http.ResponseWriter, r *http.Request) {
	id := r.URL.Query().Get("id")
	acc, exists := h.engine.GetAccount(id)
	if !exists {
		http.Error(w, "Account not found", http.StatusNotFound)
		return
	}

	activeID := h.engine.GetActiveAccountID()
	isActive := acc.DhanClientID == activeID

	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	fmt.Fprintf(w, `
	<div class="modal-content shadow-2xl rounded-4 overflow-hidden"
	     style="background: #0c0c0e; border: 1px solid rgba(255, 255, 255, 0.08); color: #fafafa;">
		<div class="modal-header py-3 px-4 d-flex justify-content-between align-items-center"
		     style="border-bottom: 1px solid rgba(255, 255, 255, 0.06); background: rgba(255, 255, 255, 0.02);">
			<div class="d-flex align-items-center gap-2.5">
				<div class="rounded-circle bg-info bg-opacity-20 text-info d-flex align-items-center justify-content-center" style="width: 36px; height: 36px;">
					<i class="bi bi-shield-check fs-5"></i>
				</div>
				<div>
					<h5 class="modal-title fs-6 fw-bold mb-0 text-white">%s (%s)</h5>
					<small class="text-secondary font-monospace" style="font-size: 0.72rem;">Client ID: %s &bull; Gateway: %s</small>
				</div>
			</div>
			<button type="button" class="btn-close btn-close-white opacity-50" data-bs-dismiss="modal" aria-label="Close"></button>
		</div>

		<div class="modal-body p-4 d-flex flex-column gap-3">
			<div class="row g-3">
				<div class="col-6 col-md-4">
					<div class="p-3 rounded-3" style="background: #141416; border: 1px solid rgba(255, 255, 255, 0.07);">
						<div class="text-uppercase text-secondary smaller fw-semibold mb-1">Available Cash</div>
						<div class="fs-5 fw-bold text-success font-monospace">₹%.2f</div>
					</div>
				</div>
				<div class="col-6 col-md-4">
					<div class="p-3 rounded-3" style="background: #141416; border: 1px solid rgba(255, 255, 255, 0.07);">
						<div class="text-uppercase text-secondary smaller fw-semibold mb-1">SOD Limit</div>
						<div class="fs-5 fw-bold text-white font-monospace">₹%.2f</div>
					</div>
				</div>
				<div class="col-6 col-md-4">
					<div class="p-3 rounded-3" style="background: #141416; border: 1px solid rgba(255, 255, 255, 0.07);">
						<div class="text-uppercase text-secondary smaller fw-semibold mb-1">Utilized Margin</div>
						<div class="fs-5 fw-bold text-warning font-monospace">₹%.2f</div>
					</div>
				</div>
				<div class="col-6 col-md-4">
					<div class="p-3 rounded-3" style="background: #141416; border: 1px solid rgba(255, 255, 255, 0.07);">
						<div class="text-uppercase text-secondary smaller fw-semibold mb-1">Positions</div>
						<div class="fs-5 fw-bold text-info font-monospace">%d Open</div>
					</div>
				</div>
				<div class="col-6 col-md-4">
					<div class="p-3 rounded-3" style="background: #141416; border: 1px solid rgba(255, 255, 255, 0.07);">
						<div class="text-uppercase text-secondary smaller fw-semibold mb-1">Total Orders</div>
						<div class="fs-5 fw-bold text-white font-monospace">%d Logged</div>
					</div>
				</div>
				<div class="col-6 col-md-4">
					<div class="p-3 rounded-3" style="background: #141416; border: 1px solid rgba(255, 255, 255, 0.07);">
						<div class="text-uppercase text-secondary smaller fw-semibold mb-1">Created At</div>
						<div class="small text-secondary font-monospace mt-1">%s</div>
					</div>
				</div>
			</div>
		</div>

		<div class="modal-footer py-3 px-4 d-flex justify-content-between"
		     style="border-top: 1px solid rgba(255, 255, 255, 0.06); background: rgba(255, 255, 255, 0.02);">
			<button type="button" class="btn btn-sm btn-outline-secondary px-3"
			        hx-get="/mock/accounts/modal/list" hx-target="#globalHtmxModalDialog">
				<i class="bi bi-arrow-left me-1"></i> Back to Accounts
			</button>
			%s
		</div>
	</div>
	`, acc.AccountName, acc.Broker, acc.DhanClientID, acc.Broker,
		acc.AvailableBalance, acc.SodLimit, acc.UtilizedMargin,
		len(acc.Positions), len(acc.Orders), acc.CreatedAt.Format("2006-01-02 15:04"),
		func() string {
			if !isActive {
				return fmt.Sprintf(`<button class="btn btn-sm btn-primary px-3 fw-bold" hx-post="/mock/accounts/select?id=%s" hx-target="#account-switcher-wrapper" hx-swap="outerHTML" onclick="closeGlobalModal()"><i class="bi bi-check2 me-1"></i> Switch to this Account</button>`, acc.DhanClientID)
			}
			return `<span class="badge bg-success bg-opacity-20 text-success border border-success border-opacity-30 px-3 py-2 fw-bold"><i class="bi bi-check-circle-fill me-1"></i> Currently Active</span>`
		}())
}

// handleAccountModalEdit renders the edit form for account name, broker, and funds.
func (h *Handler) handleAccountModalEdit(w http.ResponseWriter, r *http.Request) {
	id := r.URL.Query().Get("id")
	acc, exists := h.engine.GetAccount(id)
	if !exists {
		http.Error(w, "Account not found", http.StatusNotFound)
		return
	}

	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	fmt.Fprintf(w, `
	<div class="modal-content shadow-2xl rounded-4 overflow-hidden"
	     style="background: #0c0c0e; border: 1px solid rgba(255, 255, 255, 0.08); color: #fafafa;">
		<div class="modal-header py-3 px-4 d-flex justify-content-between align-items-center"
		     style="border-bottom: 1px solid rgba(255, 255, 255, 0.06); background: rgba(255, 255, 255, 0.02);">
			<div class="d-flex align-items-center gap-2.5">
				<div class="rounded-circle bg-warning bg-opacity-20 text-warning d-flex align-items-center justify-content-center" style="width: 36px; height: 36px;">
					<i class="bi bi-pencil-square fs-5"></i>
				</div>
				<div>
					<h5 class="modal-title fs-6 fw-bold mb-0 text-white">Edit Account: %s</h5>
					<small class="text-secondary font-monospace" style="font-size: 0.72rem;">Client ID: %s</small>
				</div>
			</div>
			<button type="button" class="btn-close btn-close-white opacity-50" data-bs-dismiss="modal" aria-label="Close"></button>
		</div>

		<form hx-post="/mock/accounts/update" hx-target="#globalHtmxModalDialog">
			<input type="hidden" name="id" value="%s">
			<div class="modal-body p-4 d-flex flex-column gap-3">
				<div>
					<label class="form-label text-secondary small fw-semibold mb-1">Account Display Name</label>
					<input type="text" name="name" class="form-control"
					       style="background: #141416; border: 1px solid rgba(255, 255, 255, 0.09); color: #fafafa;"
					       value="%s" required>
				</div>

				<div>
					<label class="form-label text-secondary small fw-semibold mb-1">Broker Platform Gateway</label>
					<select name="broker" class="form-select"
					        style="background: #141416; border: 1px solid rgba(255, 255, 255, 0.09); color: #fafafa;">
						<option value="Dhan" %s>Dhan (HQ Execution)</option>
						<option value="Fyers" %s>Fyers (Data Feed &amp; API)</option>
						<option value="Zerodha Mock" %s>Zerodha Kite (Mock)</option>
						<option value="Angel One Mock" %s>Angel One SmartAPI (Mock)</option>
					</select>
				</div>

				<div class="p-3 rounded-3" style="background: #141416; border: 1px solid rgba(255, 255, 255, 0.07);">
					<div class="d-flex justify-content-between align-items-center mb-2">
						<span class="text-secondary small fw-semibold">Current Balance:</span>
						<span class="font-monospace text-success fw-bold">₹%.2f</span>
					</div>
					<label class="form-label text-secondary small fw-semibold mb-1">Adjust Virtual Cash (Deposit / Withdraw)</label>
					<div class="input-group">
						<span class="input-group-text" style="background: #18181b; border: 1px solid rgba(255, 255, 255, 0.09); color: #a1a1aa;">₹</span>
						<input type="number" name="adjust_amount" step="10000" class="form-control font-monospace"
						       style="background: #141416; border: 1px solid rgba(255, 255, 255, 0.09); color: #fafafa;"
						       value="0" placeholder="+/- Amount (e.g. 100000 or -50000)">
					</div>
					<small class="text-secondary" style="font-size: 0.7rem;">Enter positive value to deposit, negative value to withdraw.</small>
				</div>
			</div>

			<div class="modal-footer py-3 px-4 d-flex justify-content-between"
			     style="border-top: 1px solid rgba(255, 255, 255, 0.06); background: rgba(255, 255, 255, 0.02);">
				<button type="button" class="btn btn-sm btn-outline-secondary px-3"
				        hx-get="/mock/accounts/modal/list" hx-target="#globalHtmxModalDialog">
					<i class="bi bi-arrow-left me-1"></i> Back
				</button>
				<button type="submit" class="btn btn-sm btn-primary px-4 fw-bold">Save Changes</button>
			</div>
		</form>
	</div>
	`, acc.DhanClientID, acc.DhanClientID, acc.DhanClientID, acc.AccountName,
		func(b string) string {
			if b == "Dhan" {
				return "selected"
			}
			return ""
		}(acc.Broker),
		func(b string) string {
			if b == "Fyers" {
				return "selected"
			}
			return ""
		}(acc.Broker),
		func(b string) string {
			if strings.Contains(b, "Zerodha") {
				return "selected"
			}
			return ""
		}(acc.Broker),
		func(b string) string {
			if strings.Contains(b, "Angel") {
				return "selected"
			}
			return ""
		}(acc.Broker),
		acc.AvailableBalance)
}

// handleAccountUpdate processes edits to an account and triggers dashboard updates.
func (h *Handler) handleAccountUpdate(w http.ResponseWriter, r *http.Request) {
	r.ParseForm()
	id := r.FormValue("id")
	name := r.FormValue("name")
	broker := r.FormValue("broker")
	adjStr := r.FormValue("adjust_amount")
	adj, _ := strconv.ParseFloat(adjStr, 64)

	err := h.engine.UpdateAccount(id, name, broker, adj)
	if err != nil {
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		fmt.Fprintf(w, `<div class="p-4 text-center text-danger">Error: %s</div>`, err.Error())
		return
	}

	toastMsg := fmt.Sprintf("Changes saved for Account %s", id)
	w.Header().Set("HX-Trigger", fmt.Sprintf(`{"accountChanged": true, "closeModal": true, "showToast": {"title": "Account Updated", "message": "%s", "type": "success"}}`, toastMsg))
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	fmt.Fprintf(w, `
	<div class="modal-content shadow-2xl rounded-4 overflow-hidden text-center p-4"
	     style="background: #0c0c0e; border: 1px solid rgba(16, 185, 129, 0.25); color: #fafafa;">
		<i class="bi bi-check-circle-fill text-success fs-1 mb-2 d-block"></i>
		<h5 class="fw-bold text-white mb-1">Account Updated</h5>
		<p class="text-secondary small mb-0">Changes saved for Account <strong class="text-info">%s</strong>.</p>
	</div>
	`, id)
}

// handleAccountModalDeleteConfirm renders a confirmation modal before deleting an account.
func (h *Handler) handleAccountModalDeleteConfirm(w http.ResponseWriter, r *http.Request) {
	id := r.URL.Query().Get("id")
	acc, exists := h.engine.GetAccount(id)
	if !exists {
		http.Error(w, "Account not found", http.StatusNotFound)
		return
	}

	totalAccs := len(h.engine.GetAllAccounts())
	openPos := 0
	for _, p := range acc.Positions {
		if p.NetQty != 0 {
			openPos++
		}
	}

	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	if totalAccs <= 1 {
		fmt.Fprintf(w, `
		<div class="modal-content shadow-2xl rounded-4 overflow-hidden"
		     style="background: #14120d; border: 1px solid rgba(245, 158, 11, 0.25); color: #fafafa;">
			<div class="modal-body p-4 text-center">
				<i class="bi bi-shield-exclamation text-warning fs-1 mb-2 d-block"></i>
				<h5 class="fw-bold text-white mb-2">Cannot Delete Sole Account</h5>
				<p class="text-secondary small mb-4">Account <strong class="text-white">%s</strong> is the only remaining account in the system. The emulator requires at least one active account.</p>
				<button class="btn btn-sm btn-outline-secondary px-4" hx-get="/mock/accounts/modal/list" hx-target="#globalHtmxModalDialog">Back to Accounts</button>
			</div>
		</div>
		`, acc.DhanClientID)
		return
	}

	if openPos > 0 {
		fmt.Fprintf(w, `
		<div class="modal-content shadow-2xl rounded-4 overflow-hidden"
		     style="background: #140d0e; border: 1px solid rgba(239, 68, 68, 0.25); color: #fafafa;">
			<div class="modal-body p-4 text-center">
				<i class="bi bi-slash-circle-fill text-danger fs-1 mb-2 d-block"></i>
				<h5 class="fw-bold text-white mb-2">Active Positions Open</h5>
				<p class="text-secondary small mb-4">Account <strong class="text-white">%s</strong> currently has <strong class="text-warning">%d active position(s)</strong>. You must square off all positions before removing this account.</p>
				<button class="btn btn-sm btn-outline-secondary px-4" hx-get="/mock/accounts/modal/list" hx-target="#globalHtmxModalDialog">Back to Accounts</button>
			</div>
		</div>
		`, acc.DhanClientID, openPos)
		return
	}

	fmt.Fprintf(w, `
	<div class="modal-content shadow-2xl rounded-4 overflow-hidden"
	     style="background: #120a0b; border: 1px solid rgba(239, 68, 68, 0.25); color: #fafafa;">
		<div class="modal-header py-3 px-4 d-flex justify-content-between align-items-center"
		     style="border-bottom: 1px solid rgba(239, 68, 68, 0.15); background: rgba(239, 68, 68, 0.04);">
			<div class="d-flex align-items-center gap-2 text-danger">
				<i class="bi bi-exclamation-octagon-fill fs-5"></i>
				<h5 class="modal-title fs-6 fw-bold mb-0 text-white">Delete Account Confirmation</h5>
			</div>
			<button type="button" class="btn-close btn-close-white opacity-50" data-bs-dismiss="modal" aria-label="Close"></button>
		</div>

		<div class="modal-body p-4">
			<p class="text-white mb-2">Are you sure you want to delete Account <strong class="text-danger font-monospace">%s</strong> (%s)?</p>
			<div class="alert alert-danger bg-danger bg-opacity-10 border border-danger border-opacity-20 text-light smaller mb-0">
				<i class="bi bi-info-circle me-1"></i>
				This will permanently wipe this account's virtual balance (₹%.2f), order logs, and simulated history. This action cannot be undone.
			</div>
		</div>

		<div class="modal-footer py-3 px-4 d-flex justify-content-between"
		     style="border-top: 1px solid rgba(255, 255, 255, 0.06); background: rgba(255, 255, 255, 0.02);">
			<button type="button" class="btn btn-sm btn-outline-secondary px-3"
			        hx-get="/mock/accounts/modal/list" hx-target="#globalHtmxModalDialog">
				Cancel
			</button>
			<button type="button" class="btn btn-sm btn-danger px-4 fw-bold"
			        hx-post="/mock/accounts/delete?id=%s"
			        hx-target="#globalHtmxModalDialog">
				<i class="bi bi-trash-fill me-1"></i> Delete Account
			</button>
		</div>
	</div>
	`, acc.DhanClientID, acc.AccountName, acc.AvailableBalance, acc.DhanClientID)
}

// handleAccountDelete removes an account, auto-switches active account if needed, and notifies UI.
func (h *Handler) handleAccountDelete(w http.ResponseWriter, r *http.Request) {
	id := r.URL.Query().Get("id")
	err := h.engine.DeleteAccount(id)
	if err != nil {
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		fmt.Fprintf(w, `<div class="p-4 text-center text-danger">Error: %s</div>`, err.Error())
		return
	}

	newActive := h.engine.GetActiveAccountID()
	http.SetCookie(w, &http.Cookie{
		Name:     "marmot_mock_client_id",
		Value:    newActive,
		Path:     "/",
		MaxAge:   86400 * 30,
		HttpOnly: false,
	})

	toastMsg := fmt.Sprintf("Account %s removed, active context switched to %s", id, newActive)
	w.Header().Set("HX-Trigger", fmt.Sprintf(`{"accountChanged": true, "closeModal": true, "showToast": {"title": "Account Deleted", "message": "%s", "type": "info"}}`, toastMsg))
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	fmt.Fprintf(w, `
	<div class="modal-content shadow-2xl rounded-4 overflow-hidden text-center p-4"
	     style="background: #0c0c0e; border: 1px solid rgba(16, 185, 129, 0.25); color: #fafafa;">
		<i class="bi bi-check-circle-fill text-success fs-1 mb-2 d-block"></i>
		<h5 class="fw-bold text-white mb-1">Account Deleted</h5>
		<p class="text-secondary small mb-0">Active account switched to <strong class="text-info">%s</strong>.</p>
	</div>
	`, newActive)
}


// handleDashboardSummary renders post-run equity curve and trade session analytics partial.
func (h *Handler) handleDashboardSummary(w http.ResponseWriter, r *http.Request) {
	clientID := h.resolveClientID(r)
	summary := h.engine.GetPerformanceSummary(clientID)

	pnlClass := "text-success"
	pnlBadgeClass := "bg-success bg-opacity-20 text-success border-success"
	pnlSign := "+"
	if summary.NetRealizedPnL < 0 {
		pnlClass = "text-danger"
		pnlBadgeClass = "bg-danger bg-opacity-20 text-danger border-danger"
		pnlSign = ""
	}

	chartLabelsJSON, _ := json.Marshal(func() []string {
		var labels []string
		for _, pt := range summary.EquityCurve {
			labels = append(labels, pt.Timestamp)
		}
		if len(labels) == 0 {
			labels = []string{"Start", "Now"}
		}
		return labels
	}())

	chartDataJSON, _ := json.Marshal(func() []float64 {
		var data []float64
		for _, pt := range summary.EquityCurve {
			data = append(data, pt.Equity)
		}
		if len(data) == 0 {
			data = []float64{summary.InitialCapital, summary.FinalEquity}
		}
		return data
	}())

	var tradeRows strings.Builder
	if len(summary.ClosedPositions) == 0 {
		tradeRows.WriteString(`<tr><td colspan="7" class="text-center text-muted py-4 font-monospace smaller"><i class="bi bi-clock-history me-1 text-warning"></i> No closed trade positions recorded for this session yet. Replay trades will populate in real time.</td></tr>`)
	} else {
		for i, pos := range summary.ClosedPositions {
			pnl := pos.RealizedProfit
			badgeClass := "bg-secondary"
			triggerLabel := "CLOSED"
			if pnl > 0 {
				badgeClass = "bg-success bg-opacity-25 text-success border border-success border-opacity-30"
				triggerLabel = "TP_HIT"
			} else if pnl < 0 {
				badgeClass = "bg-danger bg-opacity-25 text-danger border border-danger border-opacity-30"
				triggerLabel = "SL_HIT"
			}
			trPnlClass := "text-success"
			trPnlSign := "+"
			if pnl < 0 {
				trPnlClass = "text-danger"
				trPnlSign = ""
			}
			sideBadge := `<span class="badge bg-primary bg-opacity-20 text-info border border-info border-opacity-30 font-monospace px-2 py-0.5">BUY</span>`
			qty := pos.BuyQty
			if qty == 0 {
				qty = pos.SellQty
			}
			timeStr := pos.ExitTime
			if timeStr == "" {
				timeStr = pos.EntryTime
			}

			sym := pos.TradingSymbol
			if sym == "" {
				sym = pos.SecurityID
			}
			tradeRows.WriteString(fmt.Sprintf(`
			<tr class="align-middle border-bottom border-white border-opacity-5">
				<td class="font-monospace text-secondary smaller py-2">#%d</td>
				<td class="font-monospace fw-bold text-white py-2">%s</td>
				<td class="py-2">%s</td>
				<td class="font-monospace py-2 text-white-50">₹%.2f &rarr; ₹%.2f <span class="smaller text-muted">(%d Qty)</span></td>
				<td class="font-monospace fw-bold %s py-2">%s₹%.2f</td>
				<td class="py-2"><span class="badge %s px-2 py-0.5 font-monospace smaller">%s</span></td>
				<td class="font-monospace text-secondary smaller py-2">%s</td>
			</tr>`, i+1, sym, sideBadge, pos.BuyAvg, pos.SellAvg, qty, trPnlClass, trPnlSign, pnl, badgeClass, triggerLabel, timeStr))
		}
	}

	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	fmt.Fprintf(w, `
	<div class="card glass-card p-3 mb-3 border-secondary border-opacity-20 shadow-sm" style="background-color: var(--card-background, #0c0c0e) !important;">
		<div class="d-flex align-items-center justify-content-between mb-3 pb-2 border-bottom border-secondary border-opacity-20">
			<div class="d-flex align-items-center gap-2">
				<div class="rounded-circle d-flex align-items-center justify-content-center shadow-sm" style="width: 32px; height: 32px; background: rgba(16, 185, 129, 0.12); color: #10B981; border: 1px solid rgba(16, 185, 129, 0.25);">
					<i class="bi bi-graph-up-arrow"></i>
				</div>
				<div>
					<h6 class="mb-0 fw-bold theme-text-main" style="font-size: 0.95rem;">Session Performance Summary & Equity Curve</h6>
					<span class="text-secondary smaller">Marmot Execution Engine &bull; Account %s</span>
				</div>
			</div>
			<div class="d-flex align-items-center gap-2">
				<span class="badge %s border rounded-pill px-3 py-1 fs-xs fw-bold font-monospace shadow-sm">
					Net PnL: %s₹%.2f (%.2f%%)
				</span>
				<button class="btn btn-dark btn-sm border border-white border-opacity-10 text-white-50 px-2.5 py-1 rounded-pill smaller" 
				        hx-get="/mock/dashboard/summary" hx-target="#session-summary-container" hx-swap="innerHTML" title="Refresh Summary">
					<i class="bi bi-arrow-clockwise"></i>
				</button>
			</div>
		</div>

		<!-- KPI Ribbon -->
		<div class="row g-2 mb-3">
			<div class="col-6 col-md-3 col-lg-2">
				<div class="p-2.5 rounded-3 bg-dark bg-opacity-40 border border-white border-opacity-5">
					<div class="text-secondary smaller text-uppercase fw-semibold font-monospace">Net Realized PnL</div>
					<div class="fs-6 fw-bold %s font-monospace mt-1">%s₹%.2f</div>
				</div>
			</div>
			<div class="col-6 col-md-3 col-lg-2">
				<div class="p-2.5 rounded-3 bg-dark bg-opacity-40 border border-white border-opacity-5">
					<div class="text-secondary smaller text-uppercase fw-semibold font-monospace">Win Rate</div>
					<div class="fs-6 fw-bold text-white font-monospace mt-1">%.1f%% <span class="smaller text-muted fw-normal">(%d/%d)</span></div>
				</div>
			</div>
			<div class="col-6 col-md-3 col-lg-2">
				<div class="p-2.5 rounded-3 bg-dark bg-opacity-40 border border-white border-opacity-5">
					<div class="text-secondary smaller text-uppercase fw-semibold font-monospace">Profit Factor</div>
					<div class="fs-6 fw-bold text-info font-monospace mt-1">%.2f</div>
				</div>
			</div>
			<div class="col-6 col-md-3 col-lg-2">
				<div class="p-2.5 rounded-3 bg-dark bg-opacity-40 border border-white border-opacity-5">
					<div class="text-secondary smaller text-uppercase fw-semibold font-monospace">Max Drawdown</div>
					<div class="fs-6 fw-bold text-danger font-monospace mt-1">₹%.2f <span class="smaller fw-normal">(%.1f%%)</span></div>
				</div>
			</div>
			<div class="col-6 col-md-3 col-lg-2">
				<div class="p-2.5 rounded-3 bg-dark bg-opacity-40 border border-white border-opacity-5">
					<div class="text-secondary smaller text-uppercase fw-semibold font-monospace">Total ROI</div>
					<div class="fs-6 fw-bold %s font-monospace mt-1">%s%.2f%%</div>
				</div>
			</div>
			<div class="col-6 col-md-3 col-lg-2">
				<div class="p-2.5 rounded-3 bg-dark bg-opacity-40 border border-white border-opacity-5">
					<div class="text-secondary smaller text-uppercase fw-semibold font-monospace">Portfolio Balance</div>
					<div class="fs-6 fw-bold text-white font-monospace mt-1">₹%.2f</div>
				</div>
			</div>
		</div>

		<!-- Equity Curve Chart -->
		<div class="p-3 rounded-3 bg-dark bg-opacity-30 border border-white border-opacity-5 mb-3">
			<div class="d-flex align-items-center justify-content-between mb-2">
				<span class="text-secondary smaller fw-bold text-uppercase font-monospace">
					<i class="bi bi-activity me-1 text-info"></i> Interactive Portfolio Equity Trajectory (Mark-to-Market)
				</span>
				<span class="smaller text-muted font-monospace">Initial: ₹%.2f &rarr; Current: ₹%.2f</span>
			</div>
			<div style="position: relative; height: 220px; width: 100%%;">
				<canvas id="sessionEquityChart"></canvas>
			</div>
		</div>

		<!-- Executed Trades Audit Table -->
		<div class="d-flex align-items-center justify-content-between mb-2">
			<span class="text-secondary smaller fw-bold text-uppercase font-monospace">
				<i class="bi bi-list-check me-1 text-warning"></i> Closed Trades & Execution Audit (%d Total)
			</span>
		</div>
		<div class="table-responsive">
			<table class="table table-dark table-hover table-sm align-middle mb-0" style="background: transparent;">
				<thead>
					<tr class="text-secondary border-bottom border-white border-opacity-10 smaller text-uppercase font-monospace">
						<th class="py-2">#</th>
						<th class="py-2">Symbol</th>
						<th class="py-2">Type</th>
						<th class="py-2">Execution Fill</th>
						<th class="py-2">Net Realized PnL</th>
						<th class="py-2">Exit Trigger</th>
						<th class="py-2">Timestamp</th>
					</tr>
				</thead>
				<tbody>
					%s
				</tbody>
			</table>
		</div>
	</div>

	<script>
	(function() {
		const ctx = document.getElementById('sessionEquityChart');
		if (!ctx) return;
		if (window.marmotEquityChartInstance) {
			window.marmotEquityChartInstance.destroy();
		}
		const labels = %s;
		const data = %s;
		const isProfitable = %t;
		const strokeColor = isProfitable ? '#10B981' : '#EF4444';
		const chartCtx = ctx.getContext('2d');
		const gradient = chartCtx.createLinearGradient(0, 0, 0, 220);
		if (isProfitable) {
			gradient.addColorStop(0, 'rgba(16, 185, 129, 0.35)');
			gradient.addColorStop(1, 'rgba(16, 185, 129, 0.00)');
		} else {
			gradient.addColorStop(0, 'rgba(239, 68, 68, 0.35)');
			gradient.addColorStop(1, 'rgba(239, 68, 68, 0.00)');
		}

		window.marmotEquityChartInstance = new Chart(ctx, {
			type: 'line',
			data: {
				labels: labels,
				datasets: [{
					label: 'Portfolio Equity (₹)',
					data: data,
					borderColor: strokeColor,
					borderWidth: 2,
					pointRadius: data.length > 30 ? 0 : 3,
					pointHoverRadius: 5,
					pointBackgroundColor: strokeColor,
					fill: true,
					backgroundColor: gradient,
					tension: 0.2
				}]
			},
			options: {
				responsive: true,
				maintainAspectRatio: false,
				interaction: {
					intersect: false,
					mode: 'index',
				},
				plugins: {
					legend: { display: false },
					tooltip: {
						backgroundColor: 'rgba(12, 12, 14, 0.95)',
						titleColor: '#fafafa',
						bodyColor: '#fafafa',
						borderColor: 'rgba(255, 255, 255, 0.15)',
						borderWidth: 1,
						padding: 10,
						callbacks: {
							label: function(c) {
								return ' Equity: ₹' + c.parsed.y.toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2});
							}
						}
					}
				},
				scales: {
					x: {
						grid: { color: 'rgba(255, 255, 255, 0.04)' },
						ticks: {
							color: 'rgba(255, 255, 255, 0.4)',
							font: { family: 'Google Sans Code, monospace', size: 10 },
							maxTicksLimit: 8
						}
					},
					y: {
						grid: { color: 'rgba(255, 255, 255, 0.04)' },
						ticks: {
							color: 'rgba(255, 255, 255, 0.5)',
							font: { family: 'Google Sans Code, monospace', size: 10 },
							callback: function(v) {
								return '₹' + Number(v).toLocaleString('en-IN');
							}
						}
					}
				}
			}
		});
	})();
	</script>
	`, clientID, pnlBadgeClass, pnlSign, summary.NetRealizedPnL, summary.ROI,
		pnlClass, pnlSign, summary.NetRealizedPnL,
		summary.WinRate, summary.WinningTrades, summary.TotalTrades,
		summary.ProfitFactor,
		summary.MaxDrawdown, summary.MaxDrawdownPct,
		pnlClass, pnlSign, summary.ROI,
		summary.FinalEquity,
		summary.InitialCapital, summary.FinalEquity,
		summary.TotalTrades,
		tradeRows.String(),
		string(chartLabelsJSON), string(chartDataJSON), summary.NetRealizedPnL >= 0)
}

