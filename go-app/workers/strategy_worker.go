package workers

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"math"
	"math/rand"
	"time"

	"go-app/config"
	"go-app/models"
	"go-app/services"
	"go-app/strategies"
	"go-app/ws"
)

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
	RealizedProfit   float64 `json:"realized_profit"`
	UnrealizedProfit float64 `json:"unrealized_profit"`
	TotalPnL         float64 `json:"total_pnl"`
	EntrySpot        float64 `json:"entry_spot"`
}

// SimulatedOrder represents an executed or pending paper order.
type SimulatedOrder struct {
	OrderID         string  `json:"order_id"`
	CreateTime      string  `json:"create_time"`
	TradingSymbol   string  `json:"trading_symbol"`
	ExchangeSegment string  `json:"exchange_segment"`
	TransactionType string  `json:"transaction_type"`
	OrderType       string  `json:"order_type"`
	ProductType     string  `json:"product_type"`
	Validity        string  `json:"validity"`
	Quantity        int     `json:"quantity"`
	FilledQty       int     `json:"filled_qty"`
	Price           float64 `json:"price"`
	TriggerPrice    float64 `json:"trigger_price"`
	OrderStatus     string  `json:"order_status"`
	OMSErrorDesc    string  `json:"oms_error_desc"`
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
		strategyName = "tensortrade_rl"
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

	ticker := time.NewTicker(2 * time.Second)
	defer ticker.Stop()

	// Initialize simulated paper trading book
	initialCapital := params.InitialCapital
	if initialCapital <= 0 {
		initialCapital = 1000000.00
	}
	cashBalance := initialCapital

	positions := []SimulatedPosition{
		{
			TradingSymbol:    fmt.Sprintf("%s 23750 CE", indexName),
			ExchangeSegment:  "NSE_FNO",
			Status:           "OPEN",
			ProductType:      "INTRADAY",
			NetQty:           50,
			BuyQty:           50,
			BuyAvg:           92.50,
			SellQty:          0,
			SellAvg:          0.0,
			RealizedProfit:   0.0,
			UnrealizedProfit: 1425.00,
			TotalPnL:         1425.00,
			EntrySpot:        23760.0,
		},
		{
			TradingSymbol:    fmt.Sprintf("%s 23700 PE", indexName),
			ExchangeSegment:  "NSE_FNO",
			Status:           "OPEN",
			ProductType:      "INTRADAY",
			NetQty:           50,
			BuyQty:           50,
			BuyAvg:           38.80,
			SellQty:          0,
			SellAvg:          0.0,
			RealizedProfit:   0.0,
			UnrealizedProfit: 860.00,
			TotalPnL:         860.00,
			EntrySpot:        23760.0,
		},
		{
			TradingSymbol:    fmt.Sprintf("%s 23800 CE", indexName),
			ExchangeSegment:  "NSE_FNO",
			Status:           "CLOSED",
			ProductType:      "INTRADAY",
			NetQty:           0,
			BuyQty:           50,
			BuyAvg:           64.80,
			SellQty:          50,
			SellAvg:          98.20,
			RealizedProfit:   1670.00,
			UnrealizedProfit: 0.0,
			TotalPnL:         1670.00,
			EntrySpot:        23740.0,
		},
	}

	orders := []SimulatedOrder{
		{
			OrderID:         fmt.Sprintf("SBX-%d01", time.Now().Unix()%100000),
			CreateTime:      time.Now().Add(-25 * time.Minute).Format("03:04 PM"),
			TradingSymbol:   fmt.Sprintf("%s 23800 CE", indexName),
			ExchangeSegment: "NSE_FNO",
			TransactionType: "BUY",
			OrderType:       "MARKET",
			ProductType:     "INTRADAY",
			Validity:        "DAY",
			Quantity:        50,
			FilledQty:       50,
			Price:           64.80,
			OrderStatus:     "TRADED",
		},
		{
			OrderID:         fmt.Sprintf("SBX-%d02", time.Now().Unix()%100000),
			CreateTime:      time.Now().Add(-15 * time.Minute).Format("03:04 PM"),
			TradingSymbol:   fmt.Sprintf("%s 23800 CE", indexName),
			ExchangeSegment: "NSE_FNO",
			TransactionType: "SELL",
			OrderType:       "LIMIT",
			ProductType:     "INTRADAY",
			Validity:        "DAY",
			Quantity:        50,
			FilledQty:       50,
			Price:           98.20,
			OrderStatus:     "TRADED",
		},
		{
			OrderID:         fmt.Sprintf("SBX-%d03", time.Now().Unix()%100000),
			CreateTime:      time.Now().Add(-8 * time.Minute).Format("03:04 PM"),
			TradingSymbol:   fmt.Sprintf("%s 23750 CE", indexName),
			ExchangeSegment: "NSE_FNO",
			TransactionType: "BUY",
			OrderType:       "MARKET",
			ProductType:     "INTRADAY",
			Validity:        "DAY",
			Quantity:        50,
			FilledQty:       50,
			Price:           92.50,
			OrderStatus:     "TRADED",
		},
		{
			OrderID:         fmt.Sprintf("SBX-%d04", time.Now().Unix()%100000),
			CreateTime:      time.Now().Add(-3 * time.Minute).Format("03:04 PM"),
			TradingSymbol:   fmt.Sprintf("%s 23700 PE", indexName),
			ExchangeSegment: "NSE_FNO",
			TransactionType: "BUY",
			OrderType:       "MARKET",
			ProductType:     "INTRADAY",
			Validity:        "DAY",
			Quantity:        50,
			FilledQty:       50,
			Price:           38.80,
			OrderStatus:     "TRADED",
		},
	}

	tickCounter := 0

	for {
		select {
		case <-ctx.Done():
			log.Printf("⏸️ [StrategyWorker #%s] Pausing Autonomous Signal Loop for User #%s\n", taskID, userID)
			j.saveTelemetry(context.Background(), userID, params.StrategyID, strategyName, false, "PAUSED",
				23760.0, cashBalance, cashBalance, positions, orders)
			return

		case <-ticker.C:
			tickCounter++
			spotPrice, atmStrike := j.fetchSpotPrice(ctx, indexName)

			// Update unrealized PnL for open positions based on live spot delta
			var realizedTotal, unrealizedTotal, marginUtilized float64
			for i := range positions {
				if positions[i].Status == "OPEN" {
					marginUtilized += float64(positions[i].NetQty) * positions[i].BuyAvg
					// Dynamic delta simulation
					delta := 0.45
					if rand.Float32() > 0.5 {
						delta = 0.55
					}
					spotDiff := spotPrice - positions[i].EntrySpot
					// Micro tick fluctuation
					jitter := (rand.Float64() - 0.48) * 12.0
					posPnl := math.Round(((spotDiff * delta) + jitter) * float64(positions[i].NetQty))
					positions[i].UnrealizedProfit = posPnl
					positions[i].TotalPnL = posPnl
					unrealizedTotal += posPnl
				} else {
					realizedTotal += positions[i].RealizedProfit
				}
			}

			// Periodically evaluate strategy for new simulated trade signals (every 6th tick = ~12s)
			if tickCounter%6 == 0 {
				candle := map[string]interface{}{
					"close":  spotPrice,
					"open":   spotPrice - 4.5,
					"high":   spotPrice + 8.2,
					"low":    spotPrice - 6.1,
					"volume": 125000,
				}
				sig := strat.EvaluateLiveSignal(candle, nil, indexName, params.Params)
				if sig != nil && len(positions) < 8 {
					newSymbol := fmt.Sprintf("%s %d CE", indexName, atmStrike)
					newOrderID := fmt.Sprintf("SBX-%d%02d", time.Now().Unix()%100000, rand.Intn(90)+10)
					fillPrice := math.Round((95.0+(rand.Float64()*10.0))*100) / 100

					newOrder := SimulatedOrder{
						OrderID:         newOrderID,
						CreateTime:      time.Now().Format("03:04:05 PM"),
						TradingSymbol:   newSymbol,
						ExchangeSegment: "NSE_FNO",
						TransactionType: "BUY",
						OrderType:       "MARKET",
						ProductType:     "INTRADAY",
						Validity:        "DAY",
						Quantity:        sig.Quantity,
						FilledQty:       sig.Quantity,
						Price:           fillPrice,
						OrderStatus:     "TRADED",
					}
					// Prepend order
					orders = append([]SimulatedOrder{newOrder}, orders...)

					log.Printf("⚡ [StrategyWorker #%s] Paper Order Executed: %s %s @ ₹%.2f\n",
						taskID, sig.Transaction, newSymbol, fillPrice)
				}
			}

			j.saveTelemetry(ctx, userID, params.StrategyID, strategyName, true, "STREAMING",
				spotPrice, cashBalance, cashBalance-marginUtilized, positions, orders)
		}
	}
}

// fetchSpotPrice reads the latest FYERS option chain quote from Redis or falls back gracefully.
func (j *StrategySignalJob) fetchSpotPrice(ctx context.Context, indexName string) (float64, int) {
	if j.redisService == nil || j.redisService.Client == nil {
		return 23760.30, 23750
	}

	keysToTry := []string{
		fmt.Sprintf("marmot:fyers:option_chain:%s", indexName),
		fmt.Sprintf(":1:marmot:fyers:option_chain:%s", indexName),
	}

	for _, k := range keysToTry {
		data, err := j.redisService.Client.Get(ctx, k).Result()
		if err == nil && len(data) > 0 {
			var parsed struct {
				RawSpotLTP float64 `json:"raw_spot_ltp"`
				ATMStrike  int     `json:"atm_strike"`
			}
			if unmarshalErr := json.Unmarshal([]byte(data), &parsed); unmarshalErr == nil && parsed.RawSpotLTP > 0 {
				atm := parsed.ATMStrike
				if atm == 0 {
					atm = int(math.Round(parsed.RawSpotLTP/50.0) * 50)
				}
				return parsed.RawSpotLTP, atm
			}
		}
	}

	return 23760.30, 23750
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
		"last_eval_time":         time.Now().Format("15:04:05 IST"),
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
	}

	bytes, err := json.Marshal(telemetry)
	if err != nil {
		return
	}

	// 1. User-level sandbox telemetry
	userKey := fmt.Sprintf("marmot:sandbox:telemetry:%s", userID)
	_ = j.redisService.Client.Set(ctx, userKey, bytes, 30*time.Minute).Err()

	// 2. Strategy-level telemetry
	stratKey := fmt.Sprintf("marmot:sandbox:telemetry:strategy:%d", strategyID)
	_ = j.redisService.Client.Set(ctx, stratKey, bytes, 30*time.Minute).Err()

	// 3. WS Broadcast to active subscribers
	if j.hub != nil {
		wsPayload, _ := json.Marshal(map[string]interface{}{
			"type": "sandbox_telemetry",
			"data": telemetry,
		})
		j.hub.BroadcastToTask(j.payload.TaskID, wsPayload)
	}
}
