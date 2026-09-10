package ws

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"strings"
	"time"

	"go-app/services"
)

// LiveTickPayload represents normalized tick telemetry pushed to frontend dashboards.
type LiveTickPayload struct {
	Type          string  `json:"type"`
	Index         string  `json:"index"`
	SpotPrice     float64 `json:"spot_price"`
	LTP           string  `json:"ltp"`
	Change        string  `json:"change"`
	ChangePct     string  `json:"change_pct"`
	High          string  `json:"high"`
	Low           string  `json:"low"`
	IsPositive    bool    `json:"is_positive"`
	FormattedTime string  `json:"formatted_time"`
	Timestamp     string  `json:"timestamp"`
}

// StartMarketDataBroadcaster streams real-time index ticks and Pub/Sub events to WS clients.
func StartMarketDataBroadcaster(ctx context.Context, redisService *services.RedisService, hub *Hub) {
	log.Println("🚀 [WS Broadcaster] Starting market data streaming broadcaster...")

	// 1. Subscribe to real-time Redis Pub/Sub events (ticks, orders, positions, telemetry)
	pubsub := redisService.Subscribe(ctx, "marmot:ticks", "marmot:orders", "marmot:positions", "marmot:telemetry")
	defer pubsub.Close()

	go func() {
		ch := pubsub.Channel()
		for {
			select {
			case <-ctx.Done():
				return
			case msg, ok := <-ch:
				if !ok {
					return
				}
				if msg != nil && len(msg.Payload) > 0 {
					hub.Broadcast <- []byte(msg.Payload)
				}
			}
		}
	}()

	// 2. Periodic tick sync: Reads latest Redis cache and broadcasts whenever clients are connected
	ticker := time.NewTicker(1 * time.Second)
	defer ticker.Stop()

	indices := []string{"NIFTY", "BANKNIFTY"}

	for {
		select {
		case <-ctx.Done():
			log.Println("🛑 [WS Broadcaster] Stopping market broadcaster.")
			return
		case <-ticker.C:
			// Only broadcast if there are connected clients
			if len(hub.clients) == 0 {
				continue
			}

			for _, idx := range indices {
				payload := fetchLatestTickFromRedis(ctx, redisService, idx)
				if payload != nil {
					data, err := json.Marshal(payload)
					if err == nil {
						hub.Broadcast <- data
					}
				}
			}
		}
	}
}

// fetchLatestTickFromRedis extracts the latest quote from Redis cache keys.
func fetchLatestTickFromRedis(ctx context.Context, redisService *services.RedisService, indexName string) *LiveTickPayload {
	keys := []string{
		fmt.Sprintf("marmot:fyers:option_chain:%s", indexName),
		fmt.Sprintf(":1:marmot:fyers:option_chain:%s", indexName),
		fmt.Sprintf("marmot:fyers_quote:NSE:%s50-INDEX", indexName),
		fmt.Sprintf(":1:marmot:fyers_quote:NSE:%s50-INDEX", indexName),
	}

	for _, k := range keys {
		val, err := redisService.Client.Get(ctx, k).Result()
		if err != nil || len(val) == 0 {
			continue
		}

		var rawMap map[string]interface{}
		if err := json.Unmarshal([]byte(val), &rawMap); err != nil {
			continue
		}

		spotRaw, hasSpot := rawMap["raw_spot_ltp"]
		if !hasSpot {
			spotRaw = rawMap["spot_ltp"]
		}

		var spotFloat float64
		switch v := spotRaw.(type) {
		case float64:
			spotFloat = v
		case string:
			cleanStr := strings.ReplaceAll(strings.ReplaceAll(v, ",", ""), "₹", "")
			_, _ = fmt.Sscanf(cleanStr, "%f", &spotFloat)
		}

		if spotFloat > 0 {
			chStr := fmt.Sprintf("%v", rawMap["spot_change"])
			chpStr := fmt.Sprintf("%v", rawMap["spot_change_pct"])
			hpStr := fmt.Sprintf("%v", rawMap["high_price"])
			lpStr := fmt.Sprintf("%v", rawMap["low_price"])
			nowStr := time.Now().Format("03:04:05 PM")

			return &LiveTickPayload{
				Type:          "live_tick",
				Index:         indexName,
				SpotPrice:     spotFloat,
				LTP:           fmt.Sprintf("%.2f", spotFloat),
				Change:        chStr,
				ChangePct:     chpStr,
				High:          hpStr,
				Low:           lpStr,
				IsPositive:    !strings.HasPrefix(chStr, "-"),
				FormattedTime: nowStr,
				Timestamp:     nowStr,
			}
		}
	}

	return nil
}
