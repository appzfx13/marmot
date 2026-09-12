package engine

import (
	"bytes"
	"encoding/json"
	"fmt"
	"log"
	"math/rand"
	"net/http"
	"sync"
	"time"

	"dhan-emulator/models"
)

// ClientAccount tracks isolated virtual balance, orders, and positions per dhanClientId.
type ClientAccount struct {
	DhanClientID     string                          `json:"dhanClientId"`
	AvailableBalance float64                         `json:"availableBalance"`
	SodLimit         float64                         `json:"sodLimit"`
	UtilizedMargin   float64                         `json:"utilizedMargin"`
	Orders           map[string]*models.OrderRecord  `json:"orders"`
	OrderList        []string                        `json:"orderList"` // ordered IDs
	Positions        map[string]*models.PositionItem `json:"positions"` // key: securityId + "_" + productType
}

// MatchingEngine manages the central thread-safe multi-client mock broker state.
type MatchingEngine struct {
	mu           sync.RWMutex
	accounts     map[string]*ClientAccount
	ltpMap       map[string]float64
	chaos        *ChaosManager
	postbackURL  string
	httpClient   *http.Client
	orderCounter int64
}

// NewMatchingEngine initializes the MatchingEngine.
func NewMatchingEngine(chaos *ChaosManager, postbackURL string) *MatchingEngine {
	if postbackURL == "" {
		postbackURL = "http://web:8000/postback/dhan/postback/"
	}
	return &MatchingEngine{
		accounts:    make(map[string]*ClientAccount),
		ltpMap:      make(map[string]float64),
		chaos:       chaos,
		postbackURL: postbackURL,
		httpClient:  &http.Client{Timeout: 5 * time.Second},
	}
}

// getOrCreateAccountLocked returns the ClientAccount, initializing with default 5,00,000 if new.
func (m *MatchingEngine) getOrCreateAccountLocked(clientID string) *ClientAccount {
	if clientID == "" {
		clientID = "1000000001"
	}
	acc, exists := m.accounts[clientID]
	if !exists {
		acc = &ClientAccount{
			DhanClientID:     clientID,
			AvailableBalance: 500000.0,
			SodLimit:         500000.0,
			UtilizedMargin:   0.0,
			Orders:           make(map[string]*models.OrderRecord),
			OrderList:        make([]string, 0),
			Positions:        make(map[string]*models.PositionItem),
		}
		m.accounts[clientID] = acc
	}
	return acc
}

// IngestTick updates internal LTP for symbols and recalculates MTM for all active accounts.
func (m *MatchingEngine) IngestTick(tick models.MarketTick) {
	m.mu.Lock()
	defer m.mu.Unlock()

	if tick.SecurityID == "" || tick.LTP <= 0 {
		return
	}
	m.ltpMap[tick.SecurityID] = tick.LTP

	// Recalculate Unrealized PnL and MTM across open positions
	for _, acc := range m.accounts {
		for _, pos := range acc.Positions {
			if pos.SecurityID == tick.SecurityID && pos.NetQty != 0 {
				if pos.NetQty > 0 {
					pos.UnrealizedProfit = (tick.LTP - pos.BuyAvg) * float64(pos.NetQty)
				} else {
					pos.UnrealizedProfit = (pos.SellAvg - tick.LTP) * float64(-pos.NetQty)
				}
			}
		}
	}

	// Autonomous SL/TP Check on pending orders
	for _, acc := range m.accounts {
		for _, ord := range acc.Orders {
			if ord.Status == "PENDING" && ord.Order.SecurityID == tick.SecurityID {
				isTriggered := false
				if ord.Order.OrderType == "STOP_LOSS" || ord.Order.OrderType == "STOP_LOSS_MARKET" {
					if ord.Order.TransactionType == "BUY" && tick.LTP >= ord.Order.TriggerPrice {
						isTriggered = true
					} else if ord.Order.TransactionType == "SELL" && tick.LTP <= ord.Order.TriggerPrice {
						isTriggered = true
					}
				}
				if isTriggered {
					go m.executeOrderAsync(acc.DhanClientID, ord.OrderID, tick.LTP)
				}
			}
		}
	}
}

// PlaceOrder validates and creates a new order in PENDING status, then launches async execution.
func (m *MatchingEngine) PlaceOrder(req models.OrderRequest) (*models.OrderResponse, error) {
	m.mu.Lock()
	m.orderCounter++
	now := time.Now()
	orderID := fmt.Sprintf("DHN%d%04d", now.Unix(), rand.Intn(10000))
	exchangeID := fmt.Sprintf("NSE%d%04d", now.Unix(), rand.Intn(10000))

	acc := m.getOrCreateAccountLocked(req.DhanClientID)
	rec := &models.OrderRecord{
		Order:       req,
		OrderID:     orderID,
		ExchangeID:  exchangeID,
		Status:      "PENDING",
		FilledQty:   0,
		FilledPrice: 0.0,
		CreatedAt:   now,
		UpdatedAt:   now,
	}

	acc.Orders[orderID] = rec
	acc.OrderList = append([]string{orderID}, acc.OrderList...)
	m.mu.Unlock()

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
		ord.UpdatedAt = time.Now()
		webhook := m.buildPostbackWebhookLocked(ord)
		m.mu.Unlock()
		m.dispatchWebhook(webhook)
		return
	}

	// 2. Resolve Fill Price
	fillPrice := ord.Order.Price
	if fillPrice <= 0 {
		if ltp, hasLtp := m.ltpMap[ord.Order.SecurityID]; hasLtp && ltp > 0 {
			fillPrice = ltp
		} else {
			fillPrice = 100.0 // Default baseline fill price
		}
	}

	// 3. Margin & Funds Verification
	requiredMargin := float64(ord.Order.Quantity) * fillPrice
	if ord.Order.TransactionType == "BUY" && acc.AvailableBalance < requiredMargin {
		ord.Status = "REJECTED"
		ord.RejectMsg = fmt.Sprintf("MARGIN_INSUFFICIENT: Required %.2f, Available %.2f", requiredMargin, acc.AvailableBalance)
		ord.UpdatedAt = time.Now()
		webhook := m.buildPostbackWebhookLocked(ord)
		m.mu.Unlock()
		m.dispatchWebhook(webhook)
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
	ord.UpdatedAt = time.Now()
	ord.EntryTime = ord.CreatedAt
	ord.StopLoss = ord.Order.BoStopLossValue
	if ord.StopLoss == 0 {
		ord.StopLoss = ord.Order.TriggerPrice
	}
	ord.TakeProfit = ord.Order.BoProfitValue

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
			EntryTime:       time.Now().Format("15:04:05"),
			StopLoss:        ord.StopLoss,
			TakeProfit:      ord.TakeProfit,
		}
		acc.Positions[posKey] = pos
	}

	if ord.Order.TransactionType == "BUY" {
		acc.AvailableBalance -= requiredMargin
		acc.UtilizedMargin += requiredMargin
		totalBuyValue := (pos.BuyAvg * float64(pos.BuyQty)) + (fillPrice * float64(ord.Order.Quantity))
		pos.BuyQty += ord.Order.Quantity
		pos.BuyAvg = totalBuyValue / float64(pos.BuyQty)
		pos.NetQty = pos.BuyQty - pos.SellQty
		if pos.EntryTime == "" {
			pos.EntryTime = time.Now().Format("15:04:05")
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
		// Realized profit calculation
		if pos.BuyQty > 0 {
			pos.RealizedProfit += (fillPrice - pos.BuyAvg) * float64(ord.Order.Quantity)
		}
	}

	if pos.NetQty > 0 {
		pos.PositionType = "LONG"
	} else if pos.NetQty < 0 {
		pos.PositionType = "SHORT"
	} else {
		pos.PositionType = "CLOSED"
		pos.ExitTime = time.Now().Format("15:04:05")
		ord.ExitTime = time.Now()
	}

	webhook := m.buildPostbackWebhookLocked(ord)
	m.mu.Unlock()

	m.dispatchWebhook(webhook)
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
	if !ok || ord.Status != "PENDING" {
		m.mu.Unlock()
		return
	}

	ord.Status = "TRADED"
	ord.FilledQty = ord.Order.Quantity
	ord.FilledPrice = fillPrice
	ord.UpdatedAt = time.Now()

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
		pos.BuyQty += ord.Order.Quantity
		pos.BuyAvg = fillPrice
		pos.NetQty = pos.BuyQty - pos.SellQty
	} else {
		acc.AvailableBalance += requiredMargin
		pos.SellQty += ord.Order.Quantity
		pos.SellAvg = fillPrice
		pos.NetQty = pos.BuyQty - pos.SellQty
	}

	webhook := m.buildPostbackWebhookLocked(ord)
	m.mu.Unlock()

	m.dispatchWebhook(webhook)
}

// buildPostbackWebhookLocked creates the official DhanPostbackWebhook struct.
func (m *MatchingEngine) buildPostbackWebhookLocked(ord *models.OrderRecord) models.DhanPostbackWebhook {
	nowStr := time.Now().Format("2006-01-02 15:04:05")
	return models.DhanPostbackWebhook{
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
		TradingSymbol:     ord.Order.CorrelationID,
		SecurityID:        ord.Order.SecurityID,
		Quantity:          ord.Order.Quantity,
		DisclosedQuantity: ord.Order.DisclosedQuantity,
		Price:             ord.Order.Price,
		TriggerPrice:      ord.Order.TriggerPrice,
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

	log.Printf("[MOCK BROKER] Dispatched Webhook: OrderID=%s, Status=%s -> Response Code %d", webhook.OrderID, webhook.OrderStatus, resp.StatusCode)
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
	ord.UpdatedAt = time.Now()
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
	ord.UpdatedAt = time.Now()
	return nil
}

// GetFundLimit returns official Dhan API v2 fund limit metrics.
func (m *MatchingEngine) GetFundLimit(clientID string) models.FundLimitResponse {
	m.mu.RLock()
	defer m.mu.RUnlock()

	acc, ok := m.accounts[clientID]
	if !ok {
		return models.FundLimitResponse{
			DhanClientID:        clientID,
			AvailabelBalance:    500000.0,
			SodLimit:            500000.0,
			CollateralAmount:    0.0,
			ReceiveableAmount:   0.0,
			UtilizedAmount:      0.0,
			BlockedPayoutAmount: 0.0,
			WithdrawableBalance: 500000.0,
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
				ord.UpdatedAt = time.Now()
				cancelled++
				webhook := m.buildPostbackWebhookLocked(ord)
				go m.dispatchWebhook(webhook)
			}
		}
	}
	return cancelled
}
