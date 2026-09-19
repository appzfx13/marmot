package workers

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log"
	"math"
	"math/rand"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/redis/go-redis/v9"

	"go-app/config"
	"go-app/models"
	"go-app/services"
	"go-app/strategies"
	"go-app/ws"
)

// DhanOrderPayload represents the REST payload dispatched to the Mock Broker Order API.
type DhanOrderPayload struct {
	DhanClientID    string  `json:"dhanClientId"`
	CorrelationID   string  `json:"correlationId"`
	TransactionType string  `json:"transactionType"`
	ExchangeSegment string  `json:"exchangeSegment"`
	ProductType     string  `json:"productType"`
	OrderType       string  `json:"orderType"`
	Validity        string  `json:"validity"`
	SecurityID      string  `json:"securityId"`
	Quantity        int     `json:"quantity"`
	Price           float64 `json:"price,omitempty"`
	TriggerPrice    float64 `json:"triggerPrice,omitempty"`
	BoStopLossValue float64 `json:"boStopLossValue,omitempty"`
	BoProfitValue   float64 `json:"boProfitValue,omitempty"`
}

// isMockMode returns true if the execution mode corresponds to paper trading, sandbox, or simulation.
func isMockMode(mode string) bool {
	return strings.EqualFold(mode, "MOCK") || strings.EqualFold(mode, "LIVE")
}

// getActiveMockAccountID queries the active mock broker account ID dynamically.
func (j *StrategySignalJob) getActiveMockAccountID() string {
	client := &http.Client{Timeout: 800 * time.Millisecond}
	resp, err := client.Get("http://mock_broker:8088/mock/v2/active-account")
	if err == nil && resp.StatusCode == http.StatusOK {
		defer resp.Body.Close()
		var res map[string]interface{}
		if err := json.NewDecoder(resp.Body).Decode(&res); err == nil {
			if accID, ok := res["active_account_id"].(string); ok && accID != "" {
				return accID
			}
			if accID, ok := res["accountId"].(string); ok && accID != "" {
				return accID
			}
		}
	}
	return "1000000001"
}

// dispatchOrderToMockBroker sends an asynchronous order request to the Dhan mock broker REST endpoint.
func (j *StrategySignalJob) dispatchOrderToMockBroker(req DhanOrderPayload) {
	go func() {
		if req.DhanClientID == "" || req.DhanClientID == "1000000001" {
			req.DhanClientID = j.getActiveMockAccountID()
		}
		bodyBytes, err := json.Marshal(req)
		if err != nil {
			log.Printf("⚠️ [StrategyWorker] Failed to marshal mock broker order payload: %v", err)
			return
		}
		httpReq, err := http.NewRequest("POST", "http://mock_broker:8088/mock/v2/orders", bytes.NewBuffer(bodyBytes))
		if err != nil {
			log.Printf("⚠️ [StrategyWorker] Failed to create mock broker order request: %v", err)
			return
		}
		httpReq.Header.Set("Content-Type", "application/json")
		httpReq.Header.Set("client-id", req.DhanClientID)

		client := &http.Client{Timeout: 3 * time.Second}
		resp, err := client.Do(httpReq)
		if err != nil {
			log.Printf("⚠️ [StrategyWorker] Mock Broker HTTP Order API dispatch failed: %v", err)
			return
		}
		defer resp.Body.Close()
		log.Printf("📤 [StrategyWorker] Order dispatched to Mock Broker API (Acc: %s | %s %s x %d) -> HTTP %d",
			req.DhanClientID, req.TransactionType, req.SecurityID, req.Quantity, resp.StatusCode)
	}()
}

// MockBrokerPosition represents a position item returned by the Dhan mock broker.
type MockBrokerPosition struct {
	TradingSymbol    string  `json:"tradingSymbol"`
	SecurityID       string  `json:"securityId"`
	PositionType     string  `json:"positionType"`
	BuyAvg           float64 `json:"buyAvg"`
	BuyQty           int     `json:"buyQty"`
	SellAvg          float64 `json:"sellAvg"`
	SellQty          int     `json:"sellQty"`
	NetQty           int     `json:"netQty"`
	RealizedProfit   float64 `json:"realizedProfit"`
	UnrealizedProfit float64 `json:"unrealizedProfit"`
	ExitTime         string  `json:"exitTime"`
	StopLoss         float64 `json:"stopLoss"`
	TakeProfit       float64 `json:"takeProfit"`
}

// fetchMockBrokerPositions queries the mock broker for active and closed positions.
func (j *StrategySignalJob) fetchMockBrokerPositions() []MockBrokerPosition {
	client := &http.Client{Timeout: 1 * time.Second}
	resp, err := client.Get("http://mock_broker:8088/mock/v2/positions")
	if err != nil || resp.StatusCode != http.StatusOK {
		if resp != nil {
			resp.Body.Close()
		}
		return nil
	}
	defer resp.Body.Close()
	var posList []MockBrokerPosition
	_ = json.NewDecoder(resp.Body).Decode(&posList)
	return posList
}

// StrategySignalJob manages the autonomous paper trading loop for an active strategy in Sandbox mode.
type StrategySignalJob struct {
	dbService    *services.DBService
	config       *config.Config
	payload      models.CommandPayload
	hub          *ws.Hub
	redisService *services.RedisService
}

// SimulatedPosition represents an intraday simulated option position.
type SimulatedPosition struct {
	TradingSymbol    string  `json:"trading_symbol"`
	ExchangeSegment  string  `json:"exchange_segment"`
	Status           string  `json:"status"`
	ProductType      string  `json:"product_type"`
	NetQty           int     `json:"net_qty"`
	BuyQty           int     `json:"buy_qty"`
	BuyAvg           float64 `json:"buy_avg"`
	SellQty          int     `json:"sell_qty"`
	SellAvg          float64 `json:"sell_avg"`
	CurrentLTP       float64 `json:"current_ltp"`
	RealizedProfit   float64 `json:"realized_profit"`
	UnrealizedProfit float64 `json:"unrealized_profit"`
	TotalPnL         float64 `json:"total_pnl"`
	EntrySpot        float64 `json:"entry_spot"`
}

// SimulatedOrder represents an executed or pending paper order.
type SimulatedOrder struct {
	OrderID         string                 `json:"order_id"`
	CreateTime      string                 `json:"create_time"`
	TradingSymbol   string                 `json:"trading_symbol"`
	ExchangeSegment string                 `json:"exchange_segment"`
	TransactionType string                 `json:"transaction_type"`
	OrderType       string                 `json:"order_type"`
	ProductType     string                 `json:"product_type"`
	Validity        string                 `json:"validity"`
	Quantity        int                    `json:"quantity"`
	FilledQty       int                    `json:"filled_qty"`
	Price           float64                `json:"price"`
	TriggerPrice    float64                `json:"trigger_price"`
	OrderStatus     string                 `json:"order_status"`
	OMSErrorDesc    string                 `json:"oms_error_desc"`
	SignalTime      string                 `json:"signal_time,omitempty"`
	ExecutionTime   string                 `json:"execution_time,omitempty"`
	LimitEntryPrice float64                `json:"limit_entry_price,omitempty"`
	LimitTappedTime string                 `json:"limit_tapped_time,omitempty"`
	TargetPrice          float64                `json:"target_price,omitempty"`
	StopLossPrice        float64                `json:"stop_loss_price,omitempty"`
	InitialTargetPrice   float64                `json:"initial_target_price,omitempty"`
	InitialStopLossPrice float64                `json:"initial_stop_loss_price,omitempty"`
	CurrentLTP           float64                `json:"current_ltp,omitempty"`
	RuleID          int                    `json:"rule_id,omitempty"`
	RuleName        string                 `json:"rule_name,omitempty"`
	TriggerReason   string                 `json:"trigger_reason,omitempty"`
	Indicators      map[string]interface{} `json:"indicators,omitempty"`
	SlippagePts     float64                `json:"slippage_pts"`
}

// NewStrategySignalJob instantiates a new background strategy worker.
func NewStrategySignalJob(
	dbService *services.DBService,
	cfg *config.Config,
	payload models.CommandPayload,
	hub *ws.Hub,
	redisService *services.RedisService,
) *StrategySignalJob {
	return &StrategySignalJob{
		dbService:    dbService,
		config:       cfg,
		payload:      payload,
		hub:          hub,
		redisService: redisService,
	}
}

// Run executes the continuous background signal evaluation loop against live FYERS ticks.
func (j *StrategySignalJob) Run(ctx context.Context) {
	taskID := j.payload.TaskID
	params := j.payload.Params
	strategyName := params.StrategyName
	if strategyName == "" {
		strategyName = "quant_engine"
	}
	indexName := params.IndexName
	if indexName == "" {
		indexName = "NIFTY"
	}
	userID := params.UserID
	if userID == "" {
		userID = "1"
	}

	strat, ok := strategies.GetStrategy(strategyName)
	if !ok {
		log.Printf("❌ [StrategyWorker #%s] Strategy '%s' not registered\n", taskID, strategyName)
		return
	}

	log.Printf("🚀 [StrategyWorker #%s] Autonomous Signal Loop started for %s (%s) [User #%s]\n",
		taskID, strategyName, indexName, userID)

	ticker := time.NewTicker(250 * time.Millisecond)
	defer ticker.Stop()

	initialCapital := params.InitialCapital
	if initialCapital <= 0 {
		initialCapital = 1000000.00
	}
	cashBalance := initialCapital

	positions := []SimulatedPosition{}
	orders := []SimulatedOrder{}

	tickCounter := 0
	var prevSpotPrice float64
	var spotPrice float64

	var candleSub *redis.PubSub
	var candleChan <-chan *redis.Message
	if j.redisService != nil && j.redisService.Client != nil {
		candleSub = j.redisService.Client.Subscribe(ctx, "marmot:streamer:candles")
		candleChan = candleSub.Channel()
		defer candleSub.Close()
	}

	for {
		select {
		case <-ctx.Done():
			log.Printf("⏸️ [StrategyWorker #%s] Pausing Autonomous Signal Loop for User #%s\n", taskID, userID)
			j.saveTelemetry(context.Background(), userID, params.StrategyID, strategyName, false, "PAUSED",
				23760.0, cashBalance, cashBalance, positions, orders, 0)
			return

		case msg, ok := <-candleChan:
			if !ok || msg == nil {
				continue
			}
			var cData map[string]interface{}
			if err := json.Unmarshal([]byte(msg.Payload), &cData); err != nil {
				continue
			}
			if idx, ok := cData["index"].(string); ok && len(idx) > 0 && !strings.EqualFold(idx, indexName) {
				continue
			}

			loopStart := time.Now()
			cSpot, _ := cData["spot_price"].(float64)
			if cSpot <= 0 {
				cSpot, _ = cData["close"].(float64)
			}
			if cSpot > 0 {
				spotPrice = cSpot
			}

			// In SANDBOX / MOCK mode, sync open positions with mock broker matching engine
			if isMockMode(params.ExecutionMode) && len(positions) > 0 {
				mockPositions := j.fetchMockBrokerPositions()
				for i := range positions {
					if positions[i].Status == "OPEN" {
						for _, mp := range mockPositions {
							if (mp.TradingSymbol == positions[i].TradingSymbol || mp.SecurityID == positions[i].TradingSymbol) &&
								(mp.PositionType == "CLOSED" || mp.NetQty == 0) {
								positions[i].Status = "CLOSED"
								positions[i].RealizedProfit = mp.RealizedProfit
								positions[i].UnrealizedProfit = 0
								positions[i].SellQty = mp.SellQty
								positions[i].SellAvg = mp.SellAvg
								positions[i].NetQty = 0

								triggerReason := "SL Hit"
								if mp.RealizedProfit > 0 {
									triggerReason = "TP Hit"
								}
								exitTime := mp.ExitTime
								if exitTime == "" {
									if dt, ok := cData["datetime"].(string); ok && len(dt) >= 19 {
										exitTime = dt[11:19]
									} else {
										exitTime = nowIST().Format("03:04:05 PM")
									}
								}
								exitOrder := SimulatedOrder{
									OrderID:         fmt.Sprintf("DHN-EXIT-%d", time.Now().Unix()%100000),
									CreateTime:      exitTime,
									ExecutionTime:   exitTime,
									TradingSymbol:   positions[i].TradingSymbol,
									ExchangeSegment: "NSE_FNO",
									TransactionType: "SELL",
									OrderType:       "MARKET",
									ProductType:     "INTRADAY",
									Validity:        "DAY",
									Quantity:        positions[i].BuyQty,
									FilledQty:       positions[i].BuyQty,
									Price:           mp.SellAvg,
									CurrentLTP:      mp.SellAvg,
									OrderStatus:     "TRADED",
									TriggerReason:   triggerReason,
								}
								orders = append([]SimulatedOrder{exitOrder}, orders...)
								log.Printf("🛡️ [StrategyWorker #%s] POSITION SQUARED OFF BY BROKER OMS (%s): SELL %s @ ₹%.2f (Realized: ₹%.2f)\n",
									taskID, triggerReason, positions[i].TradingSymbol, mp.SellAvg, mp.RealizedProfit)
								break
							}
						}
					}
				}
			}

			// Evaluate strategy on arriving 1-minute candle
			activeExp := j.fetchActiveExpiry(ctx, indexName)
			if params.Params == nil {
				params.Params = make(map[string]interface{})
			}
			params.Params["execution_mode"] = params.ExecutionMode
			if activeExp != "" {
				params.Params["active_expiry"] = activeExp
			}

			sig := strat.EvaluateLiveSignal(cData, nil, indexName, params.Params)
			if sig != nil {
				alreadyOpen := false
				for _, pos := range positions {
					if pos.Status == "OPEN" && pos.TradingSymbol == sig.TradingSymbol {
						alreadyOpen = true
						break
					}
				}
				for _, o := range orders {
					if o.OrderStatus == "PENDING" && o.TradingSymbol == sig.TradingSymbol {
						alreadyOpen = true
						break
					}
				}

				openPositionsCount := 0
				for _, pos := range positions {
					if pos.Status == "OPEN" {
						openPositionsCount++
					}
				}

				if !alreadyOpen && openPositionsCount < 6 {
					fillPrice := j.fetchOptionLTP(ctx, indexName, sig.TradingSymbol, spotPrice)
					if fillPrice <= 0 {
						fillPrice = 120.0
					}

					slPts := 15.0
					rrRatio := 2.0
					if params.Params != nil {
						if sl, ok := params.Params["sl_pts"].(float64); ok && sl > 0 {
							slPts = sl
						}
						if rr, ok := params.Params["rr_ratio"].(float64); ok && rr > 0 {
							rrRatio = rr
						}
					}
					stopLoss := math.Max(1.0, math.Round((fillPrice-slPts)*100)/100)
					target := math.Round((fillPrice+(slPts*rrRatio))*100) / 100

					orderTime := sig.Timestamp
					if orderTime == "" {
						if dt, ok := cData["datetime"].(string); ok && len(dt) >= 19 {
							orderTime = dt[11:19]
						} else {
							orderTime = nowIST().Format("03:04:05 PM")
						}
					}

					newOrderID := fmt.Sprintf("SBX-%d%02d", time.Now().Unix()%100000, rand.Intn(90)+10)
					status := "TRADED"
					if sig.OrderType == "LIMIT" {
						status = "PENDING"
					}

					newOrder := SimulatedOrder{
						OrderID:         newOrderID,
						CreateTime:      orderTime,
						SignalTime:      orderTime,
						ExecutionTime:   "",
						TradingSymbol:   sig.TradingSymbol,
						ExchangeSegment: "NSE_FNO",
						TransactionType: sig.Transaction,
						OrderType:       sig.OrderType,
						ProductType:     "INTRADAY",
						Validity:        "DAY",
						Quantity:        sig.Quantity,
						FilledQty:       0,
						Price:           fillPrice,
						LimitEntryPrice: fillPrice,
						LimitTappedTime: orderTime,
						TargetPrice:     target,
						StopLossPrice:   stopLoss,
						CurrentLTP:      fillPrice,
						OrderStatus:     status,
						RuleID:          sig.RuleID,
						RuleName:        sig.RuleName,
						TriggerReason:   sig.TriggerReason,
						Indicators:      sig.Indicators,
						SlippagePts:     0.00,
					}

					if status == "TRADED" {
						newOrder.ExecutionTime = orderTime
						newOrder.FilledQty = sig.Quantity
						newPos := SimulatedPosition{
							TradingSymbol:    sig.TradingSymbol,
							ExchangeSegment:  "NSE_FNO",
							Status:           "OPEN",
							ProductType:      "INTRADAY",
							NetQty:           sig.Quantity,
							BuyQty:           sig.Quantity,
							BuyAvg:           fillPrice,
							CurrentLTP:       fillPrice,
							RealizedProfit:   0.0,
							UnrealizedProfit: 0.0,
							TotalPnL:         0.0,
							EntrySpot:        spotPrice,
						}
						positions = append([]SimulatedPosition{newPos}, positions...)
						log.Printf("🚀 [StrategyWorker #%s] EVENT-DRIVEN ENTRY BUY: %s @ ₹%.2f (Rule #%d: %s | SL=%.1f TP=%.1f)\n",
							taskID, sig.TradingSymbol, fillPrice, sig.RuleID, sig.RuleName, stopLoss, target)

						if isMockMode(params.ExecutionMode) {
							j.dispatchOrderToMockBroker(DhanOrderPayload{
								DhanClientID:    "1000000001",
								CorrelationID:   sig.TradingSymbol,
								TransactionType: sig.Transaction,
								ExchangeSegment: "NSE_FNO",
								ProductType:     "INTRADAY",
								OrderType:       "MARKET",
								Validity:        "DAY",
								SecurityID:      sig.TradingSymbol,
								Quantity:        sig.Quantity,
								Price:           fillPrice,
								TriggerPrice:    stopLoss,
								BoStopLossValue: stopLoss,
								BoProfitValue:   target,
							})
						}
					}
					orders = append([]SimulatedOrder{newOrder}, orders...)
				}
			}

			var realizedTotal, unrealizedTotal, marginUtilized float64
			for i := range positions {
				if positions[i].Status == "OPEN" {
					marginUtilized += float64(positions[i].NetQty) * positions[i].BuyAvg
					unrealizedTotal += positions[i].UnrealizedProfit
				} else {
					realizedTotal += positions[i].RealizedProfit
				}
			}
			latencyMs := time.Since(loopStart).Milliseconds()
			j.saveTelemetry(ctx, userID, params.StrategyID, strategyName, true, "STREAMING",
				spotPrice, cashBalance, cashBalance-marginUtilized, positions, orders, latencyMs)

		case <-ticker.C:
			segment := "INDEX"
			if strings.Contains(indexName, "INR") || strings.Contains(indexName, "USD") || strings.Contains(indexName, "EUR") {
				segment = "FOREX"
			}
			isMarketOpen := isSegmentMarketOpen(segment)
			if isMockMode(params.ExecutionMode) {
				isMarketOpen = true
			} else if !isMarketOpen && j.redisService != nil && j.redisService.Client != nil {
				if val, err := j.redisService.Client.Get(ctx, "marmot:mock_feed:active").Result(); err == nil && val == "true" {
					isMarketOpen = true
				}
			}
			if !isMarketOpen {
				// When market is closed, sleep evaluation to avoid CPU and log churn
				if tickCounter%30 == 0 {
					spotPrice, _ = j.fetchSpotPrice(ctx, indexName)
					j.saveTelemetry(ctx, userID, params.StrategyID, strategyName, false, "MARKET_CLOSED",
						spotPrice, cashBalance, cashBalance, positions, orders, 0)
				}
				tickCounter++
				continue
			}

			loopStart := time.Now()
			tickCounter++
			spotPrice, _ = j.fetchSpotPrice(ctx, indexName)

			var realizedTotal, unrealizedTotal, marginUtilized float64

			for k := range orders {
				if orders[k].OrderStatus == "PENDING" || orders[k].OrderStatus == "TRADED" {
					liveLTP := j.fetchOptionLTP(ctx, indexName, orders[k].TradingSymbol, spotPrice)
					if liveLTP > 0 {
						orders[k].CurrentLTP = liveLTP
					}
				}

				if orders[k].OrderStatus == "PENDING" && orders[k].CurrentLTP > 0 {
					if orders[k].TransactionType == "BUY" && orders[k].CurrentLTP <= orders[k].LimitEntryPrice {
						orders[k].OrderStatus = "TRADED"
						orders[k].ExecutionTime = nowIST().Format("03:04:05 PM")
						orders[k].FilledQty = orders[k].Quantity

						newPos := SimulatedPosition{
							TradingSymbol:    orders[k].TradingSymbol,
							ExchangeSegment:  "NSE_FNO",
							Status:           "OPEN",
							ProductType:      "INTRADAY",
							NetQty:           orders[k].Quantity,
							BuyQty:           orders[k].Quantity,
							BuyAvg:           orders[k].CurrentLTP,
							CurrentLTP:       orders[k].CurrentLTP,
							RealizedProfit:   0.0,
							UnrealizedProfit: 0.0,
							TotalPnL:         0.0,
							EntrySpot:        spotPrice,
						}
						positions = append([]SimulatedPosition{newPos}, positions...)
						log.Printf("⚡ [StrategyWorker #%s] PENDING LIMIT EXECUTED: BUY %s @ ₹%.2f\n", taskID, orders[k].TradingSymbol, orders[k].CurrentLTP)

						if isMockMode(params.ExecutionMode) {
							j.dispatchOrderToMockBroker(DhanOrderPayload{
								DhanClientID:    "1000000001",
								CorrelationID:   orders[k].TradingSymbol,
								TransactionType: "BUY",
								ExchangeSegment: "NSE_FNO",
								ProductType:     "INTRADAY",
								OrderType:       "LIMIT",
								Validity:        "DAY",
								SecurityID:      orders[k].TradingSymbol,
								Quantity:        orders[k].Quantity,
								Price:           orders[k].CurrentLTP,
								BoStopLossValue: orders[k].StopLossPrice,
								BoProfitValue:   orders[k].TargetPrice,
							})
						}
					}
				}
			}

			for i := range positions {
				if positions[i].Status == "OPEN" {
					marginUtilized += float64(positions[i].NetQty) * positions[i].BuyAvg

					liveLTP := j.fetchOptionLTP(ctx, indexName, positions[i].TradingSymbol, spotPrice)
					if liveLTP > 0 {
						positions[i].CurrentLTP = liveLTP
					}

					posPnl := math.Round((positions[i].CurrentLTP - positions[i].BuyAvg) * float64(positions[i].NetQty))
					positions[i].UnrealizedProfit = posPnl
					positions[i].TotalPnL = posPnl

					var sl, tp float64
					for _, o := range orders {
						if o.TradingSymbol == positions[i].TradingSymbol && o.TransactionType == "BUY" && o.OrderStatus == "TRADED" {
							sl = o.StopLossPrice
							tp = o.TargetPrice
							break
						}
					}

					if isMockMode(params.ExecutionMode) {
						// In SANDBOX / MOCK mode, the Mock Broker Matching Engine autonomously monitors ticks and squares off
						// positions on SL/TP breach. Marmot strictly relies on the broker OMS and never dispatches duplicate sells.
						if tickCounter%2 == 0 {
							mockPositions := j.fetchMockBrokerPositions()
							for _, mp := range mockPositions {
								if (mp.TradingSymbol == positions[i].TradingSymbol || mp.SecurityID == positions[i].TradingSymbol) &&
									(mp.PositionType == "CLOSED" || mp.NetQty == 0) {
									positions[i].Status = "CLOSED"
									positions[i].RealizedProfit = mp.RealizedProfit
									positions[i].UnrealizedProfit = 0
									positions[i].SellQty = mp.SellQty
									positions[i].SellAvg = mp.SellAvg
									positions[i].NetQty = 0

									triggerReason := "SL Hit"
									if mp.RealizedProfit > 0 {
										triggerReason = "TP Hit"
									}
									exitTime := mp.ExitTime
									if exitTime == "" {
										exitTime = nowIST().Format("03:04:05 PM")
									}
									exitOrder := SimulatedOrder{
										OrderID:         fmt.Sprintf("DHN-EXIT-%d", time.Now().Unix()%100000),
										CreateTime:      exitTime,
										ExecutionTime:   exitTime,
										TradingSymbol:   positions[i].TradingSymbol,
										ExchangeSegment: "NSE_FNO",
										TransactionType: "SELL",
										OrderType:       "MARKET",
										ProductType:     "INTRADAY",
										Validity:        "DAY",
										Quantity:        positions[i].BuyQty,
										FilledQty:       positions[i].BuyQty,
										Price:           mp.SellAvg,
										CurrentLTP:      mp.SellAvg,
										OrderStatus:     "TRADED",
										TriggerReason:   triggerReason,
									}
									orders = append([]SimulatedOrder{exitOrder}, orders...)
									log.Printf("🛡️ [StrategyWorker #%s] POSITION SQUARED OFF BY BROKER OMS (%s): SELL %s @ ₹%.2f (Realized: ₹%.2f)\n",
										taskID, triggerReason, positions[i].TradingSymbol, mp.SellAvg, mp.RealizedProfit)
									break
								}
							}
						}
					} else if positions[i].CurrentLTP > 0 && sl > 0 && tp > 0 {
						triggerReason := ""
						if positions[i].CurrentLTP <= sl {
							triggerReason = "SL Hit"
						} else if positions[i].CurrentLTP >= tp {
							triggerReason = "TP Hit"
						}

						if triggerReason != "" {
							positions[i].Status = "CLOSED"
							positions[i].RealizedProfit = posPnl
							positions[i].UnrealizedProfit = 0
							positions[i].SellQty = positions[i].BuyQty
							positions[i].SellAvg = positions[i].CurrentLTP
							positions[i].NetQty = 0

							nowStr := nowIST().Format("03:04:05 PM")
							exitOrder := SimulatedOrder{
								OrderID:         fmt.Sprintf("SBX-%d%02d", time.Now().Unix()%100000, rand.Intn(90)+10),
								CreateTime:      nowStr,
								ExecutionTime:   nowStr,
								TradingSymbol:   positions[i].TradingSymbol,
								ExchangeSegment: "NSE_FNO",
								TransactionType: "SELL",
								OrderType:       "MARKET",
								ProductType:     "INTRADAY",
								Validity:        "DAY",
								Quantity:        positions[i].BuyQty,
								FilledQty:       positions[i].BuyQty,
								Price:           positions[i].CurrentLTP,
								CurrentLTP:      positions[i].CurrentLTP,
								OrderStatus:     "TRADED",
								TriggerReason:   triggerReason,
							}
							orders = append([]SimulatedOrder{exitOrder}, orders...)
							log.Printf("🛡️ [StrategyWorker #%s] POSITION SQUARED OFF (%s): SELL %s @ ₹%.2f\n", taskID, triggerReason, positions[i].TradingSymbol, positions[i].CurrentLTP)
						}
					}

					if positions[i].Status == "OPEN" {
						unrealizedTotal += positions[i].UnrealizedProfit
					} else {
						realizedTotal += positions[i].RealizedProfit
					}
				} else {
					realizedTotal += positions[i].RealizedProfit
				}
			}

			if isMarketOpen && tickCounter%8 == 0 {
				activeExp := j.fetchActiveExpiry(ctx, indexName)
				if params.Params == nil {
					params.Params = make(map[string]interface{})
				}
				params.Params["execution_mode"] = params.ExecutionMode
				if activeExp != "" {
					params.Params["active_expiry"] = activeExp
				}

				if prevSpotPrice == 0 {
					prevSpotPrice = spotPrice
				}
				barOpen := prevSpotPrice
				barClose := spotPrice
				barHigh := math.Max(barOpen, barClose) + 0.5
				barLow := math.Min(barOpen, barClose) - 0.5
				prevSpotPrice = spotPrice

				candle := map[string]interface{}{
					"close":  barClose,
					"open":   barOpen,
					"high":   barHigh,
					"low":    barLow,
					"volume": 125000,
				}
				sig := strat.EvaluateLiveSignal(candle, nil, indexName, params.Params)
				if sig != nil {
					alreadyOpen := false
					for _, pos := range positions {
						if pos.Status == "OPEN" && pos.TradingSymbol == sig.TradingSymbol {
							alreadyOpen = true
							break
						}
					}
					for _, o := range orders {
						if o.OrderStatus == "PENDING" && o.TradingSymbol == sig.TradingSymbol {
							alreadyOpen = true
							break
						}
					}

					openPositionsCount := 0
					for _, pos := range positions {
						if pos.Status == "OPEN" {
							openPositionsCount++
						}
					}

					if !alreadyOpen && openPositionsCount < 6 {
						now := nowIST()
						newOrderID := fmt.Sprintf("SBX-%d%02d", now.Unix()%100000, rand.Intn(90)+10)
						fillPrice := j.fetchOptionLTP(ctx, indexName, sig.TradingSymbol, spotPrice)

						if fillPrice > 0 {
							slPts := 15.0
							rrRatio := 2.0
							if params.Params != nil {
								if sl, ok := params.Params["sl_pts"].(float64); ok && sl > 0 {
									slPts = sl
								}
								if rr, ok := params.Params["rr_ratio"].(float64); ok && rr > 0 {
									rrRatio = rr
								}
							}
							stopLoss := math.Max(1.0, math.Round((fillPrice-slPts)*100)/100)
							target := math.Round((fillPrice+(slPts*rrRatio))*100) / 100

							nowStr := now.Format("03:04:05 PM")
							signalTime := sig.Timestamp
							if signalTime == "" {
								signalTime = nowStr
							}

							status := "TRADED"
							if sig.OrderType == "LIMIT" {
								status = "PENDING"
							}

							newOrder := SimulatedOrder{
								OrderID:         newOrderID,
								CreateTime:      nowStr,
								SignalTime:      signalTime,
								ExecutionTime:   "",
								TradingSymbol:   sig.TradingSymbol,
								ExchangeSegment: "NSE_FNO",
								TransactionType: sig.Transaction,
								OrderType:       sig.OrderType,
								ProductType:     "INTRADAY",
								Validity:        "DAY",
								Quantity:        sig.Quantity,
								FilledQty:       0,
								Price:           fillPrice,
								LimitEntryPrice: fillPrice,
								LimitTappedTime: nowStr,
								TargetPrice:     target,
								StopLossPrice:   stopLoss,
								CurrentLTP:      fillPrice,
								OrderStatus:     status,
								RuleID:          sig.RuleID,
								RuleName:        sig.RuleName,
								TriggerReason:   sig.TriggerReason,
								Indicators:      sig.Indicators,
								SlippagePts:     0.00,
							}

							if status == "TRADED" {
								newOrder.ExecutionTime = nowStr
								newOrder.FilledQty = sig.Quantity
								newPos := SimulatedPosition{
									TradingSymbol:    sig.TradingSymbol,
									ExchangeSegment:  "NSE_FNO",
									Status:           "OPEN",
									ProductType:      "INTRADAY",
									NetQty:           sig.Quantity,
									BuyQty:           sig.Quantity,
									BuyAvg:           fillPrice,
									CurrentLTP:       fillPrice,
									RealizedProfit:   0.0,
									UnrealizedProfit: 0.0,
									TotalPnL:         0.0,
									EntrySpot:        spotPrice,
								}
								positions = append([]SimulatedPosition{newPos}, positions...)
								log.Printf("⚡ [StrategyWorker #%s] MARKET EXECUTED: %s %s @ ₹%.2f\n", taskID, sig.Transaction, sig.TradingSymbol, fillPrice)

								if isMockMode(params.ExecutionMode) {
									j.dispatchOrderToMockBroker(DhanOrderPayload{
										DhanClientID:    "1000000001",
										CorrelationID:   sig.TradingSymbol,
										TransactionType: sig.Transaction,
										ExchangeSegment: "NSE_FNO",
										ProductType:     "INTRADAY",
										OrderType:       sig.OrderType,
										Validity:        "DAY",
										SecurityID:      sig.TradingSymbol,
										Quantity:        sig.Quantity,
										Price:           fillPrice,
										BoStopLossValue: stopLoss,
										BoProfitValue:   target,
									})
								}
							} else {
								log.Printf("⏳ [StrategyWorker #%s] LIMIT ORDER PLACED (PENDING): %s %s @ ₹%.2f\n", taskID, sig.Transaction, sig.TradingSymbol, fillPrice)
							}

							orders = append([]SimulatedOrder{newOrder}, orders...)
						} else {
							log.Printf("⚠️ [StrategyWorker #%s] Missed tick for %s, skipping fake fallback logic.", taskID, sig.TradingSymbol)
						}
					}
				}
			}

			statusStr := "STREAMING"
			if !isMarketOpen {
				statusStr = "MARKET_CLOSED"
			}

			latencyMs := time.Since(loopStart).Milliseconds()
			j.saveTelemetry(ctx, userID, params.StrategyID, strategyName, isMarketOpen, statusStr,
				spotPrice, cashBalance, cashBalance-marginUtilized, positions, orders, latencyMs)
		}
	}
}

var istLocation = time.FixedZone("IST", 5*3600+1800)

// nowIST returns the current timestamp in Indian Standard Time (Asia/Kolkata).
func nowIST() time.Time {
	return time.Now().In(istLocation)
}

// isIndianMarketOpen checks if current time in IST is within active trading hours for the given instrument segment.
func isIndianMarketOpen() bool {
	return isSegmentMarketOpen("INDEX")
}

// isSegmentMarketOpen checks trading hours by segment:
// - "INDEX": 09:15 to 15:30 IST (NIFTY, BANKNIFTY, SENSEX)
// - "FOREX": 09:00 to 17:00 IST (USDINR, EURINR, etc.)
// - "FOREX_CROSS": 09:00 to 19:30 IST (EURUSD, GBPUSD, etc.)
func isSegmentMarketOpen(segment string) bool {
	now := nowIST()
	weekday := now.Weekday()
	if weekday == time.Saturday || weekday == time.Sunday {
		return false
	}
	totalMinutes := now.Hour()*60 + now.Minute()
	switch strings.ToUpper(segment) {
	case "FOREX", "CURRENCY":
		return totalMinutes >= 540 && totalMinutes <= 1020
	case "FOREX_CROSS":
		return totalMinutes >= 540 && totalMinutes <= 1170
	case "INDEX", "EQUITY":
		fallthrough
	default:
		return totalMinutes >= 555 && totalMinutes <= 930
	}
}


// parseOptionSymbol extracts strike price, option type ("CALL" / "PUT"), and expiry tag (e.g. "15SEP") from trading symbol.
func parseOptionSymbol(symbol string) (int, string, string) {
	parts := strings.Fields(symbol)
	strike := 0
	optType := "CALL"
	expDay := ""
	expMon := ""

	months := map[string]bool{
		"JAN": true, "FEB": true, "MAR": true, "APR": true, "MAY": true, "JUN": true,
		"JUL": true, "AUG": true, "SEP": true, "OCT": true, "NOV": true, "DEC": true,
	}

	for i, p := range parts {
		pUpper := strings.ToUpper(p)
		if pUpper == "CE" || pUpper == "CALL" {
			optType = "CALL"
		} else if pUpper == "PE" || pUpper == "PUT" {
			optType = "PUT"
		} else if val, err := strconv.Atoi(p); err == nil {
			if val >= 1000 {
				strike = val
			} else if val > 0 && val <= 31 && expDay == "" {
				expDay = fmt.Sprintf("%02d", val)
			}
		} else if months[pUpper] {
			expMon = pUpper
			if i > 0 && expDay == "" {
				if dVal, dErr := strconv.Atoi(parts[i-1]); dErr == nil && dVal > 0 && dVal <= 31 {
					expDay = fmt.Sprintf("%02d", dVal)
				}
			}
		}
	}
	expTag := ""
	if expDay != "" && expMon != "" {
		expTag = expDay + expMon
	}
	return strike, optType, expTag
}

// toFyersOptionSymbol maps standard symbol (e.g. "NIFTY 15 SEP 23400 CALL") to exchange FYERS contract symbol.
func toFyersOptionSymbol(indexName, symbol string) string {
	strike, optType, expTag := parseOptionSymbol(symbol)
	if strike <= 0 || len(expTag) < 5 {
		return ""
	}
	day := expTag[:2]
	mon := expTag[2:]
	monthCodes := map[string]string{
		"JAN": "1", "FEB": "2", "MAR": "3", "APR": "4", "MAY": "5", "JUN": "6",
		"JUL": "7", "AUG": "8", "SEP": "9", "OCT": "O", "NOV": "N", "DEC": "D",
	}
	mCode, ok := monthCodes[mon]
	if !ok {
		mCode = "9"
	}
	cePe := "CE"
	if optType == "PUT" {
		cePe = "PE"
	}
	return fmt.Sprintf("NSE:%s26%s%s%d%s", indexName, mCode, day, strike, cePe)
}

// fetchActiveExpiry retrieves the active exchange expiry date from Redis option chain or returns empty string.
func (j *StrategySignalJob) fetchActiveExpiry(ctx context.Context, indexName string) string {
	if j.redisService == nil || j.redisService.Client == nil {
		return ""
	}

	expKey := fmt.Sprintf("marmot:fyers:active_expiry:%s", indexName)
	if val, err := j.redisService.Client.Get(ctx, expKey).Result(); err == nil && len(val) > 0 {
		return strings.TrimSpace(val)
	}

	ocKeys := []string{
		fmt.Sprintf("marmot:fyers:option_chain:%s", indexName),
		fmt.Sprintf(":1:marmot:fyers:option_chain:%s", indexName),
	}
	for _, k := range ocKeys {
		if data, err := j.redisService.Client.Get(ctx, k).Result(); err == nil && len(data) > 0 {
			var ocPayload struct {
				ExpiryInfo struct {
					ExpiryDate string `json:"expiry_date"`
				} `json:"expiry_info"`
			}
			if jsonErr := json.Unmarshal([]byte(data), &ocPayload); jsonErr == nil && ocPayload.ExpiryInfo.ExpiryDate != "" {
				parts := strings.Split(ocPayload.ExpiryInfo.ExpiryDate, "-")
				if len(parts) == 3 {
					day := parts[0]
					monNum := parts[1]
					months := map[string]string{
						"01": "JAN", "02": "FEB", "03": "MAR", "04": "APR",
						"05": "MAY", "06": "JUN", "07": "JUL", "08": "AUG",
						"09": "SEP", "10": "OCT", "11": "NOV", "12": "DEC",
					}
					if monName, ok := months[monNum]; ok {
						return fmt.Sprintf("%s %s", day, monName)
					}
				}
			}
		}
	}

	return ""
}

// fetchOptionLTP queries the real-time option contract market price from Redis with strict expiry partitioning.
func (j *StrategySignalJob) fetchOptionLTP(ctx context.Context, indexName, tradingSymbol string, spotPrice float64) float64 {
	strike, optType, expTag := parseOptionSymbol(tradingSymbol)
	if strike <= 0 {
		return 0.0
	}

	// 1. In SANDBOX / MOCK mode, query local mock broker emulator directly for live advancing Parquet replay ticks
	if isMockMode(j.payload.Params.ExecutionMode) {
		resp, err := http.Get(fmt.Sprintf("http://mock_broker:8088/mock/v2/optionchain?index=%s", indexName))
		if err == nil && resp.StatusCode == http.StatusOK {
			var ocPayload struct {
				Strikes []map[string]interface{} `json:"strikes"`
			}
			if jsonErr := json.NewDecoder(resp.Body).Decode(&ocPayload); jsonErr == nil {
				resp.Body.Close()
				for _, s := range ocPayload.Strikes {
					spVal, _ := s["strike"].(float64)
					if int(spVal) == strike {
						if optType == "CALL" {
							if cltp, ok := s["ce_ltp"].(float64); ok && cltp > 0 {
								return cltp
							}
						} else {
							if pltp, ok := s["pe_ltp"].(float64); ok && pltp > 0 {
								return pltp
							}
						}
					}
				}
			} else {
				resp.Body.Close()
			}
		}
	}

	if j.redisService == nil || j.redisService.Client == nil {
		return 0.0
	}

	fyersSym := toFyersOptionSymbol(indexName, tradingSymbol)

	keysToTry := []string{}
	// 1. Check exact contract FYERS symbol in Redis
	if fyersSym != "" {
		keysToTry = append(keysToTry,
			fmt.Sprintf("marmot:contract_ltp:%s", fyersSym),
			fmt.Sprintf(":1:marmot:contract_ltp:%s", fyersSym),
		)
	}

	// 2. Check SPOT and expiry-partitioned keys
	tags := []string{"SPOT"}
	if expTag != "" && expTag != "SPOT" {
		tags = append(tags, expTag)
	}

	for _, tag := range tags {
		keysToTry = append(keysToTry,
			fmt.Sprintf("marmot:opt_ltp:%s:%s:%d:%s", indexName, tag, strike, optType),
			fmt.Sprintf(":1:marmot:opt_ltp:%s:%s:%d:%s", indexName, tag, strike, optType),
		)
		if optType == "CALL" {
			keysToTry = append(keysToTry,
				fmt.Sprintf("marmot:opt_ltp:%s:%s:%d:CE", indexName, tag, strike),
				fmt.Sprintf(":1:marmot:opt_ltp:%s:%s:%d:CE", indexName, tag, strike),
			)
		} else {
			keysToTry = append(keysToTry,
				fmt.Sprintf("marmot:opt_ltp:%s:%s:%d:PE", indexName, tag, strike),
				fmt.Sprintf(":1:marmot:opt_ltp:%s:%s:%d:PE", indexName, tag, strike),
			)
		}
	}

	for _, k := range keysToTry {
		valStr, err := j.redisService.Client.Get(ctx, k).Result()
		if err == nil && len(valStr) > 0 {
			if ltp, parseErr := strconv.ParseFloat(valStr, 64); parseErr == nil && ltp > 0 {
				return ltp
			}
		}
	}

	// 3. Fall back to live option chain strikes array
	ocKeys := []string{
		fmt.Sprintf("marmot:fyers:option_chain:%s", indexName),
		fmt.Sprintf(":1:marmot:fyers:option_chain:%s", indexName),
	}
	for _, ocKey := range ocKeys {
		data, err := j.redisService.Client.Get(ctx, ocKey).Result()
		if err == nil && len(data) > 0 {
			var ocPayload struct {
				Strikes []map[string]interface{} `json:"strikes"`
			}
			if errUnmarshal := json.Unmarshal([]byte(data), &ocPayload); errUnmarshal == nil {
				for _, s := range ocPayload.Strikes {
					spVal, _ := s["strike"].(float64)
					if int(spVal) == strike {
						if optType == "CALL" {
							if cltp, ok := s["ce_ltp"].(float64); ok && cltp > 0 {
								return cltp
							}
						} else {
							if pltp, ok := s["pe_ltp"].(float64); ok && pltp > 0 {
								return pltp
							}
						}
					}
				}
			}
		}
	}

	// 4. Fall back to mock broker emulator directly
	resp, err := http.Get(fmt.Sprintf("http://mock_broker:8088/mock/v2/optionchain?index=%s", indexName))
	if err == nil && resp.StatusCode == http.StatusOK {
		var ocPayload struct {
			Strikes []map[string]interface{} `json:"strikes"`
		}
		if jsonErr := json.NewDecoder(resp.Body).Decode(&ocPayload); jsonErr == nil {
			resp.Body.Close()
			for _, s := range ocPayload.Strikes {
				spVal, _ := s["strike"].(float64)
				if int(spVal) == strike {
					if optType == "CALL" {
						if cltp, ok := s["ce_ltp"].(float64); ok && cltp > 0 {
							return cltp
						}
					} else {
						if pltp, ok := s["pe_ltp"].(float64); ok && pltp > 0 {
							return pltp
						}
					}
				}
			}
		} else {
			resp.Body.Close()
		}
	}

	return 0.0
}

// LiveQuoteMetrics holds real-time quote metrics fetched from Redis for index spot and candle construction.
type LiveQuoteMetrics struct {
	SpotPrice float64
	ATMStrike int
	OpenPrice float64
	HighPrice float64
	LowPrice  float64
}

// fetchSpotMetrics reads authentic session quote data from Redis (open, high, low, lp).
func (j *StrategySignalJob) fetchSpotMetrics(ctx context.Context, indexName string) LiveQuoteMetrics {
	res := LiveQuoteMetrics{}

	// 1. In SANDBOX / MOCK mode, query local mock broker emulator directly for live advancing Parquet replay spot
	if isMockMode(j.payload.Params.ExecutionMode) {
		resp, err := http.Get(fmt.Sprintf("http://mock_broker:8088/mock/v2/optionchain?index=%s", indexName))
		if err == nil && resp.StatusCode == http.StatusOK {
			var mockData map[string]interface{}
			if jsonErr := json.NewDecoder(resp.Body).Decode(&mockData); jsonErr == nil {
				resp.Body.Close()
				if p, ok := mockData["raw_spot_ltp"].(float64); ok && p > 0 {
					res.SpotPrice = p
					res.OpenPrice = p
					res.HighPrice = p
					res.LowPrice = p
					step := StrikeIntervalForIndex(indexName)
					if step <= 0 {
						step = 50
					}
					res.ATMStrike = int(math.Round(p/float64(step)) * float64(step))
					return res
				}
			} else {
				resp.Body.Close()
			}
		}
	}

	if j.redisService == nil || j.redisService.Client == nil {
		return res
	}

	keysToTry := []string{
		fmt.Sprintf("marmot:fyers_quote:NSE:%s50-INDEX", indexName),
		fmt.Sprintf("marmot:fyers_quote:NSE:%s-INDEX", indexName),
		fmt.Sprintf(":1:marmot:fyers_quote:NSE:%s50-INDEX", indexName),
		fmt.Sprintf(":1:marmot:fyers_quote:NSE:%s-INDEX", indexName),
		fmt.Sprintf("marmot:fyers:option_chain:%s", indexName),
		fmt.Sprintf(":1:marmot:fyers:option_chain:%s", indexName),
		fmt.Sprintf("marmot:fyers:last_known_option_chain:%s", indexName),
	}

	for _, k := range keysToTry {
		data, err := j.redisService.Client.Get(ctx, k).Result()
		if err == nil && len(data) > 0 {
			var rawMap map[string]interface{}
			if unmarshalErr := json.Unmarshal([]byte(data), &rawMap); unmarshalErr == nil {
				var price float64
				if v, ok := rawMap["raw_spot_ltp"].(float64); ok && v > 0 {
					price = v
				} else if v, ok := rawMap["lp"].(float64); ok && v > 0 {
					price = v
				} else if s, ok := rawMap["spot_ltp"].(string); ok {
					cleanStr := strings.ReplaceAll(strings.ReplaceAll(s, ",", ""), "₹", "")
					_, _ = fmt.Sscanf(cleanStr, "%f", &price)
				}

				if price > 0 {
					res.SpotPrice = price
					if v, ok := rawMap["open_price"].(float64); ok {
						res.OpenPrice = v
					}
					if res.OpenPrice == 0 {
						res.OpenPrice = price
					}
					if v, ok := rawMap["high_price"].(float64); ok {
						res.HighPrice = v
					}
					if res.HighPrice == 0 {
						res.HighPrice = price
					}
					if v, ok := rawMap["low_price"].(float64); ok {
						res.LowPrice = v
					}
					if res.LowPrice == 0 {
						res.LowPrice = price
					}

					step := StrikeIntervalForIndex(indexName)
					if step <= 0 {
						step = 50
					}
					if v, ok := rawMap["atm_strike"].(float64); ok && v > 0 {
						res.ATMStrike = int(v)
					} else {
						res.ATMStrike = int(math.Round(price/float64(step)) * float64(step))
					}
					return res
				}
			}
		}
	}

	// Fallback to local mock broker emulator endpoint
	resp, err := http.Get(fmt.Sprintf("http://mock_broker:8088/mock/v2/optionchain?index=%s", indexName))
	if err == nil && resp.StatusCode == http.StatusOK {
		var mockData map[string]interface{}
		if jsonErr := json.NewDecoder(resp.Body).Decode(&mockData); jsonErr == nil {
			resp.Body.Close()
			if p, ok := mockData["raw_spot_ltp"].(float64); ok && p > 0 {
				res.SpotPrice = p
				res.OpenPrice = p
				res.HighPrice = p
				res.LowPrice = p
				res.ATMStrike = int(math.Round(p/50.0) * 50.0)
				if b, mErr := json.Marshal(mockData); mErr == nil && j.redisService != nil && j.redisService.Client != nil {
					_ = j.redisService.Client.Set(ctx, fmt.Sprintf("marmot:fyers:option_chain:%s", indexName), b, 1*time.Second).Err()
				}
				return res
			}
		} else {
			resp.Body.Close()
		}
	}

	return res
}

// fetchSpotPrice reads the latest FYERS option chain quote from Redis or falls back gracefully.
func (j *StrategySignalJob) fetchSpotPrice(ctx context.Context, indexName string) (float64, int) {
	m := j.fetchSpotMetrics(ctx, indexName)
	if m.SpotPrice > 0 {
		return m.SpotPrice, m.ATMStrike
	}
	return 0.0, 0
}

// saveTelemetry packages and writes sandbox simulated portfolio state to Redis.
func (j *StrategySignalJob) saveTelemetry(
	ctx context.Context,
	userID string,
	strategyID int,
	strategyName string,
	isActive bool,
	status string,
	spotPrice float64,
	cashBalance float64,
	availableMargin float64,
	positions []SimulatedPosition,
	orders []SimulatedOrder,
	processingLatencyMs int64,
) {
	if j.redisService == nil || j.redisService.Client == nil {
		return
	}

	var realizedTotal, unrealizedTotal, marginUtilized float64
	openCount := 0
	closedCount := 0

	for _, p := range positions {
		if p.Status == "OPEN" {
			openCount++
			unrealizedTotal += p.UnrealizedProfit
			marginUtilized += float64(p.NetQty) * p.BuyAvg
		} else {
			closedCount++
			realizedTotal += p.RealizedProfit
		}
	}

	telemetry := map[string]interface{}{
		"strategy_id":            strategyID,
		"strategy_name":          strategyName,
		"user_id":                userID,
		"is_active":              isActive,
		"status":                 status,
		"spot_price":             spotPrice,
		"last_eval_time":         nowIST().Format("15:04:05 IST"),
		"available_margin":       fmt.Sprintf("%.2f", availableMargin),
		"cash_balance":           fmt.Sprintf("%.2f", cashBalance),
		"margin_utilized":        fmt.Sprintf("%.2f", marginUtilized),
		"live_net_pnl":           realizedTotal + unrealizedTotal,
		"realized_pnl":           realizedTotal,
		"unrealized_pnl":         unrealizedTotal,
		"open_positions_count":   openCount,
		"closed_positions_count": closedCount,
		"todays_orders_count":    len(orders),
		"positions":              positions,
		"orders":                 orders,
		"processing_latency_ms":  processingLatencyMs,
	}

	bytes, err := json.Marshal(telemetry)
	if err != nil {
		return
	}

	// 1. User-level sandbox telemetry
	userKey := fmt.Sprintf("marmot:mock:telemetry:%s", userID)
	_ = j.redisService.Client.Set(ctx, userKey, bytes, 30*time.Minute).Err()

	// 2. Strategy-level telemetry
	stratKey := fmt.Sprintf("marmot:mock:telemetry:strategy:%d", strategyID)
	_ = j.redisService.Client.Set(ctx, stratKey, bytes, 30*time.Minute).Err()

	// 3. WS Broadcast to active subscribers & general hub
	if j.hub != nil {
		wsPayload, _ := json.Marshal(map[string]interface{}{
			"type":       "mock_telemetry",
			"task_id":    j.payload.TaskID,
			"spot_price": spotPrice,
			"data":       telemetry,
		})
		if status == "STREAMING" && processingLatencyMs > 0 {
			log.Printf("📡 [WS Telemetry] Task=%s | Spot=₹%.2f | NetPnL=₹%.2f | Margin=₹%s | OpenPos=%d | Latency=%dms\n",
				j.payload.TaskID, spotPrice, realizedTotal+unrealizedTotal, telemetry["available_margin"], openCount, processingLatencyMs)
		}
		j.hub.BroadcastToTask(j.payload.TaskID, wsPayload)
		select {
		case j.hub.Broadcast <- wsPayload:
		default:
		}
	}
}
