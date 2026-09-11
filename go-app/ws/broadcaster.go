package ws

import (
	"context"
	"encoding/binary"
	"encoding/json"
	"fmt"
	"log"
	"math"
	"net/http"
	"strings"
	"sync/atomic"
	"time"

	"github.com/gorilla/websocket"

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
func StartMarketDataBroadcaster(ctx context.Context, redisService *services.RedisService, dbService *services.DBService, hub *Hub) {
	log.Println("🚀 [WS Broadcaster] Starting Hybrid Market Data Ingestion Pipeline (WS + REST)...")

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

	// 2. Start Hybrid Ingestion Pipeline (Primary WebSocket + 5s REST Fallback + Targeted Option Chain)
	if dbService != nil {
		var wsConnected atomic.Bool
		var lastWSTickUnix atomic.Int64

		// Primary: Real-time WebSocket streaming for sub-10ms spot price updates
		go StreamFyersTicks(ctx, redisService, dbService, hub, &wsConnected, &lastWSTickUnix)

		// Fallback: Automated REST poller watchdog if WS fails or is disconnected > 5 seconds
		go PollFyersLiveQuotes(ctx, redisService, dbService, hub, &wsConnected, &lastWSTickUnix)

		// Targeted: Multi-strike heavy option chain REST fetcher (on ATM shift or 5s interval)
		go TargetedOptionChainPoller(ctx, redisService, dbService)
	}

	// 3. Periodic tick sync: Reads latest Redis cache and broadcasts whenever clients are connected
	ticker := time.NewTicker(1 * time.Second)
	defer ticker.Stop()

	indices := []string{"NIFTY", "BANKNIFTY", "SENSEX"}

	tickCount := 0
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

			tickCount++
			for _, idx := range indices {
				payload := fetchLatestTickFromRedis(ctx, redisService, idx)
				if payload != nil {
					data, err := json.Marshal(payload)
					if err == nil {
						if tickCount%5 == 0 {
							log.Printf("📈 [WS Passing Value -> Clients] %s LTP: %.2f | Chg: %s (%s) | High: %s Low: %s | Time: %s\n",
								idx, payload.SpotPrice, payload.Change, payload.ChangePct, payload.High, payload.Low, payload.Timestamp)
						}
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
		fmt.Sprintf("marmot:fyers:last_known_option_chain:%s", indexName),
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

// StreamFyersTicks maintains a WebSocket connection to FYERS DataSocket V3 for sub-10ms spot updates.
func StreamFyersTicks(ctx context.Context, redisService *services.RedisService, dbService *services.DBService, hub *Hub, wsConnected *atomic.Bool, lastWSTickUnix *atomic.Int64) {
	log.Println("⚡ [FYERS WS Streamer] Starting Primary WebSocket V3 Streamer...")
	backoff := 1 * time.Second
	maxBackoff := 30 * time.Second

	symbolToIndex := map[string]string{
		"NSE:NIFTY50-INDEX":   "NIFTY",
		"NSE:NIFTYBANK-INDEX": "BANKNIFTY",
		"BSE:SENSEX-INDEX":    "SENSEX",
	}

	for {
		select {
		case <-ctx.Done():
			log.Println("🛑 [FYERS WS Streamer] Context cancelled. Exiting streamer.")
			wsConnected.Store(false)
			return
		default:
		}

		if !IsMarketSessionActive() {
			wsConnected.Store(false)
			time.Sleep(30 * time.Second)
			continue
		}

		appID, token, err := dbService.GetBrokerCredentials(ctx)
		if err != nil || strings.TrimSpace(appID) == "" || strings.TrimSpace(token) == "" {
			log.Printf("⚠️ [FYERS WS Streamer] Broker credentials unavailable: %v. Retrying in %v...\n", err, backoff)
			time.Sleep(backoff)
			backoff = minDuration(backoff*2, maxBackoff)
			continue
		}

		cleanAppID := strings.TrimSpace(appID)
		cleanToken := strings.TrimSpace(token)
		authHeader := fmt.Sprintf("%s:%s", cleanAppID, cleanToken)

		endpoints := []string{"wss://api.fyers.in/socket/v2/data/", "wss://socket.fyers.in/data/v3"}
		var conn *websocket.Conn
		var connectedURL string

		dialer := websocket.Dialer{
			HandshakeTimeout: 5 * time.Second,
		}

		for _, wsURL := range endpoints {
			log.Printf("⚡ [FYERS WS Streamer] Attempting connection to %s ...\n", wsURL)
			c, resp, err := dialer.DialContext(ctx, wsURL, nil)
			if err == nil {
				conn = c
				connectedURL = wsURL
				break
			}
			if resp != nil {
				log.Printf("⚠️ [FYERS WS Streamer] Dial to %s failed (status %d): %v\n", wsURL, resp.StatusCode, err)
			} else {
				log.Printf("⚠️ [FYERS WS Streamer] Dial to %s failed: %v\n", wsURL, err)
			}
		}

		if conn == nil {
			wsConnected.Store(false)
			time.Sleep(backoff)
			backoff = minDuration(backoff*2, maxBackoff)
			continue
		}

		log.Printf("✅ [FYERS WS Streamer] Connected successfully to %s\n", connectedURL)
		wsConnected.Store(true)
		lastWSTickUnix.Store(time.Now().Unix())
		backoff = 1 * time.Second

		// Authenticate and subscribe over socket
		authMsg := map[string]interface{}{
			"T":            "SUB_DATA",
			"SUB_T":        1,
			"access_token": authHeader,
			"symbols":      []string{"NSE:NIFTY50-INDEX", "NSE:NIFTYBANK-INDEX", "BSE:SENSEX-INDEX"},
		}
		if authBytes, err := json.Marshal(authMsg); err == nil {
			_ = conn.WriteMessage(websocket.TextMessage, authBytes)
		}

		subMsg := map[string]interface{}{
			"symbol": []string{"NSE:NIFTY50-INDEX", "NSE:NIFTYBANK-INDEX", "BSE:SENSEX-INDEX"},
			"type":   "symbolUpdate",
		}
		if subBytes, err := json.Marshal(subMsg); err == nil {
			_ = conn.WriteMessage(websocket.TextMessage, subBytes)
		}

		// Also send legacy SUB_DATA payload for v2/v3 cross-compatibility
		legacySub := map[string]interface{}{
			"T":       "SUB_DATA",
			"SUB_T":   1,
			"symbols": []string{"NSE:NIFTY50-INDEX", "NSE:NIFTYBANK-INDEX", "BSE:SENSEX-INDEX"},
		}
		if legBytes, err := json.Marshal(legacySub); err == nil {
			_ = conn.WriteMessage(websocket.TextMessage, legBytes)
		}

		conn.SetReadDeadline(time.Now().Add(30 * time.Second))
		conn.SetPongHandler(func(string) error {
			conn.SetReadDeadline(time.Now().Add(30 * time.Second))
			return nil
		})

		doneChan := make(chan struct{})
		go func() {
			pingTicker := time.NewTicker(15 * time.Second)
			defer pingTicker.Stop()
			for {
				select {
				case <-doneChan:
					return
				case <-ctx.Done():
					return
				case <-pingTicker.C:
					if err := conn.WriteControl(websocket.PingMessage, []byte("ping"), time.Now().Add(5*time.Second)); err != nil {
						return
					}
				}
			}
		}()

		prevLTP := make(map[string]float64)

		for {
			msgType, msgBytes, err := conn.ReadMessage()
			if err != nil {
				log.Printf("⚠️ [FYERS WS Streamer] Socket read error or connection lost: %v\n", err)
				break
			}

			conn.SetReadDeadline(time.Now().Add(30 * time.Second))
			lastWSTickUnix.Store(time.Now().Unix())
			wsConnected.Store(true)

			parseAndPublishFyersFrame(ctx, msgType, msgBytes, redisService, symbolToIndex, prevLTP)
		}

		close(doneChan)
		conn.Close()
		wsConnected.Store(false)
		log.Printf("🔄 [FYERS WS Streamer] Disconnected. Reconnecting in %v...\n", backoff)
		time.Sleep(backoff)
		backoff = minDuration(backoff*2, maxBackoff)
	}
}

// parseAndPublishFyersFrame processes incoming WebSocket frames (JSON text or binary packets) into Redis.
func parseAndPublishFyersFrame(ctx context.Context, msgType int, msgBytes []byte, redisService *services.RedisService, symbolToIndex map[string]string, prevLTP map[string]float64) {
	if len(msgBytes) == 0 {
		return
	}

	// 1. Text or JSON encapsulated in Binary
	if msgType == websocket.TextMessage || msgBytes[0] == '{' || msgBytes[0] == '[' {
		var rawMap map[string]interface{}
		if err := json.Unmarshal(msgBytes, &rawMap); err == nil {
			processFyersJSONMap(ctx, rawMap, redisService, symbolToIndex, prevLTP)
			return
		}
		var rawList []map[string]interface{}
		if err := json.Unmarshal(msgBytes, &rawList); err == nil {
			for _, item := range rawList {
				processFyersJSONMap(ctx, item, redisService, symbolToIndex, prevLTP)
			}
			return
		}
	}

	// 2. Binary frame unpack (symbolUpdate 72-byte or lite packet)
	if msgType == websocket.BinaryMessage && len(msgBytes) >= 24 {
		processFyersBinaryPacket(ctx, msgBytes, redisService, symbolToIndex, prevLTP)
	}
}

// processFyersJSONMap normalizes JSON quote dicts and publishes to Redis.
func processFyersJSONMap(ctx context.Context, data map[string]interface{}, redisService *services.RedisService, symbolToIndex map[string]string, prevLTP map[string]float64) {
	sym, _ := data["symbol"].(string)
	if sym == "" {
		sym, _ = data["n"].(string)
	}
	if sym == "" {
		sym, _ = data["s"].(string)
	}

	idxName, ok := symbolToIndex[sym]
	if !ok {
		// Check nested inside "d" array or "v" object
		if dArr, isD := data["d"].([]interface{}); isD {
			for _, item := range dArr {
				if itemMap, ok := item.(map[string]interface{}); ok {
					processFyersJSONMap(ctx, itemMap, redisService, symbolToIndex, prevLTP)
				}
			}
			return
		}
		return
	}

	var ltp, ch, chp, high, low, open, prevClose float64
	if vMap, isV := data["v"].(map[string]interface{}); isV {
		ltp, _ = vMap["lp"].(float64)
		ch, _ = vMap["ch"].(float64)
		chp, _ = vMap["chp"].(float64)
		high, _ = vMap["high_price"].(float64)
		low, _ = vMap["low_price"].(float64)
		open, _ = vMap["open_price"].(float64)
		prevClose, _ = vMap["prev_close_price"].(float64)
	} else {
		ltp, _ = data["ltp"].(float64)
		ch, _ = data["ch"].(float64)
		chp, _ = data["chp"].(float64)
		high, _ = data["high_price"].(float64)
		low, _ = data["low_price"].(float64)
		open, _ = data["open_price"].(float64)
		prevClose, _ = data["prev_close_price"].(float64)
	}

	if ltp <= 0 {
		return
	}

	publishIndexQuoteToRedis(ctx, redisService, idxName, sym, ltp, ch, chp, high, low, open, prevClose, "WS_V3", prevLTP)
}

// processFyersBinaryPacket unpacks raw binary symbolUpdate frames.
func processFyersBinaryPacket(ctx context.Context, msgBytes []byte, redisService *services.RedisService, symbolToIndex map[string]string, prevLTP map[string]float64) {
	// Offset 0-2: Packet length or header
	// Inspect ASCII symbol prefix in header if available
	strRepr := string(msgBytes)
	for sym, idxName := range symbolToIndex {
		if strings.Contains(strRepr, sym) {
			// Extract float32/float64 LTP from binary tail
			if len(msgBytes) >= 32 {
				bits := binary.BigEndian.Uint32(msgBytes[len(msgBytes)-8 : len(msgBytes)-4])
				ltp := float64(math.Float32frombits(bits))
				if ltp > 1000 && ltp < 100000 {
					publishIndexQuoteToRedis(ctx, redisService, idxName, sym, ltp, 0, 0, ltp, ltp, ltp, ltp, "WS_BINARY", prevLTP)
					return
				}
			}
		}
	}
}

// publishIndexQuoteToRedis writes normalized spot quote and calculated ATM strike to Redis.
func publishIndexQuoteToRedis(ctx context.Context, redisService *services.RedisService, idxName, sym string, ltp, ch, chp, high, low, open, prevClose float64, source string, prevLTP map[string]float64) {
	step := 50
	if idxName == "BANKNIFTY" || idxName == "SENSEX" {
		step = 100
	}
	atmStrike := int(math.Round(ltp/float64(step)) * float64(step))
	nowStr := time.Now().Format("03:04:05 PM")

	chainPayload := map[string]interface{}{
		"is_live":         true,
		"is_fyers_live":   true,
		"feed_status":     source,
		"index_name":      idxName,
		"spot_symbol":     idxName,
		"fyers_symbol":    sym,
		"raw_spot_ltp":    ltp,
		"spot_ltp":        fmt.Sprintf("%.2f", ltp),
		"spot_change":     fmt.Sprintf("%.2f", ch),
		"spot_change_pct": fmt.Sprintf("%.2f%%", chp),
		"open_price":      open,
		"high_price":      high,
		"low_price":       low,
		"prev_close":      prevClose,
		"atm_strike":      atmStrike,
		"last_updated":    nowStr,
	}

	chainBytes, err := json.Marshal(chainPayload)
	if err != nil {
		return
	}

	_ = redisService.Client.Set(ctx, fmt.Sprintf("marmot:fyers:last_known_option_chain:%s", idxName), chainBytes, 24*time.Hour).Err()
	_ = redisService.Client.Set(ctx, fmt.Sprintf("marmot:fyers:option_chain:%s", idxName), chainBytes, 10*time.Second).Err()
	_ = redisService.Client.Set(ctx, fmt.Sprintf("marmot:fyers_quote:%s", sym), chainBytes, 24*time.Hour).Err()

	if prevLTP[idxName] != ltp {
		log.Printf("⚡ [FYERS Sub-10ms Tick: %s] %s: ₹%.2f (Chg: %.2f | %.2f%%) | ATM: %d\n",
			source, idxName, ltp, ch, chp, atmStrike)
		prevLTP[idxName] = ltp
	}
}

type fyersQuoteData struct {
	N string `json:"n"`
	S string `json:"s"`
	V struct {
		Lp             float64 `json:"lp"`
		Ch             float64 `json:"ch"`
		Chp            float64 `json:"chp"`
		HighPrice      float64 `json:"high_price"`
		LowPrice       float64 `json:"low_price"`
		OpenPrice      float64 `json:"open_price"`
		PrevClosePrice float64 `json:"prev_close_price"`
	} `json:"v"`
}

type fyersQuoteResponse struct {
	S string           `json:"s"`
	D []fyersQuoteData `json:"d"`
}

// PollFyersLiveQuotes acts as the REST fallback and watchdog when the primary WebSocket is disconnected >5s.
func PollFyersLiveQuotes(ctx context.Context, redisService *services.RedisService, dbService *services.DBService, hub *Hub, wsConnected *atomic.Bool, lastWSTickUnix *atomic.Int64) {
	log.Println("🛡️ [FYERS Fallback Manager] Initialized 5-second WS failover watchdog.")
	ticker := time.NewTicker(1 * time.Second)
	defer ticker.Stop()

	httpClient := &http.Client{Timeout: 3 * time.Second}
	var cachedAppID, cachedToken string
	lastCredsCheck := time.Time{}
	prevLTP := make(map[string]float64)

	symbolToIndex := map[string]string{
		"NSE:NIFTY50-INDEX":   "NIFTY",
		"NSE:NIFTYBANK-INDEX": "BANKNIFTY",
		"BSE:SENSEX-INDEX":    "SENSEX",
	}

	for {
		select {
		case <-ctx.Done():
			log.Println("🛑 [FYERS Fallback Manager] Stopped.")
			return
		case <-ticker.C:
			if !IsMarketSessionActive() {
				continue
			}

			// Check if primary WebSocket is actively streaming
			lastTick := lastWSTickUnix.Load()
			wsActive := wsConnected.Load() && (time.Since(time.Unix(lastTick, 0)) < 5*time.Second)

			if wsActive {
				// WebSocket is healthy, fallback yields to conserve REST rate limits
				continue
			}

			// Fallback triggered: Primary WS is down or silent > 5 seconds
			if time.Since(lastCredsCheck) > 60*time.Second || cachedAppID == "" || cachedToken == "" {
				appID, token, err := dbService.GetBrokerCredentials(ctx)
				if err != nil {
					log.Printf("⚠️ [FYERS REST Fallback] DB Credentials read error: %v\n", err)
				} else {
					cachedAppID = strings.TrimSpace(appID)
					cachedToken = strings.TrimSpace(token)
					lastCredsCheck = time.Now()
				}
			}

			if cachedAppID == "" || cachedToken == "" {
				continue
			}

			url := "https://api-t1.fyers.in/data/quotes?symbols=NSE:NIFTY50-INDEX,NSE:NIFTYBANK-INDEX,BSE:SENSEX-INDEX"
			req, err := http.NewRequestWithContext(ctx, "GET", url, nil)
			if err != nil {
				continue
			}
			req.Header.Set("Authorization", fmt.Sprintf("%s:%s", cachedAppID, cachedToken))

			resp, err := httpClient.Do(req)
			if err != nil {
				continue
			}

			if resp.StatusCode != http.StatusOK {
				resp.Body.Close()
				continue
			}

			var quoteResp fyersQuoteResponse
			err = json.NewDecoder(resp.Body).Decode(&quoteResp)
			resp.Body.Close()
			if err != nil || quoteResp.S != "ok" {
				continue
			}

			for _, item := range quoteResp.D {
				idxName, recognized := symbolToIndex[item.N]
				if !recognized || item.V.Lp <= 0 {
					continue
				}

				v := item.V
				publishIndexQuoteToRedis(ctx, redisService, idxName, item.N, v.Lp, v.Ch, v.Chp, v.HighPrice, v.LowPrice, v.OpenPrice, v.PrevClosePrice, "REST_FALLBACK", prevLTP)
			}
		}
	}
}

// TargetedOptionChainPoller fetches heavy 31-strike option chains on demand or throttled 5-second interval.
func TargetedOptionChainPoller(ctx context.Context, redisService *services.RedisService, dbService *services.DBService) {
	ticker := time.NewTicker(5 * time.Second)
	defer ticker.Stop()

	httpClient := &http.Client{Timeout: 5 * time.Second}
	var cachedAppID, cachedToken string
	lastCredsCheck := time.Time{}
	lastATM := make(map[string]int)

	indexSymbols := map[string]string{
		"NIFTY":     "NSE:NIFTY50-INDEX",
		"BANKNIFTY": "NSE:NIFTYBANK-INDEX",
		"SENSEX":    "BSE:SENSEX-INDEX",
	}

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			if !IsMarketSessionActive() {
				continue
			}

			if time.Since(lastCredsCheck) > 60*time.Second || cachedAppID == "" || cachedToken == "" {
				appID, token, err := dbService.GetBrokerCredentials(ctx)
				if err == nil {
					cachedAppID = strings.TrimSpace(appID)
					cachedToken = strings.TrimSpace(token)
					lastCredsCheck = time.Now()
				}
			}
			if cachedAppID == "" || cachedToken == "" {
				continue
			}

			for idxName, fyersSym := range indexSymbols {
				chainKey := fmt.Sprintf("marmot:fyers:last_known_option_chain:%s", idxName)
				val, err := redisService.Client.Get(ctx, chainKey).Result()
				if err != nil || len(val) == 0 {
					continue
				}

				var spotData map[string]interface{}
				if err := json.Unmarshal([]byte(val), &spotData); err != nil {
					continue
				}

				atmVal, ok := spotData["atm_strike"]
				if !ok {
					continue
				}

				var curATM int
				switch v := atmVal.(type) {
				case float64:
					curATM = int(v)
				case int:
					curATM = v
				}

				if curATM != lastATM[idxName] && curATM > 0 {
					lastATM[idxName] = curATM
					fetchTargetedOptionChain(ctx, httpClient, cachedAppID, cachedToken, redisService, idxName, fyersSym)
				}
			}
		}
	}
}

// fetchTargetedOptionChain calls the FYERS options-chain-v3 endpoint and caches the full 31-strike dataset into Redis.
func fetchTargetedOptionChain(ctx context.Context, client *http.Client, appID, token string, redisService *services.RedisService, idxName, fyersSym string) {
	url := fmt.Sprintf("https://api-t1.fyers.in/data/options-chain-v3?symbol=%s&strikecount=15", fyersSym)
	req, err := http.NewRequestWithContext(ctx, "GET", url, nil)
	if err != nil {
		return
	}
	req.Header.Set("Authorization", fmt.Sprintf("%s:%s", appID, token))

	resp, err := client.Do(req)
	if err != nil {
		return
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusOK {
		var chainData map[string]interface{}
		if err := json.NewDecoder(resp.Body).Decode(&chainData); err == nil && chainData["s"] == "ok" {
			rawBytes, _ := json.Marshal(chainData)
			_ = redisService.Client.Set(ctx, fmt.Sprintf("marmot:fyers:full_option_chain:%s", idxName), rawBytes, 30*time.Second).Err()
			log.Printf("📑 [Targeted Option Chain] Cached 31 strikes for %s via REST\n", idxName)
		}
	}
}

func minDuration(a, b time.Duration) time.Duration {
	if a < b {
		return a
	}
	return b
}

var istMarketLoc = time.FixedZone("IST", 5*3600+1800)

// IsMarketSessionActive checks if the Indian Equity Index session is active (09:00 to 15:45 IST, Mon-Fri).
func IsMarketSessionActive() bool {
	return IsSegmentMarketSessionActive("INDEX")
}

// IsSegmentMarketSessionActive returns true during trading days for the specified market segment.
// Segments:
//   - "INDEX": 09:00 - 15:45 IST (NIFTY, BANKNIFTY, SENSEX)
//   - "FOREX": 08:45 - 17:15 IST (NSE Currency: USDINR, EURINR, GBPINR, JPYINR)
//   - "FOREX_CROSS": 08:45 - 19:45 IST (Cross Currency: EURUSD, GBPUSD, USDJPY)
func IsSegmentMarketSessionActive(segment string) bool {
	now := time.Now().In(istMarketLoc)
	weekday := now.Weekday()
	if weekday == time.Saturday || weekday == time.Sunday {
		return false
	}

	mins := now.Hour()*60 + now.Minute()
	switch strings.ToUpper(segment) {
	case "FOREX", "CURRENCY":
		// NSE Currency Derivatives: 09:00 to 17:00 IST (with 15m buffer: 08:45 to 17:15)
		return mins >= 525 && mins <= 1035
	case "FOREX_CROSS":
		// Cross Currency Pairs: 09:00 to 19:30 IST (with 15m buffer: 08:45 to 19:45)
		return mins >= 525 && mins <= 1185
	case "INDEX", "EQUITY":
		fallthrough
	default:
		// Equity Index: 09:15 to 15:30 IST (with 15m buffer: 09:00 to 15:45)
		return mins >= 540 && mins <= 945
	}
}


