package engine

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log"
	"math"
	"math/rand"
	"net/http"
	"regexp"
	"strings"
	"sync"
	"time"

	"github.com/redis/go-redis/v9"
	"dhan-emulator/models"
)

// ClientAccount tracks isolated virtual balance, orders, and positions per dhanClientId.
type ClientAccount struct {
	DhanClientID     string                          `json:"dhanClientId"`
	AccountName      string                          `json:"accountName"`
	Broker           string                          `json:"broker"`
	AvailableBalance float64                         `json:"availableBalance"`
	InitialBalance   float64                         `json:"initialBalance"`
	SodLimit         float64                         `json:"sodLimit"`
	UtilizedMargin   float64                         `json:"utilizedMargin"`
	TotalCharges     float64                         `json:"totalCharges"`
	TotalBrokerage   float64                         `json:"totalBrokerage"`
	CreatedAt        time.Time                       `json:"createdAt"`
	Orders           map[string]*models.OrderRecord  `json:"orders"`
	OrderList        []string                        `json:"orderList"` // ordered IDs
	Positions        map[string]*models.PositionItem `json:"positions"` // key: securityId + "_" + productType
}

// BroadcastHandler defines the function signature for broadcasting raw WebSocket messages.
type BroadcastHandler func(msg []byte)

// MatchingEngine manages the central thread-safe multi-client mock broker state.
type MatchingEngine struct {
	mu                 sync.RWMutex
	SessionID          string
	accounts           map[string]*ClientAccount
	accountList        []string
	activeAccountID    string
	ltpMap             map[string]float64
	chaos              *ChaosManager
	postbackURL        string
	httpClient         *http.Client
	orderCounter       int64
	broadcaster        BroadcastHandler
	lastStatsBroadcast time.Time
	rdb                *redis.Client
	virtualTime        time.Time
}

func (m *MatchingEngine) now() time.Time {
	if !m.virtualTime.IsZero() {
		return m.virtualTime
	}
	return time.Now()
}

// NewMatchingEngine initializes the MatchingEngine with seeded default accounts.
func NewMatchingEngine(chaos *ChaosManager, postbackURL string, rdb *redis.Client) *MatchingEngine {
	if postbackURL == "" {
		postbackURL = "http://web:8000/postback/dhan/postback/"
	}
	now := time.Now()
	engine := &MatchingEngine{
		SessionID:       fmt.Sprintf("sess_%d", now.UnixNano()),
		accounts:        make(map[string]*ClientAccount),
		accountList:     make([]string, 0),
		activeAccountID: "1000000001",
		ltpMap:          make(map[string]float64),
		chaos:           chaos,
		postbackURL:     postbackURL,
		httpClient:      &http.Client{Timeout: 5 * time.Second},
		rdb:             rdb,
	}

	// Seed Primary Account (Dhan) - Default ₹1,00,000
	acc1 := &ClientAccount{
		DhanClientID:     "1000000001",
		AccountName:      "Primary Algorithmic Trading",
		Broker:           "Dhan",
		AvailableBalance: 100000.0,
		InitialBalance:   100000.0,
		SodLimit:         100000.0,
		UtilizedMargin:   0.0,
		CreatedAt:        now,
		Orders:           make(map[string]*models.OrderRecord),
		OrderList:        make([]string, 0),
		Positions:        make(map[string]*models.PositionItem),
	}
	// Seed Secondary Account (Fyers)
	acc2 := &ClientAccount{
		DhanClientID:     "1000000002",
		AccountName:      "Scalp Strategy Alpha",
		Broker:           "Fyers",
		AvailableBalance: 100000.0,
		InitialBalance:   100000.0,
		SodLimit:         100000.0,
		UtilizedMargin:   0.0,
		CreatedAt:        now,
		Orders:           make(map[string]*models.OrderRecord),
		OrderList:        make([]string, 0),
		Positions:        make(map[string]*models.PositionItem),
	}

	engine.accounts["1000000001"] = acc1
	engine.accounts["1000000002"] = acc2
	engine.accountList = append(engine.accountList, "1000000001", "1000000002")

	return engine
}

// getOrCreateAccountLocked returns the ClientAccount, initializing with default 5,00,000 if new.
func (m *MatchingEngine) getOrCreateAccountLocked(clientID string) *ClientAccount {
	if clientID == "" {
		clientID = m.activeAccountID
		if clientID == "" {
			clientID = "1000000001"
		}
	}
	acc, exists := m.accounts[clientID]
	if !exists {
		acc = &ClientAccount{
			DhanClientID:     clientID,
			AccountName:      fmt.Sprintf("Account %s", clientID),
			Broker:           "Dhan",
			AvailableBalance: 500000.0,
			SodLimit:         500000.0,
			UtilizedMargin:   0.0,
			CreatedAt:        m.now(),
			Orders:           make(map[string]*models.OrderRecord),
			OrderList:        make([]string, 0),
			Positions:        make(map[string]*models.PositionItem),
		}
		m.accounts[clientID] = acc
		m.accountList = append(m.accountList, clientID)
	}
	return acc
}


// SetBroadcaster attaches an external broadcast callback (e.g. from ParquetStreamer).
func (m *MatchingEngine) SetBroadcaster(fn BroadcastHandler) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.broadcaster = fn
}


// GetAccountStats computes live aggregated metrics for the specified client.
func (m *MatchingEngine) GetAccountStats(clientID string) models.BrokerStatsPayload {
	m.mu.RLock()
	defer m.mu.RUnlock()

	acc, ok := m.accounts[clientID]
	if !ok {
		return models.BrokerStatsPayload{
			Type:             "broker_stats",
			DhanClientID:     clientID,
			AvailableBalance: 500000.0,
		}
	}

	var realizedTotal, unrealizedTotal float64
	openCount, closedCount := 0, 0
	for _, pos := range acc.Positions {
		realizedTotal += pos.RealizedProfit
		unrealizedTotal += pos.UnrealizedProfit
		if pos.NetQty != 0 {
			openCount++
		} else {
			closedCount++
		}
	}

	totalOrders := len(acc.OrderList)
	tradedCount, pendingCount := 0, 0
	for _, ord := range acc.Orders {
		if ord.Status == "TRADED" {
			tradedCount++
		} else if ord.Status == "PENDING" {
			pendingCount++
		}
	}

	avail := acc.AvailableBalance
	netPnl := math.Round((realizedTotal + unrealizedTotal - acc.TotalCharges)*100) / 100
	netRealized := math.Round((realizedTotal - acc.TotalCharges)*100) / 100
	return models.BrokerStatsPayload{
		Type:                 "broker_stats",
		DhanClientID:         clientID,
		AvailableBalance:     avail,
		AvailableMargin:      avail,
		UtilizedMargin:       acc.UtilizedMargin,
		RealizedProfit:       realizedTotal,
		RealizedPnL:          netRealized,
		TotalCharges:         acc.TotalCharges,
		TotalBrokerage:       acc.TotalBrokerage,
		NetRealizedPnL:       netRealized,
		UnrealizedProfit:     unrealizedTotal,
		LiveNetPnL:           netPnl,
		NetPnL:               netPnl,
		OpenPositionsCount:   openCount,
		OpenPositions:        openCount,
		ClosedPositionsCount: closedCount,
		TotalOrdersCount:     totalOrders,
		TotalOrders:          totalOrders,
		TradedOrdersCount:    tradedCount,
		PendingOrdersCount:   pendingCount,
	}
}


// BroadcastAccountStats pushes updated stats over WebSocket.
func (m *MatchingEngine) BroadcastAccountStats(clientID string) {
	stats := m.GetAccountStats(clientID)
	bytes, err := json.Marshal(stats)
	if err != nil {
		return
	}

	m.mu.RLock()
	fn := m.broadcaster
	m.mu.RUnlock()

	if fn != nil {
		fn(bytes)
	}
}


// BroadcastOrderEvent pushes an order update event over WebSocket.
func (m *MatchingEngine) BroadcastOrderEvent(clientID string, ord *models.OrderRecord) {
	sym := ord.Order.TradingSymbol
	if sym == "" {
		sym = ord.Order.CorrelationID
	}
	evt := models.BrokerOrderEvent{
		Type:            "broker_order_event",
		DhanClientID:    clientID,
		OrderID:         ord.OrderID,
		Status:          ord.Status,
		TradingSymbol:   sym,
		TransactionType: ord.Order.TransactionType,
		Price:           ord.FilledPrice,
		Quantity:        ord.FilledQty,
		Event:           ord.RejectMsg,
		LegName:         ord.Order.LegName,
	}
	bytes, err := json.Marshal(evt)
	if err != nil {
		return
	}

	m.mu.RLock()
	fn := m.broadcaster
	m.mu.RUnlock()

	if fn != nil {
		fn(bytes)
	}
}

// parseOptionKey extracts underlying index, strike number and option type from arbitrary option symbols or IDs.
func parseOptionKey(s string) (underlying string, strike string, optType string) {
	upper := strings.ToUpper(strings.TrimSpace(s))
	if upper == "" {
		return "", "", ""
	}

	if strings.Contains(upper, "BANKNIFTY") {
		underlying = "BANKNIFTY"
	} else if strings.Contains(upper, "FINNIFTY") {
		underlying = "FINNIFTY"
	} else if strings.Contains(upper, "MIDCPNIFTY") {
		underlying = "MIDCPNIFTY"
	} else if strings.Contains(upper, "NIFTY") {
		underlying = "NIFTY"
	} else if strings.Contains(upper, "SENSEX") {
		underlying = "SENSEX"
	}

	if strings.HasSuffix(upper, "PE") || strings.Contains(upper, "_PE") || strings.Contains(upper, " PE") || strings.Contains(upper, "-PE") || strings.Contains(upper, ":PE") || strings.Contains(upper, "PUT") {
		optType = "PE"
	} else if strings.HasSuffix(upper, "CE") || strings.Contains(upper, "_CE") || strings.Contains(upper, " CE") || strings.Contains(upper, "-CE") || strings.Contains(upper, ":CE") || strings.Contains(upper, "CALL") {
		optType = "CE"
	}

	if optType != "" {
		re := regexp.MustCompile(`(\d{4,5})\s*(?:-|_)?(?:CE|PE|CALL|PUT)`)
		if m := re.FindStringSubmatch(upper); len(m) > 1 {
			strike = m[1]
			return underlying, strike, optType
		}
	}

	var digits []rune
	for _, r := range upper {
		if r >= '0' && r <= '9' {
			digits = append(digits, r)
		} else {
			if len(digits) >= 4 && len(digits) <= 5 {
				break
			}
			digits = digits[:0]
		}
	}
	if len(digits) >= 4 {
		strike = string(digits)
	}
	return underlying, strike, optType
}

// isContractMatch checks if two symbols represent the same underlying option contract or spot instrument.
func isContractMatch(id1, sym1, id2, sym2 string) bool {
	if id1 != "" && (id1 == id2 || id1 == sym2) {
		return true
	}
	if sym1 != "" && (sym1 == id2 || sym1 == sym2) {
		return true
	}

	clean := func(s string) string {
		return strings.ToUpper(strings.ReplaceAll(strings.ReplaceAll(strings.ReplaceAll(strings.ReplaceAll(s, " ", ""), ":", ""), "-", ""), "_", ""))
	}
	cId1, cSym1 := clean(id1), clean(sym1)
	cId2, cSym2 := clean(id2), clean(sym2)
	if cId1 != "" && (cId1 == cId2 || cId1 == cSym2) {
		return true
	}
	if cSym1 != "" && (cSym1 == cId2 || cSym1 == cSym2) {
		return true
	}

	s1 := sym1
	if s1 == "" {
		s1 = id1
	}
	s2 := sym2
	if s2 == "" {
		s2 = id2
	}
	u1, st1, t1 := parseOptionKey(s1)
	u2, st2, t2 := parseOptionKey(s2)

	if st1 == "" || t1 == "" {
		if uId, stId, tId := parseOptionKey(id1); stId != "" || tId != "" {
			if u1 == "" {
				u1 = uId
			}
			if st1 == "" {
				st1 = stId
			}
			if t1 == "" {
				t1 = tId
			}
		}
	}
	if st2 == "" || t2 == "" {
		if uId, stId, tId := parseOptionKey(id2); stId != "" || tId != "" {
			if u2 == "" {
				u2 = uId
			}
			if st2 == "" {
				st2 = stId
			}
			if t2 == "" {
				t2 = tId
			}
		}
	}

	if t1 != "" && t2 != "" {
		if t1 == t2 && st1 != "" && st1 == st2 {
			if u1 == "" || u2 == "" || u1 == u2 {
				return true
			}
		}
		return false
	}

	if t1 == "" && t2 == "" && u1 != "" && u1 == u2 {
		return true
	}

	return false
}

// IngestTick updates internal LTP for symbols and recalculates MTM for all active accounts.
func (m *MatchingEngine) IngestTick(tick models.MarketTick) {
	m.mu.Lock()
	defer m.mu.Unlock()

	if !tick.Timestamp.IsZero() {
		m.virtualTime = tick.Timestamp
	}

	if tick.SecurityID == "" || tick.LTP <= 0 {
		return
	}
	m.ltpMap[tick.SecurityID] = tick.LTP
	if tick.TradingSymbol != "" {
		m.ltpMap[tick.TradingSymbol] = tick.LTP
	}

	// Recalculate Unrealized PnL and MTM across open positions
	hasOpenPos := false
	for _, acc := range m.accounts {
		for _, pos := range acc.Positions {
			if isContractMatch(pos.SecurityID, pos.TradingSymbol, tick.SecurityID, tick.TradingSymbol) && pos.NetQty != 0 {
				hasOpenPos = true
				if pos.NetQty > 0 {
					pos.UnrealizedProfit = (tick.LTP - pos.BuyAvg) * float64(pos.NetQty)
				} else {
					pos.UnrealizedProfit = (pos.SellAvg - tick.LTP) * float64(-pos.NetQty)
				}
			}
		}
	}

	if hasOpenPos && time.Since(m.lastStatsBroadcast) > 250*time.Millisecond {
		m.lastStatsBroadcast = time.Now()
		go m.BroadcastAccountStats(m.activeAccountID)
	}

	// Autonomous SL/TP Check on pending orders
	for _, acc := range m.accounts {
		for _, ord := range acc.Orders {
			if ord.Status == "PENDING" && isContractMatch(ord.Order.SecurityID, ord.Order.TradingSymbol, tick.SecurityID, tick.TradingSymbol) {
				isTriggered := false
				if ord.Order.OrderType == "STOP_LOSS" || ord.Order.OrderType == "STOP_LOSS_MARKET" {
					if ord.Order.TransactionType == "BUY" && tick.LTP >= ord.Order.TriggerPrice {
						isTriggered = true
					} else if ord.Order.TransactionType == "SELL" && tick.LTP <= ord.Order.TriggerPrice {
						isTriggered = true
					}
				}
				if isTriggered {
					// Pre-mark as TRADED inside the lock to prevent double-trigger on subsequent ticks
					ord.Status = "TRADED"
					go m.executeOrderAsync(acc.DhanClientID, ord.OrderID, tick.LTP)
				}
			}
		}
	}

	// Autonomous SL/TP Check on open positions with intra-candle Low/High precision
	for _, acc := range m.accounts {
		for _, pos := range acc.Positions {
			if isContractMatch(pos.SecurityID, pos.TradingSymbol, tick.SecurityID, tick.TradingSymbol) && pos.NetQty != 0 && pos.PositionType != "CLOSED" {
				lowPrice := tick.Low
				if lowPrice <= 0 {
					lowPrice = tick.LTP
				}
				highPrice := tick.High
				if highPrice <= 0 {
					highPrice = tick.LTP
				}

				if pos.NetQty > 0 {
					// LONG position
					if pos.StopLoss > 0 && lowPrice <= pos.StopLoss {
						fillPx := pos.StopLoss
						if tick.Open < pos.StopLoss && tick.Open > 0 {
							fillPx = tick.Open // Gap down fill
						}
						m.squareOffPositionAutoLocked(acc, pos, "SL_HIT", fillPx)
					} else if pos.TakeProfit > 0 && highPrice >= pos.TakeProfit {
						fillPx := pos.TakeProfit
						if tick.Open > pos.TakeProfit {
							fillPx = tick.Open // Gap up fill
						}
						m.squareOffPositionAutoLocked(acc, pos, "TP_HIT", fillPx)
					}
				} else if pos.NetQty < 0 {
					// SHORT position
					if pos.StopLoss > 0 && highPrice >= pos.StopLoss {
						fillPx := pos.StopLoss
						if tick.Open > pos.StopLoss {
							fillPx = tick.Open // Gap up fill
						}
						m.squareOffPositionAutoLocked(acc, pos, "SL_HIT", fillPx)
					} else if pos.TakeProfit > 0 && lowPrice <= pos.TakeProfit {
						fillPx := pos.TakeProfit
						if tick.Open < pos.TakeProfit && tick.Open > 0 {
							fillPx = tick.Open // Gap down fill
						}
						m.squareOffPositionAutoLocked(acc, pos, "TP_HIT", fillPx)
					}
				}
			}
		}
	}
}

// CalculateOptionBuyingCharges computes standard Indian statutory and broker charges for option trades.
func CalculateOptionBuyingCharges(buyPrice, sellPrice float64, qty int) (totalCharges, brokerage, stt, exchangeCharges, sebiCharges, stampDuty, gst float64) {
	buyTurnover := buyPrice * float64(qty)
	sellTurnover := sellPrice * float64(qty)
	totalTurnover := buyTurnover + sellTurnover

	brokerageBuy := math.Min(20.0, buyTurnover*0.0005)
	if buyTurnover <= 0 {
		brokerageBuy = 0
	}
	brokerageSell := math.Min(20.0, sellTurnover*0.0005)
	if sellTurnover <= 0 {
		brokerageSell = 0
	}
	brokerage = math.Round((brokerageBuy+brokerageSell)*100) / 100

	stt = math.Round(sellTurnover*0.001*100) / 100
	exchangeCharges = math.Round(totalTurnover*0.0005*100) / 100
	sebiCharges = math.Round(totalTurnover*0.000001*100) / 100
	stampDuty = math.Round(buyTurnover*0.00003*100) / 100
	gst = math.Round((brokerage+exchangeCharges+sebiCharges)*0.18*100) / 100

	totalCharges = math.Round((brokerage+stt+exchangeCharges+sebiCharges+stampDuty+gst)*100) / 100
	return
}

// PlaceOrder validates and creates a new order in PENDING status, then launches async execution.
func (m *MatchingEngine) PlaceOrder(req models.OrderRequest) (*models.OrderResponse, error) {
	m.mu.Lock()
	m.orderCounter++
	now := m.now()
	orderID := fmt.Sprintf("DHN%d%04d", now.Unix(), rand.Intn(10000))
	exchangeID := fmt.Sprintf("NSE%d%04d", now.Unix(), rand.Intn(10000))

	sl := req.BoStopLossValue
	if sl <= 0 && req.TriggerPrice > 0 {
		sl = req.TriggerPrice
	}
	tp := req.BoProfitValue

	acc := m.getOrCreateAccountLocked(req.DhanClientID)
	rec := &models.OrderRecord{
		Order:       req,
		OrderID:     orderID,
		ExchangeID:  exchangeID,
		Status:      "PENDING",
		FilledQty:   0,
		FilledPrice: 0.0,
		StopLoss:    sl,
		TakeProfit:  tp,
		CreatedAt:   now,
		UpdatedAt:   now,
	}

	acc.Orders[orderID] = rec
	acc.OrderList = append([]string{orderID}, acc.OrderList...)
	m.mu.Unlock()

	m.BroadcastAccountStats(req.DhanClientID)
	m.BroadcastOrderEvent(req.DhanClientID, rec)

	// Launch async execution simulating 35ms - 50ms realistic broker latency
	go m.processAsyncLifecycle(req.DhanClientID, orderID)

	return &models.OrderResponse{
		OrderID:        orderID,
		OrderStatus:    "PENDING",
		OrderTimestamp: now.Format("2006-01-02 15:04:05"),
	}, nil
}

// processAsyncLifecycle runs in background to simulate broker execution latency & webhook dispatch.
func (m *MatchingEngine) processAsyncLifecycle(clientID, orderID string) {
	// Synthetic exchange latency: 35ms to 50ms jitter
	latencyMs := 35 + rand.Intn(16)
	time.Sleep(time.Duration(latencyMs) * time.Millisecond)

	m.mu.Lock()
	acc, ok := m.accounts[clientID]
	if !ok {
		m.mu.Unlock()
		return
	}
	ord, ok := acc.Orders[orderID]
	if !ok || ord.Status != "PENDING" {
		m.mu.Unlock()
		return
	}

	// 1. Check Synthetic Errors
	isChaosError, reason := m.chaos.CheckSyntheticError(ord.Order.CorrelationID, ord.Order.Price)
	if isChaosError {
		ord.Status = "REJECTED"
		ord.RejectMsg = reason
		ord.UpdatedAt = m.now()
		webhook := m.buildPostbackWebhookLocked(ord)
		m.mu.Unlock()
		m.dispatchWebhook(webhook)
		m.BroadcastAccountStats(clientID)
		m.BroadcastOrderEvent(clientID, ord)
		return
	}

	// 2. Spot Index Guardrail: Under SEBI / NSE exchange regulations, underlying spot indices cannot be traded directly.
	cleanSym := strings.ToUpper(strings.TrimSpace(ord.Order.TradingSymbol))
	cleanSec := strings.ToUpper(strings.TrimSpace(ord.Order.SecurityID))
	isPureSpot := false
	for _, spotName := range []string{"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX", "NIFTY 50", "NIFTY50", "NIFTY BANK"} {
		if cleanSym == spotName || cleanSec == spotName {
			isPureSpot = true
			break
		}
	}
	if isPureSpot {
		ord.Status = "REJECTED"
		ord.RejectMsg = fmt.Sprintf("EXCHANGE_ERROR: %s is an underlying spot index and cannot be traded directly. Trade Index Options or Futures.", cleanSym)
		ord.UpdatedAt = m.now()
		webhook := m.buildPostbackWebhookLocked(ord)
		m.mu.Unlock()
		m.dispatchWebhook(webhook)
		m.BroadcastAccountStats(clientID)
		m.BroadcastOrderEvent(clientID, ord)
		return
	}

	// 3. Resolve Fill Price from real-time or historical market tick
	fillPrice := ord.Order.Price
	if fillPrice <= 0 {
		if ltp, hasLtp := m.ltpMap[ord.Order.SecurityID]; hasLtp && ltp > 0 {
			fillPrice = ltp
		} else if ltp, hasLtp := m.ltpMap[ord.Order.TradingSymbol]; hasLtp && ltp > 0 {
			fillPrice = ltp
		} else {
			// Search ltpMap for matching contract key
			for k, v := range m.ltpMap {
				if isContractMatch(ord.Order.SecurityID, ord.Order.TradingSymbol, k, k) && v > 0 {
					fillPrice = v
					break
				}
			}
		}
	}

	if fillPrice <= 0 {
		ord.Status = "REJECTED"
		ord.RejectMsg = fmt.Sprintf("MARKET_DATA_UNAVAILABLE: No valid quote found for %s", ord.Order.TradingSymbol)
		ord.UpdatedAt = m.now()
		webhook := m.buildPostbackWebhookLocked(ord)
		m.mu.Unlock()
		m.dispatchWebhook(webhook)
		m.BroadcastAccountStats(clientID)
		m.BroadcastOrderEvent(clientID, ord)
		return
	}

	// 3. Margin & Funds Verification
	requiredMargin := float64(ord.Order.Quantity) * fillPrice
	if ord.Order.TransactionType == "BUY" && acc.AvailableBalance < requiredMargin {
		ord.Status = "REJECTED"
		ord.RejectMsg = fmt.Sprintf("MARGIN_INSUFFICIENT: Required %.2f, Available %.2f", requiredMargin, acc.AvailableBalance)
		ord.UpdatedAt = m.now()
		webhook := m.buildPostbackWebhookLocked(ord)
		m.mu.Unlock()
		m.dispatchWebhook(webhook)
		m.BroadcastAccountStats(clientID)
		m.BroadcastOrderEvent(clientID, ord)
		return
	}

	// If it's a pending trigger order (SL), keep in PENDING status until IngestTick triggers it
	if ord.Order.OrderType == "STOP_LOSS" || ord.Order.OrderType == "STOP_LOSS_MARKET" {
		m.mu.Unlock()
		return
	}

	// 4. Fill Order & Update Balance/Positions
	ord.Status = "TRADED"
	ord.FilledQty = ord.Order.Quantity
	ord.FilledPrice = fillPrice
	ord.UpdatedAt = m.now()
	ord.EntryTime = ord.CreatedAt
	ord.StopLoss = ord.Order.BoStopLossValue
	if ord.StopLoss == 0 {
		ord.StopLoss = ord.Order.TriggerPrice
	}
	ord.TakeProfit = ord.Order.BoProfitValue

	// OMS Guardrail: If an Option contract received an index-level SL (e.g. SL >= fillPrice or SL > 2000), normalize to option premium risk
	if (ord.Order.ExchangeSegment == "NSE_FNO" || strings.HasSuffix(strings.ToUpper(ord.Order.TradingSymbol), "CE") || strings.HasSuffix(strings.ToUpper(ord.Order.TradingSymbol), "PE") || fillPrice < 2000) && fillPrice > 0 {
		if ord.StopLoss >= fillPrice || ord.StopLoss > 2000 {
			ord.StopLoss = math.Max(0.5, math.Round(fillPrice*0.80*100)/100)
		}
		if ord.TakeProfit <= fillPrice || ord.TakeProfit > 2000 {
			ord.TakeProfit = math.Round(fillPrice*1.40*100)/100
		}
	}

	posKey := ord.Order.SecurityID + "_" + ord.Order.ProductType
	sym := ord.Order.TradingSymbol
	if sym == "" {
		sym = ord.Order.SecurityID
	}
	pos, exists := acc.Positions[posKey]
	if !exists {
		pos = &models.PositionItem{
			DhanClientID:    clientID,
			TradingSymbol:   sym,
			SecurityID:      ord.Order.SecurityID,
			PositionType:    "CLOSED",
			ExchangeSegment: ord.Order.ExchangeSegment,
			ProductType:     ord.Order.ProductType,
			Multiplier:      1,
			EntryTime:       m.now().Format("15:04:05"),
			StopLoss:        ord.StopLoss,
			TakeProfit:      ord.TakeProfit,
		}
		acc.Positions[posKey] = pos
	} else {
		if ord.StopLoss > 0 {
			pos.StopLoss = ord.StopLoss
		}
		if ord.TakeProfit > 0 {
			pos.TakeProfit = ord.TakeProfit
		}
	}

	if ord.Order.TransactionType == "BUY" {
		acc.AvailableBalance -= requiredMargin
		acc.UtilizedMargin += requiredMargin
		totalBuyValue := (pos.BuyAvg * float64(pos.BuyQty)) + (fillPrice * float64(ord.Order.Quantity))
		pos.BuyQty += ord.Order.Quantity
		pos.BuyAvg = totalBuyValue / float64(pos.BuyQty)
		pos.NetQty = pos.BuyQty - pos.SellQty
		if pos.EntryTime == "" {
			pos.EntryTime = m.now().Format("15:04:05")
		}
	} else {
		// SELL
		acc.AvailableBalance += requiredMargin
		if acc.UtilizedMargin >= requiredMargin {
			acc.UtilizedMargin -= requiredMargin
		}
		totalSellValue := (pos.SellAvg * float64(pos.SellQty)) + (fillPrice * float64(ord.Order.Quantity))
		pos.SellQty += ord.Order.Quantity
		pos.SellAvg = totalSellValue / float64(pos.SellQty)
		pos.NetQty = pos.BuyQty - pos.SellQty
		// Realized profit calculation with Indian statutory charges
		if pos.BuyQty > 0 {
			pnl := (fillPrice - pos.BuyAvg) * float64(ord.Order.Quantity)
			pos.RealizedProfit += pnl
			totalChg, brk, stt, _, _, _, _ := CalculateOptionBuyingCharges(pos.BuyAvg, fillPrice, ord.Order.Quantity)
			pos.TotalCharges += totalChg
			pos.Brokerage += brk
			pos.STT += stt
			pos.NetProfit = pos.RealizedProfit - pos.TotalCharges
			acc.TotalCharges += totalChg
			acc.TotalBrokerage += brk
			acc.AvailableBalance -= totalChg
		}
	}

	if pos.NetQty > 0 {
		pos.PositionType = "LONG"
	} else if pos.NetQty < 0 {
		pos.PositionType = "SHORT"
	} else {
		pos.PositionType = "CLOSED"
		pos.ExitTime = m.now().Format("15:04:05")
		ord.ExitTime = m.now()
	}

	webhook := m.buildPostbackWebhookLocked(ord)
	m.mu.Unlock()

	m.dispatchWebhook(webhook)
	m.BroadcastAccountStats(clientID)
	m.BroadcastOrderEvent(clientID, ord)
}

// executeOrderAsync triggers fill on pending Stop-Loss or Limit orders when tick crosses trigger.
func (m *MatchingEngine) executeOrderAsync(clientID, orderID string, fillPrice float64) {
	m.mu.Lock()
	acc, ok := m.accounts[clientID]
	if !ok {
		m.mu.Unlock()
		return
	}
	ord, ok := acc.Orders[orderID]
	if !ok || ord.FilledQty > 0 {
		// Already processed (pre-marked by IngestTick or already filled)
		m.mu.Unlock()
		return
	}

	ord.Status = "TRADED"
	ord.FilledQty = ord.Order.Quantity
	ord.FilledPrice = fillPrice
	ord.UpdatedAt = m.now()

	posKey := ord.Order.SecurityID + "_" + ord.Order.ProductType
	pos, exists := acc.Positions[posKey]
	if !exists {
		pos = &models.PositionItem{
			DhanClientID:    clientID,
			TradingSymbol:   ord.Order.CorrelationID,
			SecurityID:      ord.Order.SecurityID,
			PositionType:    "CLOSED",
			ExchangeSegment: ord.Order.ExchangeSegment,
			ProductType:     ord.Order.ProductType,
			Multiplier:      1,
		}
		acc.Positions[posKey] = pos
	}

	requiredMargin := float64(ord.Order.Quantity) * fillPrice
	if ord.Order.TransactionType == "BUY" {
		acc.AvailableBalance -= requiredMargin
		acc.UtilizedMargin += requiredMargin
		totalBuyValue := (pos.BuyAvg * float64(pos.BuyQty)) + (fillPrice * float64(ord.Order.Quantity))
		pos.BuyQty += ord.Order.Quantity
		pos.BuyAvg = totalBuyValue / float64(pos.BuyQty)
		pos.NetQty = pos.BuyQty - pos.SellQty
		if pos.EntryTime == "" {
			pos.EntryTime = m.now().Format("15:04:05")
		}
	} else {
		// SELL
		totalSellValue := (pos.SellAvg * float64(pos.SellQty)) + (fillPrice * float64(ord.Order.Quantity))
		pos.SellQty += ord.Order.Quantity
		pos.SellAvg = totalSellValue / float64(pos.SellQty)
		pos.NetQty = pos.BuyQty - pos.SellQty
		if pos.BuyQty > 0 {
			qty := ord.Order.Quantity
			pnl := (fillPrice - pos.BuyAvg) * float64(qty)
			pos.RealizedProfit += pnl
			totalChg, brk, stt, _, _, _, _ := CalculateOptionBuyingCharges(pos.BuyAvg, fillPrice, qty)
			pos.TotalCharges += totalChg
			pos.Brokerage += brk
			pos.STT += stt
			pos.NetProfit = pos.RealizedProfit - pos.TotalCharges
			acc.TotalCharges += totalChg
			acc.TotalBrokerage += brk
			releasedMargin := pos.BuyAvg * float64(qty)
			acc.AvailableBalance += releasedMargin + pnl - totalChg
			if acc.UtilizedMargin >= releasedMargin {
				acc.UtilizedMargin -= releasedMargin
			}
		} else {
			acc.AvailableBalance += requiredMargin
			if acc.UtilizedMargin >= requiredMargin {
				acc.UtilizedMargin -= requiredMargin
			}
		}
	}

	if pos.NetQty > 0 {
		pos.PositionType = "LONG"
	} else if pos.NetQty < 0 {
		pos.PositionType = "SHORT"
	} else {
		pos.PositionType = "CLOSED"
		pos.ExitTime = m.now().Format("15:04:05")
		ord.ExitTime = m.now()
		pos.UnrealizedProfit = 0.0
	}

	webhook := m.buildPostbackWebhookLocked(ord)
	m.mu.Unlock()

	m.dispatchWebhook(webhook)
	m.BroadcastAccountStats(clientID)
	m.BroadcastOrderEvent(clientID, ord)
}

// squareOffPositionAutoLocked closes an open position triggered by Stop-Loss or Take-Profit.
func (m *MatchingEngine) squareOffPositionAutoLocked(acc *ClientAccount, pos *models.PositionItem, triggerReason string, fillPrice float64) {
	if pos.NetQty == 0 || pos.PositionType == "CLOSED" {
		return
	}

	m.orderCounter++
	now := m.now()
	nowStr := now.Format("2006-01-02 15:04:05")
	orderID := fmt.Sprintf("DHN%d%04d", now.Unix(), rand.Intn(10000))
	exchangeID := fmt.Sprintf("NSE%d%04d", now.Unix(), rand.Intn(10000))

	var exitSide string
	qty := pos.NetQty
	if qty > 0 {
		// Long position -> Exit via SELL
		exitSide = "SELL"
		pnl := (fillPrice - pos.BuyAvg) * float64(qty)
		pos.RealizedProfit += pnl
		pos.SellQty += qty
		pos.SellAvg = fillPrice
		totalChg, brk, stt, _, _, _, _ := CalculateOptionBuyingCharges(pos.BuyAvg, fillPrice, qty)
		pos.TotalCharges += totalChg
		pos.Brokerage += brk
		pos.STT += stt
		pos.NetProfit = pos.RealizedProfit - pos.TotalCharges
		acc.TotalCharges += totalChg
		acc.TotalBrokerage += brk
		releasedMargin := pos.BuyAvg * float64(qty)
		acc.AvailableBalance += releasedMargin + pnl - totalChg
		if acc.UtilizedMargin >= releasedMargin {
			acc.UtilizedMargin -= releasedMargin
		}
	} else {
		// Short position -> Exit via BUY
		exitSide = "BUY"
		qty = -qty
		pnl := (pos.SellAvg - fillPrice) * float64(qty)
		pos.RealizedProfit += pnl
		pos.BuyQty += qty
		pos.BuyAvg = fillPrice
		totalChg, brk, stt, _, _, _, _ := CalculateOptionBuyingCharges(fillPrice, pos.SellAvg, qty)
		pos.TotalCharges += totalChg
		pos.Brokerage += brk
		pos.STT += stt
		pos.NetProfit = pos.RealizedProfit - pos.TotalCharges
		acc.TotalCharges += totalChg
		acc.TotalBrokerage += brk
		releasedMargin := pos.SellAvg * float64(qty)
		acc.AvailableBalance += releasedMargin + pnl - totalChg
		if acc.UtilizedMargin >= releasedMargin {
			acc.UtilizedMargin -= releasedMargin
		}
	}

	pos.NetQty = 0
	pos.UnrealizedProfit = 0.0
	pos.PositionType = "CLOSED"
	pos.ExitTime = now.Format("15:04:05")

	exitOrderReq := models.OrderRequest{
		DhanClientID:    acc.DhanClientID,
		CorrelationID:   pos.TradingSymbol,
		TransactionType: exitSide,
		ExchangeSegment: pos.ExchangeSegment,
		ProductType:     pos.ProductType,
		OrderType:       "MARKET",
		Validity:        "DAY",
		SecurityID:      pos.SecurityID,
		TradingSymbol:   pos.TradingSymbol,
		Quantity:        qty,
		Price:           fillPrice,
		TriggerPrice:    fillPrice,
		LegName:         triggerReason,
	}

	exitRec := &models.OrderRecord{
		Order:       exitOrderReq,
		OrderID:     orderID,
		ExchangeID:  exchangeID,
		Status:      "TRADED",
		FilledQty:   qty,
		FilledPrice: fillPrice,
		RejectMsg:   fmt.Sprintf("%s at %.2f", triggerReason, fillPrice),
		CreatedAt:   now,
		UpdatedAt:   now,
		EntryTime:   now,
		ExitTime:    now,
	}

	acc.Orders[orderID] = exitRec
	acc.OrderList = append([]string{orderID}, acc.OrderList...)

	webhook := models.DhanPostbackWebhook{
		SessionID:         m.SessionID,
		DhanClientID:      acc.DhanClientID,
		OrderID:           orderID,
		ExchangeOrderID:   exchangeID,
		CorrelationID:     pos.TradingSymbol,
		OrderStatus:       "TRADED",
		TransactionType:   exitSide,
		ExchangeSegment:   pos.ExchangeSegment,
		ProductType:       pos.ProductType,
		OrderType:         "MARKET",
		Validity:          "DAY",
		TradingSymbol:     pos.TradingSymbol,
		SecurityID:        pos.SecurityID,
		Quantity:          qty,
		Price:             fillPrice,
		TriggerPrice:      fillPrice,
		LegName:           triggerReason,
		CreateTime:        nowStr,
		UpdateTime:        nowStr,
		ExchangeTime:      nowStr,
		TradedPrice:       fillPrice,
		TradedQuantity:    qty,
		RejectionReason:   fmt.Sprintf("%s: Traded at %.2f", triggerReason, fillPrice),
	}

	go m.dispatchWebhook(webhook)
	go m.BroadcastAccountStats(acc.DhanClientID)
	go m.BroadcastOrderEvent(acc.DhanClientID, exitRec)
}

// buildPostbackWebhookLocked creates the official DhanPostbackWebhook struct.
func (m *MatchingEngine) buildPostbackWebhookLocked(ord *models.OrderRecord) models.DhanPostbackWebhook {
	nowStr := m.now().Format("2006-01-02 15:04:05")
	sym := ord.Order.TradingSymbol
	if sym == "" {
		sym = ord.Order.CorrelationID
	}
	return models.DhanPostbackWebhook{
		SessionID:         m.SessionID,
		DhanClientID:      ord.Order.DhanClientID,
		OrderID:           ord.OrderID,
		ExchangeOrderID:   ord.ExchangeID,
		CorrelationID:     ord.Order.CorrelationID,
		OrderStatus:       ord.Status,
		TransactionType:   ord.Order.TransactionType,
		ExchangeSegment:   ord.Order.ExchangeSegment,
		ProductType:       ord.Order.ProductType,
		OrderType:         ord.Order.OrderType,
		Validity:          ord.Order.Validity,
		TradingSymbol:     sym,
		SecurityID:        ord.Order.SecurityID,
		Quantity:          ord.Order.Quantity,
		DisclosedQuantity: ord.Order.DisclosedQuantity,
		Price:             ord.Order.Price,
		TriggerPrice:      ord.Order.TriggerPrice,
		LegName:           ord.Order.LegName,
		CreateTime:        ord.CreatedAt.Format("2006-01-02 15:04:05"),
		UpdateTime:        nowStr,
		ExchangeTime:      nowStr,
		TradedPrice:       ord.FilledPrice,
		TradedQuantity:    ord.FilledQty,
		RejectionReason:   ord.RejectMsg,
	}
}

// dispatchWebhook handles chaos modes (drop/delay) and posts payload to Marmot's webhook handler.
func (m *MatchingEngine) dispatchWebhook(webhook models.DhanPostbackWebhook) {
	mode := m.chaos.GetMode()
	if mode == ChaosModeDropWebhooks {
		log.Printf("[MOCK BROKER] Chaos DROP_WEBHOOKS active: Dropped postback for Order %s", webhook.OrderID)
		return
	}
	if mode == ChaosModeDelayWebhooks {
		delay := m.chaos.GetWebhookDelay()
		log.Printf("[MOCK BROKER] Chaos DELAY_WEBHOOKS active: Delaying postback %v for Order %s", delay, webhook.OrderID)
		time.Sleep(delay)
	}

	payload, err := json.Marshal(webhook)
	if err != nil {
		log.Printf("[MOCK BROKER] Failed to marshal postback webhook: %v", err)
		return
	}

	if m.rdb != nil {
		ctx := context.Background()
		err := m.rdb.XAdd(ctx, &redis.XAddArgs{
			Stream: "marmot:webhooks:stream",
			Values: map[string]interface{}{
				"payload":        string(payload),
				"broker_hint":    "dhan",
				"execution_mode": "MOCK",
			},
		}).Err()
		if err != nil {
			log.Printf("[MOCK BROKER] Failed to push webhook to Redis stream: %v", err)
		} else {
			log.Printf("[MOCK BROKER] Dispatched Webhook via Redis: OrderID=%s, Status=%s", webhook.OrderID, webhook.OrderStatus)
		}
		return
	}

	req, err := http.NewRequest("POST", m.postbackURL, bytes.NewBuffer(payload))
	if err != nil {
		log.Printf("[MOCK BROKER] Failed to construct postback request: %v", err)
		return
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := m.httpClient.Do(req)
	if err != nil {
		log.Printf("[MOCK BROKER] Webhook dispatch error to %s: %v", m.postbackURL, err)
		return
	}
	defer resp.Body.Close()

	log.Printf("[MOCK BROKER] Dispatched Webhook via HTTP: OrderID=%s, Status=%s -> Response Code %d", webhook.OrderID, webhook.OrderStatus, resp.StatusCode)
}

// CancelOrder marks an active pending order as CANCELLED.
func (m *MatchingEngine) CancelOrder(clientID, orderID string) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	acc, ok := m.accounts[clientID]
	if !ok {
		return fmt.Errorf("account not found")
	}
	ord, ok := acc.Orders[orderID]
	if !ok {
		return fmt.Errorf("order not found")
	}
	if ord.Status != "PENDING" {
		return fmt.Errorf("cannot cancel order with status %s", ord.Status)
	}

	ord.Status = "CANCELLED"
	ord.UpdatedAt = m.now()
	webhook := m.buildPostbackWebhookLocked(ord)
	go m.dispatchWebhook(webhook)
	return nil
}

// ModifyOrder modifies price or quantity of a pending order.
func (m *MatchingEngine) ModifyOrder(clientID, orderID string, price, triggerPrice float64, qty int) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	acc, ok := m.accounts[clientID]
	if !ok {
		return fmt.Errorf("account not found")
	}
	ord, ok := acc.Orders[orderID]
	if !ok {
		return fmt.Errorf("order not found")
	}
	if ord.Status != "PENDING" {
		return fmt.Errorf("cannot modify order with status %s", ord.Status)
	}

	if price > 0 {
		ord.Order.Price = price
	}
	if triggerPrice > 0 {
		ord.Order.TriggerPrice = triggerPrice
	}
	if qty > 0 {
		ord.Order.Quantity = qty
	}
	ord.UpdatedAt = m.now()
	return nil
}

// GetFundLimit returns official Dhan API v2 fund limit metrics.
func (m *MatchingEngine) GetFundLimit(clientID string) models.FundLimitResponse {
	m.mu.RLock()
	defer m.mu.RUnlock()

	acc, ok := m.accounts[clientID]
	if !ok {
		// Fallback to active account if available, rather than hardcoding 500000
		if activeAcc, haveActive := m.accounts[m.activeAccountID]; haveActive {
			return models.FundLimitResponse{
				DhanClientID:        activeAcc.DhanClientID,
				AvailabelBalance:    activeAcc.AvailableBalance,
				SodLimit:            activeAcc.SodLimit,
				CollateralAmount:    0.0,
				ReceiveableAmount:   0.0,
				UtilizedAmount:      activeAcc.UtilizedMargin,
				BlockedPayoutAmount: 0.0,
				WithdrawableBalance: activeAcc.AvailableBalance,
			}
		}
		return models.FundLimitResponse{
			DhanClientID:        clientID,
			AvailabelBalance:    100000.0,
			SodLimit:            100000.0,
			CollateralAmount:    0.0,
			ReceiveableAmount:   0.0,
			UtilizedAmount:      0.0,
			BlockedPayoutAmount: 0.0,
			WithdrawableBalance: 100000.0,
		}
	}

	return models.FundLimitResponse{
		DhanClientID:        clientID,
		AvailabelBalance:    acc.AvailableBalance,
		SodLimit:            acc.SodLimit,
		CollateralAmount:    0.0,
		ReceiveableAmount:   0.0,
		UtilizedAmount:      acc.UtilizedMargin,
		BlockedPayoutAmount: 0.0,
		WithdrawableBalance: acc.AvailableBalance,
	}
}

// GetPositions returns live position books with real-time Parquet MTM.
func (m *MatchingEngine) GetPositions(clientID string) []models.PositionItem {
	m.mu.RLock()
	defer m.mu.RUnlock()

	acc, ok := m.accounts[clientID]
	if !ok {
		return []models.PositionItem{}
	}

	res := make([]models.PositionItem, 0, len(acc.Positions))
	for _, pos := range acc.Positions {
		res = append(res, *pos)
	}
	return res
}


// GetAllPositions returns all positions across all accounts for dashboard view.
func (m *MatchingEngine) GetAllPositions() []models.PositionItem {
	m.mu.RLock()
	defer m.mu.RUnlock()

	var all []models.PositionItem
	for _, acc := range m.accounts {
		for _, pos := range acc.Positions {
			all = append(all, *pos)
		}
	}
	return all
}

// GetHoldings returns portfolio holdings.
func (m *MatchingEngine) GetHoldings(clientID string) []models.HoldingItem {
	return []models.HoldingItem{}
}

// GetOrders returns recent orders for a client.
func (m *MatchingEngine) GetOrders(clientID string) []*models.OrderRecord {
	m.mu.RLock()
	defer m.mu.RUnlock()

	acc, ok := m.accounts[clientID]
	if !ok {
		return []*models.OrderRecord{}
	}

	res := make([]*models.OrderRecord, 0, len(acc.OrderList))
	for _, id := range acc.OrderList {
		if ord, ok := acc.Orders[id]; ok {
			res = append(res, ord)
		}
	}
	return res
}

// GetAllOrders returns all orders across all accounts for dashboard view.
func (m *MatchingEngine) GetAllOrders() []*models.OrderRecord {
	m.mu.RLock()
	defer m.mu.RUnlock()

	var all []*models.OrderRecord
	for _, acc := range m.accounts {
		for _, id := range acc.OrderList {
			if ord, ok := acc.Orders[id]; ok {
				all = append(all, ord)
			}
		}
	}
	return all
}

// DepositWithdraw adjusts virtual balance for testing.
func (m *MatchingEngine) DepositWithdraw(clientID string, amount float64) float64 {
	m.mu.Lock()
	defer m.mu.Unlock()

	acc := m.getOrCreateAccountLocked(clientID)
	acc.AvailableBalance += amount
	acc.SodLimit += amount
	go m.BroadcastAccountStats(clientID)
	return acc.AvailableBalance
}

// KillSwitch cancels all pending orders across all clients immediately.
func (m *MatchingEngine) KillSwitch() int {
	m.mu.Lock()
	defer m.mu.Unlock()

	cancelled := 0
	for _, acc := range m.accounts {
		for _, ord := range acc.Orders {
			if ord.Status == "PENDING" {
				ord.Status = "CANCELLED"
				ord.UpdatedAt = m.now()
				cancelled++
				webhook := m.buildPostbackWebhookLocked(ord)
				go m.dispatchWebhook(webhook)
			}
		}
	}
	go m.BroadcastAccountStats(m.activeAccountID)
	return cancelled
}


// ClearAccountSession resets orders, positions, and balances back to default.
func (m *MatchingEngine) ClearAccountSession(clientID string) {
	m.mu.Lock()
	acc, ok := m.accounts[clientID]
	if ok {
		acc.Orders = make(map[string]*models.OrderRecord)
		acc.OrderList = make([]string, 0)
		acc.Positions = make(map[string]*models.PositionItem)
		if acc.InitialBalance <= 0 {
			acc.InitialBalance = 100000.0
		}
		acc.AvailableBalance = acc.InitialBalance
		acc.SodLimit = acc.InitialBalance
		acc.UtilizedMargin = 0.0
		acc.TotalCharges = 0.0
		acc.TotalBrokerage = 0.0
	}
	m.mu.Unlock()

	go m.BroadcastAccountStats(clientID)
}

// GetActiveAccountID returns the currently selected active account ID.
func (m *MatchingEngine) GetActiveAccountID() string {
	m.mu.RLock()
	defer m.mu.RUnlock()
	if m.activeAccountID == "" {
		return "1000000001"
	}
	return m.activeAccountID
}

// SetActiveAccountID sets the active account ID if it exists.
func (m *MatchingEngine) SetActiveAccountID(id string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	if _, ok := m.accounts[id]; !ok {
		return fmt.Errorf("account %s not found", id)
	}
	m.activeAccountID = id
	return nil
}

// GetAccount returns the specified ClientAccount.
func (m *MatchingEngine) GetAccount(id string) (*ClientAccount, bool) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	acc, ok := m.accounts[id]
	return acc, ok
}

// GetAllAccounts returns all accounts in deterministic order.
func (m *MatchingEngine) GetAllAccounts() []*ClientAccount {
	m.mu.RLock()
	defer m.mu.RUnlock()
	list := make([]*ClientAccount, 0, len(m.accountList))
	for _, id := range m.accountList {
		if acc, ok := m.accounts[id]; ok {
			list = append(list, acc)
		}
	}
	return list
}

// CreateAccount adds a new mock account to the engine.
func (m *MatchingEngine) CreateAccount(id, name, broker string, initialBalance float64) (*ClientAccount, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	id = strings.TrimSpace(id)
	if id == "" {
		id = fmt.Sprintf("100000%04d", len(m.accounts)+1)
	}
	if _, exists := m.accounts[id]; exists {
		return nil, fmt.Errorf("account ID %s already exists", id)
	}
	if name == "" {
		name = fmt.Sprintf("Trading Account %s", id)
	}
	if broker == "" {
		broker = "Dhan"
	}
	if initialBalance <= 0 {
		initialBalance = 500000.0
	}
	acc := &ClientAccount{
		DhanClientID:     id,
		AccountName:      name,
		Broker:           broker,
		AvailableBalance: initialBalance,
		SodLimit:         initialBalance,
		UtilizedMargin:   0.0,
		CreatedAt:        m.now(),
		Orders:           make(map[string]*models.OrderRecord),
		OrderList:        make([]string, 0),
		Positions:        make(map[string]*models.PositionItem),
	}
	m.accounts[id] = acc
	m.accountList = append(m.accountList, id)
	m.activeAccountID = id
	return acc, nil
}

// UpdateAccount updates account metadata and balance adjustment.
func (m *MatchingEngine) UpdateAccount(id, name, broker string, adjustAmount float64) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	acc, exists := m.accounts[id]
	if !exists {
		return fmt.Errorf("account %s not found", id)
	}
	if name != "" {
		acc.AccountName = name
	}
	if broker != "" {
		acc.Broker = broker
	}
	if adjustAmount != 0 {
		acc.AvailableBalance += adjustAmount
		acc.SodLimit += adjustAmount
		acc.InitialBalance = acc.AvailableBalance
	}
	return nil
}

// DeleteAccount removes an account with safety checks.
func (m *MatchingEngine) DeleteAccount(id string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	if len(m.accounts) <= 1 {
		return fmt.Errorf("cannot delete the only remaining account")
	}
	acc, exists := m.accounts[id]
	if !exists {
		return fmt.Errorf("account %s not found", id)
	}
	for _, p := range acc.Positions {
		if p.NetQty != 0 {
			return fmt.Errorf("cannot delete account %s with active open positions (Square off first)", id)
		}
	}
	delete(m.accounts, id)
	newList := make([]string, 0, len(m.accountList)-1)
	for _, item := range m.accountList {
		if item != id {
			newList = append(newList, item)
		}
	}
	m.accountList = newList

	if m.activeAccountID == id {
		if len(m.accountList) > 0 {
			m.activeAccountID = m.accountList[0]
		}
	}
	return nil
}

// GetPerformanceSummary computes session-level performance analytics and cumulative equity curve.
func (m *MatchingEngine) GetPerformanceSummary(clientID string) models.PerformanceSummary {
	m.mu.RLock()
	defer m.mu.RUnlock()

	summary := models.PerformanceSummary{
		InitialCapital: 500000.0,
		EquityCurve:    []models.EquityPoint{},
	}

	acc, ok := m.accounts[clientID]
	if !ok {
		return summary
	}

	summary.InitialCapital = acc.SodLimit
	if summary.InitialCapital <= 0 {
		summary.InitialCapital = 500000.0
	}

	var cumPnL float64
	peakEquity := summary.InitialCapital
	maxDD := 0.0

	summary.EquityCurve = append(summary.EquityCurve, models.EquityPoint{
		Timestamp: "09:15:00",
		PnL:       0.0,
		Equity:    summary.InitialCapital,
	})

	for _, pos := range acc.Positions {
		if pos.NetQty == 0 || pos.PositionType == "CLOSED" {
			summary.TotalTrades++
			pnl := pos.RealizedProfit
			if pnl > 0 {
				summary.WinningTrades++
				summary.GrossProfit += pnl
			} else if pnl < 0 {
				summary.LosingTrades++
				summary.GrossLoss += math.Abs(pnl)
			}

			cumPnL += pnl
			currentEquity := summary.InitialCapital + cumPnL
			if currentEquity > peakEquity {
				peakEquity = currentEquity
			}
			dd := peakEquity - currentEquity
			if dd > maxDD {
				maxDD = dd
			}

			tStr := pos.ExitTime
			if tStr == "" {
				tStr = pos.EntryTime
			}
			if tStr == "" {
				tStr = m.now().Format("15:04:05")
			}

			summary.EquityCurve = append(summary.EquityCurve, models.EquityPoint{
				Timestamp: tStr,
				PnL:       math.Round(cumPnL*100) / 100,
				Equity:    math.Round(currentEquity*100) / 100,
			})
			summary.ClosedPositions = append(summary.ClosedPositions, *pos)
		}
	}

	summary.TotalCharges = math.Round(acc.TotalCharges*100) / 100
	summary.TotalBrokerage = math.Round(acc.TotalBrokerage*100) / 100
	summary.NetRealizedPnL = math.Round((cumPnL-acc.TotalCharges)*100) / 100
	summary.FinalEquity = math.Round((summary.InitialCapital+cumPnL-acc.TotalCharges)*100) / 100

	if summary.TotalTrades > 0 {
		summary.WinRate = math.Round(float64(summary.WinningTrades)/float64(summary.TotalTrades)*1000) / 10
	}

	if summary.GrossLoss > 0 {
		summary.ProfitFactor = math.Round((summary.GrossProfit/summary.GrossLoss)*100) / 100
	} else if summary.GrossProfit > 0 {
		summary.ProfitFactor = 99.99
	}

	summary.MaxDrawdown = math.Round(maxDD*100) / 100
	if peakEquity > 0 {
		summary.MaxDrawdownPct = math.Round((maxDD/peakEquity)*1000) / 10
	}
	if summary.InitialCapital > 0 {
		summary.ROI = math.Round(((cumPnL-acc.TotalCharges)/summary.InitialCapital)*1000) / 10
	}

	return summary
}

// StartRedisOrderConsumer starts consuming from marmot:mock:orders
func (m *MatchingEngine) StartRedisOrderConsumer(ctx context.Context) {
	if m.rdb == nil {
		log.Println("[MOCK BROKER] Redis client is nil, skipping Redis consumer")
		return
	}

	streamName := "marmot:mock:orders"
	groupName := "mock_broker_group"
	consumerName := "consumer-1"

	err := m.rdb.XGroupCreateMkStream(ctx, streamName, groupName, "0").Err()
	if err != nil && !strings.Contains(err.Error(), "BUSYGROUP") {
		log.Printf("[MOCK BROKER] Failed to create Redis consumer group: %v", err)
	}

	log.Printf("[MOCK BROKER] Started consuming from Redis stream: %s", streamName)

	for {
		streams, err := m.rdb.XReadGroup(ctx, &redis.XReadGroupArgs{
			Group:    groupName,
			Consumer: consumerName,
			Streams:  []string{streamName, ">"},
			Count:    10,
			Block:    2 * time.Second,
		}).Result()

		if err != nil && err != redis.Nil {
			log.Printf("[MOCK BROKER] Redis XReadGroup error: %v", err)
			time.Sleep(1 * time.Second)
			continue
		}

		for _, stream := range streams {
			for _, msg := range stream.Messages {
				payloadStr, ok := msg.Values["payload"].(string)
				if !ok {
					log.Printf("[MOCK BROKER] Invalid message format in stream %s", msg.ID)
					m.rdb.XAck(ctx, streamName, groupName, msg.ID)
					continue
				}

				var req models.OrderRequest
				if err := json.Unmarshal([]byte(payloadStr), &req); err != nil {
					log.Printf("[MOCK BROKER] Failed to unmarshal order payload: %v", err)
					m.rdb.XAck(ctx, streamName, groupName, msg.ID)
					continue
				}

				// Optionally parse logical_timestamp if passed in the values
				if tsStr, ok := msg.Values["logical_timestamp"].(string); ok && tsStr != "" {
					// Store it somewhere if tick-level accuracy needs it
					// Right now we just execute it via PlaceOrder
				}

				log.Printf("[MOCK BROKER] Received order via Redis: %s", req.CorrelationID)

				// Execute PlaceOrder
				resp, err := m.PlaceOrder(req)
				if err != nil {
					log.Printf("[MOCK BROKER] PlaceOrder error via Redis: %v", err)
				} else if resp != nil && resp.OrderID != "" {
					log.Printf("[MOCK BROKER] Order placed successfully via Redis: %s", resp.OrderID)
				}

				// Ack message
				m.rdb.XAck(ctx, streamName, groupName, msg.ID)
			}
		}
	}
}
