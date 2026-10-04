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
	TradingSymbol   string  `json:"tradingSymbol,omitempty"`
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
	LegName         string  `json:"legName,omitempty"`
	LogicalTimestamp string `json:"logical_timestamp,omitempty"`
}

// deriveCanonicalOptionID extracts the canonical strike ID (e.g. 21700_PE) from arbitrary option symbols.
func deriveCanonicalOptionID(symbol string) string {
	upper := strings.ToUpper(symbol)
	optType := "CE"
	if strings.Contains(upper, "PUT") || strings.Contains(upper, "_PE") || strings.Contains(upper, " PE") {
		optType = "PE"
	}
	var digits []rune
	for _, r := range upper {
		if r >= '0' && r <= '9' {
			digits = append(digits, r)
		} else {
			if len(digits) >= 4 {
				break
			}
			digits = digits[:0]
		}
	}
	if len(digits) >= 4 {
		return fmt.Sprintf("%s_%s", string(digits), optType)
	}
	return symbol
}

// isMockMode returns true if the execution mode corresponds to paper trading, sandbox, or simulation.
func isMockMode(mode string) bool {
	return strings.EqualFold(mode, "MOCK") || strings.EqualFold(mode, "LIVE") || strings.EqualFold(mode, "SANDBOX")
}

// isRealLiveMode returns true if the execution mode corresponds to real-money production broker execution.
func isRealLiveMode(mode string) bool {
	return strings.EqualFold(mode, "REAL_LIVE") || strings.EqualFold(mode, "PRODUCTION")
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

// getDhanLiveCredentials dynamically resolves active Dhan Client ID and access token from Redis cache.
func (j *StrategySignalJob) getDhanLiveCredentials(ctx context.Context) (string, string) {
	keys, err := j.redisService.Client.Keys(ctx, "dhan_token:*").Result()
	if err == nil && len(keys) > 0 {
		for _, k := range keys {
			parts := strings.Split(k, ":")
			if len(parts) == 2 && parts[1] != "" {
				token, err := j.redisService.Client.Get(ctx, k).Result()
				if err == nil && token != "" {
					return parts[1], token
				}
			}
		}
	}
	if token, err := j.redisService.Client.Get(ctx, "marmot:dhan:active_token").Result(); err == nil && token != "" {
		cid, _ := j.redisService.Client.Get(ctx, "marmot:dhan:active_client_id").Result()
		if cid != "" {
			return cid, token
		}
	}
	return "", ""
}

// dispatchOrderToDhanLive dispatches a direct, ultra-low latency REST order to Dhan HQ Production API.
func (j *StrategySignalJob) dispatchOrderToDhanLive(ctx context.Context, req DhanOrderPayload, clientID string) {
	go func() {
		cid, token := j.getDhanLiveCredentials(ctx)
		if clientID != "" {
			cid = clientID
		}
		if cid == "" || token == "" {
			log.Printf("⚠️ [StrategyWorker Direct Live] Execution Skipped: Active Dhan live token not found in Redis")
			return
		}

		req.DhanClientID = cid
		bodyBytes, err := json.Marshal(req)
		if err != nil {
			log.Printf("⚠️ [StrategyWorker Direct Live] Failed to marshal Dhan live order payload: %v", err)
			return
		}

		httpReq, err := http.NewRequestWithContext(ctx, "POST", "https://api.dhan.co/v2/orders", bytes.NewBuffer(bodyBytes))
		if err != nil {
			log.Printf("⚠️ [StrategyWorker Direct Live] Failed to create Dhan live order request: %v", err)
			return
		}

		httpReq.Header.Set("Content-Type", "application/json")
		httpReq.Header.Set("access-token", token)
		httpReq.Header.Set("client-id", cid)

		client := &http.Client{Timeout: 5 * time.Second}
		startTime := time.Now()
		resp, err := client.Do(httpReq)
		latency := time.Since(startTime).Milliseconds()

		if err != nil {
			log.Printf("⚠️ [StrategyWorker Direct Live] Dhan Live Order API network error (%dms): %v", latency, err)
			return
		}
		defer resp.Body.Close()

		log.Printf("⚡ [StrategyWorker Direct Live Dispatch] Order executed via Dhan API (Acc: %s | %s %s x %d | Latency: %dms) -> HTTP %d",
			cid, req.TransactionType, req.TradingSymbol, req.Quantity, latency, resp.StatusCode)

		eventPayload, _ := json.Marshal(map[string]interface{}{
			"type":         "order_update",
			"broker":       "DHAN",
			"order_id":     req.CorrelationID,
			"status":       "TRADED",
			"execution_ms": latency,
		})
		_ = j.redisService.Client.Publish(ctx, "marmot:orders", eventPayload).Err()
	}()
}

// dispatchOrderToMockBroker sends a synchronous order request to the Dhan mock broker via Redis.
func (j *StrategySignalJob) dispatchOrderToMockBroker(ctx context.Context, req DhanOrderPayload) {
	if req.DhanClientID == "" || req.DhanClientID == "1000000001" {
		req.DhanClientID = j.getActiveMockAccountID()
	}
	bodyBytes, err := json.Marshal(req)
	if err != nil {
		log.Printf("⚠️ [StrategyWorker] Failed to marshal mock broker order payload: %v", err)
		return
	}

	err = j.redisService.Client.XAdd(ctx, &redis.XAddArgs{
		Stream: "marmot:mock:orders",
		Values: map[string]interface{}{
			"payload":           string(bodyBytes),
			"logical_timestamp": req.LogicalTimestamp,
		},
	}).Err()

	if err != nil {
		log.Printf("⚠️ [StrategyWorker] Mock Broker Redis Order API dispatch failed: %v", err)
		return
	}
	log.Printf("📤 [StrategyWorker] Order dispatched to Mock Broker via Redis (Acc: %s | %s %s x %d)",
		req.DhanClientID, req.TransactionType, req.SecurityID, req.Quantity)
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
	dbService            *services.DBService
	config               *config.Config
	payload              models.CommandPayload
	hub                  *ws.Hub
	redisService         *services.RedisService
	lastTelemetryLogTime time.Time
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
	TradeDuration   string                 `json:"trade_duration,omitempty"`
	LimitEntryPrice float64                `json:"limit_entry_price,omitempty"`
	LimitTappedTime string                 `json:"limit_tapped_time,omitempty"`
	TargetPrice          float64                `json:"target_price,omitempty"`
	StopLossPrice        float64                `json:"stop_loss_price,omitempty"`
	InitialTargetPrice   float64                `json:"initial_target_price,omitempty"`
	InitialStopLossPrice float64                `json:"initial_stop_loss_price,omitempty"`
	TrailingStage        int                    `json:"trailing_stage,omitempty"`
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
	stratParams := strategies.GetStrategyPreset(strategyName)

	log.Printf("🚀 [StrategyWorker #%s] Autonomous Signal Loop started for %s (%s) [User #%s]\n",
		taskID, strategyName, indexName, userID)

	ticker := time.NewTicker(1000 * time.Millisecond)
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
	var latestLogicalTime time.Time
	latestLogicalTime = nowIST()

	var candleSub *redis.PubSub
	var candleChan <-chan *redis.Message
	if j.redisService != nil && j.redisService.Client != nil {
		candleSub = j.redisService.Client.Subscribe(ctx, "marmot:streamer:candles")
		candleChan = candleSub.Channel()
		defer candleSub.Close()
	}

	liveTickChan := ws.SubscribeLiveTicks(indexName)
	defer ws.UnsubscribeLiveTicks(indexName, liveTickChan)

	for {
		select {
		case <-ctx.Done():
			log.Printf("⏸️ [StrategyWorker #%s] Pausing Autonomous Signal Loop for User #%s\n", taskID, userID)
			j.saveTelemetry(context.Background(), userID, params.StrategyID, strategyName, false, "PAUSED",
				23760.0, cashBalance, cashBalance, positions, orders, 0)
			return

		case tick, ok := <-liveTickChan:
			if ok && tick.SpotPrice > 0 {
				spotPrice = tick.SpotPrice
			}

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
			if dtStr, ok := cData["datetime"].(string); ok && len(dtStr) >= 19 {
				parsed, err := time.Parse("2006-01-02 15:04:05", dtStr[:19])
				if err == nil {
					latestLogicalTime = parsed
				}
			}
			
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
							if (mp.TradingSymbol == positions[i].TradingSymbol || mp.SecurityID == positions[i].TradingSymbol || mp.SecurityID == deriveCanonicalOptionID(positions[i].TradingSymbol)) &&
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
									exitTime = latestLogicalTime.Format("15:04:05")
								}
								
								// Calculate trade duration
								durationStr := ""
								for _, o := range orders {
									if o.TradingSymbol == positions[i].TradingSymbol && o.TransactionType == "BUY" && o.OrderStatus == "TRADED" {
										entryTime, err := time.Parse("15:04:05", o.ExecutionTime)
										if err != nil {
											entryTime, err = time.Parse("03:04:05 PM", o.ExecutionTime)
										}
										exitTimeParsed, err2 := time.Parse("15:04:05", exitTime)
										if err2 != nil {
											exitTimeParsed, err2 = time.Parse("03:04:05 PM", exitTime)
										}
										if err == nil && err2 == nil {
											diff := exitTimeParsed.Sub(entryTime)
											if diff < 0 {
												diff = -diff
											}
											if diff.Hours() >= 1 {
												durationStr = fmt.Sprintf("%dh %dm %ds", int(diff.Hours()), int(diff.Minutes())%60, int(diff.Seconds())%60)
											} else {
												durationStr = fmt.Sprintf("%dm %ds", int(diff.Minutes()), int(diff.Seconds())%60)
											}
										}
										break
									}
								}

								exitOrder := SimulatedOrder{
									OrderID:         fmt.Sprintf("DHN-EXIT-%d", time.Now().Unix()%100000),
									CreateTime:      exitTime,
									ExecutionTime:   exitTime,
									TradeDuration:   durationStr,
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

			// Inject live option chain so the strike sweep scorer can find the best entry strike.
			if optChain := j.fetchOptionChainSnaps(ctx, indexName); len(optChain) > 0 {
				params.Params["option_chain"] = optChain
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
					// Use scored sweep limit price if provided; fall back to live LTP fetch.
					fillPrice := sig.LimitPrice
					if fillPrice <= 0 || fillPrice > 2000 {
						fillPrice = j.fetchOptionLTP(ctx, indexName, sig.TradingSymbol, spotPrice)
					}
					if fillPrice <= 0 || fillPrice > 2000 {
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
					stopLoss := sig.StopLossPrice
					target := sig.TargetPrice
					if fillPrice < 2000 {
						// Option premium contract: ensure SL is below fillPrice and not index-scale
						if stopLoss <= 0 || stopLoss >= fillPrice || stopLoss > 2000 {
							optSLPts := slPts
							if optSLPts <= 0 || optSLPts >= fillPrice*0.70 {
								optSLPts = math.Max(1.0, math.Round(fillPrice*0.20*100)/100)
							}
							stopLoss = math.Max(0.5, math.Round((fillPrice-optSLPts)*100)/100)
							target = math.Round((fillPrice+(optSLPts*rrRatio))*100) / 100
						}
					} else {
						if stopLoss <= 0 {
							stopLoss = math.Max(1.0, math.Round((fillPrice-slPts)*100)/100)
						}
						if target <= 0 {
							target = math.Round((fillPrice+(slPts*rrRatio))*100) / 100
						}
					}

					orderTime := sig.Timestamp
					if orderTime == "" {
						orderTime = latestLogicalTime.Format("15:04:05")
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

						canonSecID := deriveCanonicalOptionID(sig.TradingSymbol)
						dhanPayload := DhanOrderPayload{
							DhanClientID:    "1000000001",
							CorrelationID:   sig.TradingSymbol,
							TradingSymbol:   sig.TradingSymbol,
							TransactionType: sig.Transaction,
							ExchangeSegment: "NSE_FNO",
							ProductType:     "INTRADAY",
							OrderType:       "MARKET",
							Validity:        "DAY",
							SecurityID:      canonSecID,
							Quantity:        sig.Quantity,
							Price:           fillPrice,
							TriggerPrice:    stopLoss,
							BoStopLossValue: stopLoss,
							BoProfitValue:   target,
							LogicalTimestamp: orderTime,
						}
						if isRealLiveMode(params.ExecutionMode) {
							j.dispatchOrderToDhanLive(ctx, dhanPayload, "")
						} else if isMockMode(params.ExecutionMode) {
							j.dispatchOrderToMockBroker(ctx, dhanPayload)
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
				isMarketOpen = true // In Sandbox/Mock Replay mode, market-closed rules never apply
			}
			if !isMarketOpen {
				// When market/streamer is paused or closed, throttle evaluation to avoid CPU and Redis write churn
				if tickCounter%10 == 0 {
					spotPrice, _ = j.fetchSpotPrice(ctx, indexName)
					j.saveTelemetry(ctx, userID, params.StrategyID, strategyName, false, "PAUSED",
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
						orders[k].ExecutionTime = latestLogicalTime.Format("15:04:05")
						orders[k].FilledQty = orders[k].Quantity
						
						diff := orders[k].LimitEntryPrice - orders[k].CurrentLTP
						orders[k].Price = orders[k].CurrentLTP
						
						// Recalculate SL and TP distances based on actual fill price improvement
						if diff > 0 {
							orders[k].StopLossPrice -= diff
							orders[k].TargetPrice -= diff
							orders[k].InitialStopLossPrice -= diff
							orders[k].InitialTargetPrice -= diff
							
							// Ensure SL doesn't go below minimum tick 0.05
							if orders[k].StopLossPrice < 0.05 {
								orders[k].StopLossPrice = 0.05
							}
							if orders[k].InitialStopLossPrice < 0.05 {
								orders[k].InitialStopLossPrice = 0.05
							}
						}

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

						dhanPayload := DhanOrderPayload{
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
							LogicalTimestamp: nowIST().Format("03:04:05 PM"),
						}
						if isRealLiveMode(params.ExecutionMode) {
							j.dispatchOrderToDhanLive(ctx, dhanPayload, "")
						} else if isMockMode(params.ExecutionMode) {
							j.dispatchOrderToMockBroker(ctx, dhanPayload)
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
					var activeOrderIdx = -1
					for idx, o := range orders {
						if o.TradingSymbol == positions[i].TradingSymbol && o.TransactionType == "BUY" && o.OrderStatus == "TRADED" {
							sl = o.StopLossPrice
							tp = o.TargetPrice
							activeOrderIdx = idx
							break
						}
					}

					// Dynamic TSL Evaluation
					if activeOrderIdx != -1 {
						o := &orders[activeOrderIdx]
						initialRisk := o.Price - o.InitialStopLossPrice
						if initialRisk > 0 {
							profitPts := positions[i].CurrentLTP - o.Price
							profitR := profitPts / initialRisk

							// Evaluate TSL 2
							if stratParams.TSL2_At_R > 0 && o.TrailingStage < 2 {
								if profitR >= stratParams.TSL2_At_R {
									newSL := o.Price + (initialRisk * stratParams.TSL2_Lock_R)
									if newSL > o.StopLossPrice {
										o.StopLossPrice = newSL
										o.TrailingStage = 2
										sl = newSL
										log.Printf("📈 [StrategyWorker #%s] TSL2 Activated! SL trailed to ₹%.2f (%.1fR locked)", taskID, newSL, stratParams.TSL2_Lock_R)
									}
								}
							}
							
							// Evaluate TSL 1 (Breakeven)
							threshold := stratParams.BreakevenAtR
							if threshold == 0 && stratParams.TrailBreakeven {
								threshold = 1.5 // fallback
							}
							if threshold > 0 && o.TrailingStage < 1 {
								if profitR >= threshold {
									if o.Price > o.StopLossPrice {
										o.StopLossPrice = o.Price
										o.TrailingStage = 1
										sl = o.Price
										log.Printf("📈 [StrategyWorker #%s] TSL1 Activated! SL trailed to breakeven @ ₹%.2f", taskID, o.Price)
									}
								}
							}
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
										exitTime = latestLogicalTime.Format("15:04:05")
									}
									
									// Calculate trade duration
									durationStr := ""
									for _, o := range orders {
										if o.TradingSymbol == positions[i].TradingSymbol && o.TransactionType == "BUY" && o.OrderStatus == "TRADED" {
											entryTime, err := time.Parse("15:04:05", o.ExecutionTime)
											if err != nil {
												entryTime, err = time.Parse("03:04:05 PM", o.ExecutionTime)
											}
											exitTimeParsed, err2 := time.Parse("15:04:05", exitTime)
											if err2 != nil {
												exitTimeParsed, err2 = time.Parse("03:04:05 PM", exitTime)
											}
											if err == nil && err2 == nil {
												diff := exitTimeParsed.Sub(entryTime)
												if diff < 0 {
													diff = -diff
												}
												if diff.Hours() >= 1 {
													durationStr = fmt.Sprintf("%dh %dm %ds", int(diff.Hours()), int(diff.Minutes())%60, int(diff.Seconds())%60)
												} else {
													durationStr = fmt.Sprintf("%dm %ds", int(diff.Minutes()), int(diff.Seconds())%60)
												}
											}
											break
										}
									}
									
									exitOrder := SimulatedOrder{
										OrderID:         fmt.Sprintf("DHN-EXIT-%d", time.Now().Unix()%100000),
										CreateTime:      exitTime,
										ExecutionTime:   exitTime,
										TradeDuration:   durationStr,
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

					// Active Real-Time SL and TP Monitoring across Live & Mock Trading
					if positions[i].Status == "OPEN" && positions[i].CurrentLTP > 0 && sl > 0 && tp > 0 {
						triggerReason := ""
						if positions[i].CurrentLTP <= sl {
							triggerReason = "SL Hit"
							if activeOrderIdx != -1 {
								if orders[activeOrderIdx].TrailingStage == 1 {
									triggerReason = "TSL 1 Hit"
								} else if orders[activeOrderIdx].TrailingStage >= 2 {
									triggerReason = "TSL 2 Hit"
								}
							}
						} else if positions[i].CurrentLTP >= tp {
							triggerReason = "TP Hit"
						}
						
						if triggerReason == "SL Hit" && posPnl >= 0 {
							triggerReason = "Breakeven Exit"
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
							log.Printf("🛡️ [StrategyWorker #%s] POSITION SQUARED OFF (%s): SELL %s @ ₹%.2f (P&L: ₹%.2f)\n",
								taskID, triggerReason, positions[i].TradingSymbol, positions[i].CurrentLTP, posPnl)

							leg := "SL_HIT"
							if triggerReason == "TP Hit" {
								leg = "TP_HIT"
							}
							dhanPayload := DhanOrderPayload{
								DhanClientID:    "1000000001",
								CorrelationID:   positions[i].TradingSymbol,
								TradingSymbol:   positions[i].TradingSymbol,
								TransactionType: "SELL",
								ExchangeSegment: "NSE_FNO",
								ProductType:     "INTRADAY",
								OrderType:       "MARKET",
								Validity:        "DAY",
								SecurityID:      positions[i].TradingSymbol,
								Quantity:        positions[i].BuyQty,
								Price:           positions[i].CurrentLTP,
								LegName:         leg,
								LogicalTimestamp: nowStr,
							}
							if isRealLiveMode(params.ExecutionMode) {
								j.dispatchOrderToDhanLive(ctx, dhanPayload, "")
							} else if isMockMode(params.ExecutionMode) {
								j.dispatchOrderToMockBroker(ctx, dhanPayload)
							}
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
					"datetime": latestLogicalTime.Format("2006-01-02 15:04:05"),
					"close":    barClose,
					"open":     barOpen,
					"high":     barHigh,
					"low":      barLow,
					"volume":   125000,
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

								dhanPayload := DhanOrderPayload{
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
									LogicalTimestamp: nowStr,
								}
								if isRealLiveMode(params.ExecutionMode) {
									j.dispatchOrderToDhanLive(ctx, dhanPayload, "")
								} else if isMockMode(params.ExecutionMode) {
									j.dispatchOrderToMockBroker(ctx, dhanPayload)
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

// fetchOptionChainSnaps reads live option quotes from Redis and builds a OptionSnap map
// keyed by "{strike} CALL" or "{strike} PUT" for the strike sweep scorer.
func (j *StrategySignalJob) fetchOptionChainSnaps(ctx context.Context, indexName string) map[string]strategies.OptionSnap {
	result := make(map[string]strategies.OptionSnap)
	if j.redisService == nil || j.redisService.Client == nil {
		return result
	}

	// Scan redis for all option chain quotes for this index stored by broadcaster
	ocKey := fmt.Sprintf("marmot:fyers:option_chain:%s", indexName)
	data, err := j.redisService.Client.Get(ctx, ocKey).Result()
	if err != nil || len(data) == 0 {
		// Try with key prefix used in some environments
		data, err = j.redisService.Client.Get(ctx, ":1:"+ocKey).Result()
		if err != nil || len(data) == 0 {
			return result
		}
	}

	var ocPayload struct {
		Strikes []map[string]interface{} `json:"strikes"`
	}
	if err := json.Unmarshal([]byte(data), &ocPayload); err != nil {
		return result
	}

	for _, s := range ocPayload.Strikes {
		strikeVal, _ := s["strike"].(float64)
		if strikeVal <= 0 {
			continue
		}
		strike := int(strikeVal)

		if ceLTP, ok := s["ce_ltp"].(float64); ok && ceLTP > 0 {
			ceSnap := strategies.OptionSnap{Close: ceLTP}
			if v, ok := s["ce_bid"].(float64); ok {
				ceSnap.Bid = v
			}
			if v, ok := s["ce_ask"].(float64); ok {
				ceSnap.Ask = v
			}
			if v, ok := s["ce_oi"].(float64); ok {
				ceSnap.OI = int64(v)
			}
			if v, ok := s["ce_volume"].(float64); ok {
				ceSnap.Volume = int64(v)
			}
			result[fmt.Sprintf("%d CALL", strike)] = ceSnap
		}

		if peLTP, ok := s["pe_ltp"].(float64); ok && peLTP > 0 {
			peSnap := strategies.OptionSnap{Close: peLTP}
			if v, ok := s["pe_bid"].(float64); ok {
				peSnap.Bid = v
			}
			if v, ok := s["pe_ask"].(float64); ok {
				peSnap.Ask = v
			}
			if v, ok := s["pe_oi"].(float64); ok {
				peSnap.OI = int64(v)
			}
			if v, ok := s["pe_volume"].(float64); ok {
				peSnap.Volume = int64(v)
			}
			result[fmt.Sprintf("%d PUT", strike)] = peSnap
		}
	}

	// Fallback to Fyers REST 31-strike chain cached by TargetedOptionChainPoller
	if len(result) == 0 {
		focKey := fmt.Sprintf("marmot:fyers:full_option_chain:%s", indexName)
		if fData, fErr := j.redisService.Client.Get(ctx, focKey).Result(); fErr == nil && len(fData) > 0 {
			var fullPayload struct {
				Data struct {
					OptionsChain []map[string]interface{} `json:"optionsChain"`
				} `json:"data"`
			}
			if err := json.Unmarshal([]byte(fData), &fullPayload); err == nil {
				for _, item := range fullPayload.Data.OptionsChain {
					sp, _ := item["strike_price"].(float64)
					if sp <= 0 {
						continue
					}
					strike := int(sp)
					optType, _ := item["option_type"].(string)
					ltp, _ := item["ltp"].(float64)
					if ltp <= 0 {
						continue
					}
					snap := strategies.OptionSnap{Close: ltp}
					if v, ok := item["bid"].(float64); ok {
						snap.Bid = v
					}
					if v, ok := item["ask"].(float64); ok {
						snap.Ask = v
					}
					if v, ok := item["oi"].(float64); ok {
						snap.OI = int64(v)
					}
					if v, ok := item["volume"].(float64); ok {
						snap.Volume = int64(v)
					}
					if optType == "CE" {
						result[fmt.Sprintf("%d CALL", strike)] = snap
					} else if optType == "PE" {
						result[fmt.Sprintf("%d PUT", strike)] = snap
					}
				}
			}
		}
	}

	return result
}

// LiveQuoteMetrics holds real-time quote metrics fetched from Redis for index spot and candle construction.
type LiveQuoteMetrics struct {
	SpotPrice float64
	ATMStrike int
	OpenPrice float64
	HighPrice float64
	LowPrice  float64
}

// fetchSpotMetrics reads authentic session quote data from in-memory cache or Redis (open, high, low, lp).
func (j *StrategySignalJob) fetchSpotMetrics(ctx context.Context, indexName string) LiveQuoteMetrics {
	res := LiveQuoteMetrics{}

	// 0. Primary in LIVE mode: Instant in-memory spot read from Go WebSocket engine (0.00ms, zero Redis load)
	if !isMockMode(j.payload.Params.ExecutionMode) {
		if tick, ok := ws.GetLatestSpot(indexName); ok && tick.SpotPrice > 0 {
			res.SpotPrice = tick.SpotPrice
			var high, low float64
			_, _ = fmt.Sscanf(strings.ReplaceAll(tick.High, ",", ""), "%f", &high)
			_, _ = fmt.Sscanf(strings.ReplaceAll(tick.Low, ",", ""), "%f", &low)
			res.HighPrice = high
			res.LowPrice = low
			step := StrikeIntervalForIndex(indexName)
			if step <= 0 {
				step = 50
			}
			res.ATMStrike = int(math.Round(tick.SpotPrice/float64(step)) * float64(step))
			return res
		}
	}

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

	isMock := isMockMode(j.payload.Params.ExecutionMode) || !isRealLiveMode(j.payload.Params.ExecutionMode)
	if val, err := j.redisService.Client.Get(ctx, "marmot:mock_feed:active").Result(); err == nil && val == "true" {
		isMock = true
	}

	if isMock {
		// In Mock / Sandbox mode: prioritize local mock broker emulator and mock Redis keys
		mockKeys := []string{
			fmt.Sprintf("marmot:mock:option_chain:%s", indexName),
			fmt.Sprintf("marmot:mock:last_known_option_chain:%s", indexName),
		}
		for _, k := range mockKeys {
			data, err := j.redisService.Client.Get(ctx, k).Result()
			if err == nil && len(data) > 0 {
				var rawMap map[string]interface{}
				if unmarshalErr := json.Unmarshal([]byte(data), &rawMap); unmarshalErr == nil {
					var price float64
					if v, ok := rawMap["raw_spot_ltp"].(float64); ok && v > 0 {
						price = v
					} else if s, ok := rawMap["spot_ltp"].(string); ok {
						cleanStr := strings.ReplaceAll(strings.ReplaceAll(s, ",", ""), "₹", "")
						_, _ = fmt.Sscanf(cleanStr, "%f", &price)
					}
					if price > 0 {
						res.SpotPrice = price
						res.OpenPrice = price
						res.HighPrice = price
						res.LowPrice = price
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

		// Direct query to local mock broker emulator
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
						_ = j.redisService.Client.Set(ctx, fmt.Sprintf("marmot:mock:option_chain:%s", indexName), b, 5*time.Minute).Err()
						_ = j.redisService.Client.Set(ctx, fmt.Sprintf("marmot:mock:last_known_option_chain:%s", indexName), b, 24*time.Hour).Err()
					}
					return res
				}
			} else {
				resp.Body.Close()
			}
		}
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

	// 1. User-level sandbox & mock telemetry
	userKey := fmt.Sprintf("marmot:mock:telemetry:%s", userID)
	_ = j.redisService.Client.Set(ctx, userKey, bytes, 30*time.Minute).Err()
	sandboxUserKey := fmt.Sprintf("marmot:sandbox:telemetry:%s", userID)
	_ = j.redisService.Client.Set(ctx, sandboxUserKey, bytes, 30*time.Minute).Err()

	// 2. Strategy-level telemetry
	stratKey := fmt.Sprintf("marmot:mock:telemetry:strategy:%d", strategyID)
	_ = j.redisService.Client.Set(ctx, stratKey, bytes, 30*time.Minute).Err()
	sandboxStratKey := fmt.Sprintf("marmot:sandbox:telemetry:strategy:%d", strategyID)
	_ = j.redisService.Client.Set(ctx, sandboxStratKey, bytes, 30*time.Minute).Err()

	// 3. WS Broadcast to active subscribers & general hub
	if j.hub != nil {
		wsPayload, _ := json.Marshal(map[string]interface{}{
			"type":       "mock_telemetry",
			"task_id":    j.payload.TaskID,
			"spot_price": spotPrice,
			"data":       telemetry,
		})
		if status == "STREAMING" && processingLatencyMs > 0 && time.Since(j.lastTelemetryLogTime) >= 10*time.Second {
			j.lastTelemetryLogTime = time.Now()
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
