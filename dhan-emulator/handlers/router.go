package handlers

import (
	"encoding/json"
	"fmt"
	"html/template"
	"net/http"
	"path/filepath"
	"strconv"
	"strings"

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
	funcMap := template.FuncMap{
		"plus": func(a, b float64) float64 { return a + b },
	}
	tmpl, err := template.New(filepath.Base(tmplPath)).Funcs(funcMap).ParseFiles(tmplPath)
	if err != nil {
		return nil, fmt.Errorf("failed to parse dashboard template: %w", err)
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
	// Root index redirect to dashboard
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/" {
			http.Redirect(w, r, "/mock/dashboard", http.StatusFound)
			return
		}
		http.NotFound(w, r)
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
	mux.HandleFunc("/mock/dashboard/streamer-widget", h.handleDashboardStreamerWidget)

	mux.HandleFunc("/mock/api/funds/adjust", h.handleAdjustFunds)
	mux.HandleFunc("/mock/api/chaos", h.handleUpdateChaos)
	mux.HandleFunc("/mock/api/streamer/toggle", h.handleStreamerToggle)
	mux.HandleFunc("/mock/api/streamer/speed", h.handleStreamerSpeed)
	mux.HandleFunc("/mock/api/streamer/select", h.handleStreamerSelect)
	mux.HandleFunc("/mock/api/streamer/files", h.handleStreamerFiles)
	mux.HandleFunc("/mock/api/kill-switch", h.handleKillSwitch)

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

	// Market Option Chain Endpoint (Compatible with Marmot Live HUD & Heatmap)
	mux.HandleFunc("/mock/v2/optionchain", h.handleOptionChain)
	mux.HandleFunc("/v2/optionchain", h.handleOptionChain)
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
	if !h.chaos.AllowRequest() {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusTooManyRequests)
		json.NewEncoder(w).Encode(map[string]interface{}{
			"status":       "error",
			"errorCode":    "DH-429",
			"errorType":    "RateLimitExceeded",
			"errorMessage": "Too many requests. Limit is 20 req/sec.",
		})
		return
	}

	clientID := r.Header.Get("client-id")
	if clientID == "" {
		clientID = "1000000001"
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

// handleDashboard renders the complete HTML sandbox dashboard.
func (h *Handler) handleDashboard(w http.ResponseWriter, r *http.Request) {
	clientID := "1000000001"
	funds := h.engine.GetFundLimit(clientID)
	orders := h.engine.GetAllOrders()
	positions := h.engine.GetPositions(clientID)
	isPlaying, speed, currentFile, ticks := h.streamer.GetStatus()
	curRow, totRows, pct, curDt, curDate := h.streamer.GetProgress()
	files := h.streamer.ListParquetDetails()

	data := struct {
		Funds           models.FundLimitResponse
		Orders          []*models.OrderRecord
		Positions       []models.PositionItem
		ParquetFiles    []streamer.ParquetFileInfo
		CurrentFile     string
		ChaosRPS        int
		ChaosMode       string
		StreamerPlaying bool
		StreamerSpeed   int
		TicksIngested   int64
		CurrentRow      int64
		TotalRows       int64
		ProgressPct     float64
		CurrentDatetime string
		CurrentDate     string
	}{
		Funds:           funds,
		Orders:          orders,
		Positions:       positions,
		ParquetFiles:    files,
		CurrentFile:     currentFile,
		ChaosRPS:        h.chaos.GetRPS(),
		ChaosMode:       string(h.chaos.GetMode()),
		StreamerPlaying: isPlaying,
		StreamerSpeed:   speed,
		TicksIngested:   ticks,
		CurrentRow:      curRow,
		TotalRows:       totRows,
		ProgressPct:     pct,
		CurrentDatetime: curDt,
		CurrentDate:     curDate,
	}

	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	h.tmpl.Execute(w, data)
}

// handleDashboardFunds renders the fund partial for HTMX polling.
func (h *Handler) handleDashboardFunds(w http.ResponseWriter, r *http.Request) {
	funds := h.engine.GetFundLimit("1000000001")
	fmt.Fprintf(w, `<div class="d-flex justify-content-between align-items-baseline mb-1"><span class="fs-4 fw-bold text-success font-monospace">₹%.2f</span><span class="badge bg-success bg-opacity-20 text-success border border-success border-opacity-25 font-monospace">AVAILABLE</span></div><div class="small text-secondary d-flex justify-content-between"><span>SOD Limit: ₹%.2f</span><span>Utilized: ₹%.2f</span></div>`,
		funds.AvailabelBalance, funds.SodLimit, funds.UtilizedAmount)
}

// handleDashboardProgress renders live replay progress bar and calendar date for HTMX polling.
func (h *Handler) handleDashboardProgress(w http.ResponseWriter, r *http.Request) {
	curRow, totRows, pct, curDt, curDate := h.streamer.GetProgress()
	isPlaying, speed, currentFile, ticks := h.streamer.GetStatus()

	statusBadge := `<span class="badge bg-secondary bg-opacity-25 text-white border border-white border-opacity-10 smaller">PAUSED</span>`
	if isPlaying {
		statusBadge = `<span class="badge bg-success bg-opacity-25 text-success border border-success border-opacity-30 smaller font-monospace"><i class="bi bi-circle-fill me-1" style="font-size: 0.5rem;"></i> STREAMING</span>`
	}

	fmt.Fprintf(w, `
	<div class="d-flex flex-column gap-1.5 w-100">
		<div class="d-flex align-items-center justify-content-between flex-wrap gap-2">
			<div class="d-flex align-items-center gap-2">
				%s
				<span class="badge bg-dark border border-white border-opacity-10 text-warning smaller font-monospace">
					<i class="bi bi-calendar3 me-1"></i> %s
				</span>
				<span class="text-white smaller font-monospace"><i class="bi bi-clock me-1 text-info"></i>%s</span>
			</div>
			<div class="d-flex align-items-center gap-2 smaller font-monospace text-secondary">
				<span>Dataset: <strong class="text-info">%s</strong></span>
				<span>|</span>
				<span>Rows: <strong class="text-white">%d / %d</strong></span>
				<span>|</span>
				<span>Progress: <strong class="text-success">%.1f%%</strong></span>
				<span>|</span>
				<span>Speed: <strong class="text-warning">%dx</strong></span>
				<span>|</span>
				<span>Ticks: <strong class="text-white">%d</strong></span>
			</div>
		</div>
		<div class="progress rounded-pill bg-dark border border-white border-opacity-10" style="height: 7px;">
			<div class="progress-bar progress-bar-striped progress-bar-animated bg-success" role="progressbar" style="width: %.2f%%; background-color: var(--brand-lime, #B4F105) !important;" aria-valuenow="%.1f" aria-valuemin="0" aria-valuemax="100"></div>
		</div>
	</div>`, statusBadge, curDate, curDt, currentFile, curRow, totRows, pct, speed, ticks, pct, pct)
}

// handleDashboardStreamerWidget renders real-time streaming data widget (Index Spot + Option Strikes).
func (h *Handler) handleDashboardStreamerWidget(w http.ResponseWriter, r *http.Request) {
	idxTicks, optTicks := h.streamer.GetStreamerWidgetData()

	var sb strings.Builder
	sb.WriteString(`<div class="row g-2">`)

	// Index Spot section
	sb.WriteString(`<div class="col-md-5"><div class="p-2 rounded-3 border border-white border-opacity-10 bg-dark bg-opacity-50"><div class="d-flex align-items-center justify-content-between mb-1 pb-1 border-bottom border-white border-opacity-5"><span class="smaller fw-bold text-uppercase text-secondary">Index Spot Feed</span><span class="badge bg-success bg-opacity-20 text-success smaller">LIVE</span></div>`)
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
	sb.WriteString(fmt.Sprintf(`<div class="col-md-7"><div class="p-2 rounded-3 border border-white border-opacity-10 bg-dark bg-opacity-50"><div class="d-flex align-items-center justify-content-between mb-1 pb-1 border-bottom border-white border-opacity-5"><span class="smaller fw-bold text-uppercase text-secondary">Streaming Option Strikes (CE & PE)</span><span class="badge bg-info bg-opacity-20 text-info smaller font-monospace">%d Strikes</span></div>`, len(optTicks)))
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

	niftyLTP := 24540.00
	if t, ok := ticks["13"]; ok && t.LTP > 0 {
		niftyLTP = t.LTP
	} else if t, ok := ticks["NIFTY"]; ok && t.LTP > 0 {
		niftyLTP = t.LTP
	}

	bankLTP := 51220.00
	if t, ok := ticks["25"]; ok && t.LTP > 0 {
		bankLTP = t.LTP
	} else if t, ok := ticks["BANKNIFTY"]; ok && t.LTP > 0 {
		bankLTP = t.LTP
	}

	fmt.Fprintf(w, `
	<div class="d-flex align-items-center gap-4 text-nowrap">
		<div class="d-flex align-items-baseline gap-2">
			<span class="fw-bold text-light smaller">NIFTY 50</span>
			<span class="font-monospace fw-bold text-success">₹%.2f</span>
			<span class="text-success smaller"><i class="bi bi-caret-up-fill"></i> +0.48%%</span>
		</div>
		<div class="vr bg-secondary opacity-25" style="height: 16px;"></div>
		<div class="d-flex align-items-baseline gap-2">
			<span class="fw-bold text-light smaller">BANK NIFTY</span>
			<span class="font-monospace fw-bold text-success">₹%.2f</span>
			<span class="text-success smaller"><i class="bi bi-caret-up-fill"></i> +0.39%%</span>
		</div>
		<div class="vr bg-secondary opacity-25" style="height: 16px;"></div>
		<div class="d-flex align-items-baseline gap-2">
			<span class="fw-bold text-light smaller">INDIA VIX</span>
			<span class="font-monospace fw-bold text-danger">13.28</span>
			<span class="text-danger smaller"><i class="bi bi-caret-down-fill"></i> -2.15%%</span>
		</div>
		<div class="vr bg-secondary opacity-25" style="height: 16px;"></div>
		<div class="d-flex align-items-baseline gap-2">
			<span class="fw-bold text-light smaller">SENSEX</span>
			<span class="font-monospace fw-bold text-success">80,420.50</span>
			<span class="text-success smaller"><i class="bi bi-caret-up-fill"></i> +0.41%%</span>
		</div>
	</div>`, niftyLTP, bankLTP)
}

// handleDashboardStreamer renders the streamer status partial for HTMX polling.
func (h *Handler) handleDashboardStreamer(w http.ResponseWriter, r *http.Request) {
	h.handleDashboardProgress(w, r)
}

// handleDashboardPositions renders positions partial for HTMX polling.
func (h *Handler) handleDashboardPositions(w http.ResponseWriter, r *http.Request) {
	positions := h.engine.GetPositions("1000000001")
	if len(positions) == 0 {
		fmt.Fprint(w, `<div class="p-4 text-center text-secondary small"><i class="bi bi-inbox fs-3 d-block mb-2 text-muted opacity-50"></i>No active positions. Orders placed by Marmot strategies will appear here in real-time.</div>`)
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
	orders := h.engine.GetAllOrders()
	if len(orders) == 0 {
		fmt.Fprint(w, `<table class="table table-dark table-hover align-middle mb-0"><tbody><tr><td colspan="11" class="text-center text-secondary py-4"><i class="bi bi-receipt fs-3 d-block mb-2 text-muted opacity-50"></i>No mock orders recorded yet. Place an order from Marmot to observe execution lifecycle.</td></tr></tbody></table>`)
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
	amountStr := r.URL.Query().Get("amount")
	amount, _ := strconv.ParseFloat(amountStr, 64)
	h.engine.DepositWithdraw("1000000001", amount)
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
	h.handleDashboardProgress(w, r)
}

// handleStreamerSpeed adjusts tick playback speed.
func (h *Handler) handleStreamerSpeed(w http.ResponseWriter, r *http.Request) {
	valStr := r.URL.Query().Get("val")
	if val, err := strconv.Atoi(valStr); err == nil {
		h.streamer.SetSpeed(val)
	}
	h.handleDashboardProgress(w, r)
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
	h.handleDashboardProgress(w, r)
}

// handleStreamerFiles returns JSON list of available parquet files.
func (h *Handler) handleStreamerFiles(w http.ResponseWriter, r *http.Request) {
	files := h.streamer.ListParquetDetails()
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(files)
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
