# Dhan Mock Broker — API Reference

> **Service:** `dhan-emulator` | **Port:** `8088` | **Container:** `dhan_mock_broker`
>
> Import `MOCK_BROKER_API.postman_collection.json` into Postman for interactive testing.

---

## Architecture Overview

```
Marmot Go Engine ──POST /v2/orders──► dhan-emulator (:8088)
                                           │
                          ┌────────────────┼────────────────┐
                          │                │                │
                    MatchingEngine    ParquetStreamer   HTTP Router
                    (order book,      (tick replay,    (REST + WS
                     SL/TP, MTM)      WS broadcast)    handlers)
                          │                │
                          └─────postback───► Marmot Django (:8000)
                                           │
                               WebSocket broadcast to Dashboard
```

---

## Base URLs

| Environment | Base URL |
|---|---|
| Local (direct) | `http://localhost:8088` |
| Via Nginx proxy | `http://localhost/mock-broker/` |
| WebSocket | `ws://localhost:8088/v2/marketfeed/ws` |

---

## Authentication

All Dhan v2 endpoints read the active account from the `client-id` HTTP header.

```
client-id: 1000000001
```

If omitted, the currently selected active account is used (set via `/mock/accounts/select`).

---

## Dhan v2 REST API

These endpoints mirror the real Dhan API v2 contract. The Go strategy engine targets these.

### Orders

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/v2/orders` | Place new order → returns `orderId` + `PENDING` |
| `GET`  | `/v2/orders` | List all orders for the client |
| `GET`  | `/v2/orders/{orderId}` | Get single order by ID |
| `PUT`  | `/v2/orders/{orderId}` | Modify a PENDING order (price, triggerPrice, qty) |
| `DELETE` | `/v2/orders/{orderId}` | Cancel a PENDING order |

**Order lifecycle:**
```
PlaceOrder → PENDING
    ↓ (35-50ms async)
    ├─ TRADED    → postback fired to Marmot
    ├─ REJECTED  → postback fired to Marmot (margin / chaos error)
    └─ CANCELLED → postback fired to Marmot (manual cancel / kill-switch)
```

**SL/TP auto square-off:**  
When a position has `StopLoss` or `TakeProfit` set, `IngestTick` checks every incoming tick and calls `squareOffPositionAutoLocked` when price crosses. A `TRADED` exit order is created and a `SL_HIT` / `TP_HIT` postback is dispatched.

**Order Request Body (POST /v2/orders):**
```json
{
  "dhanClientId":    "1000000001",
  "correlationId":   "strat_nifty_leg1",
  "transactionType": "BUY",
  "exchangeSegment": "NSE_FNO",
  "productType":     "INTRADAY",
  "orderType":       "MARKET",
  "validity":        "DAY",
  "securityId":      "49081",
  "tradingSymbol":   "NIFTY24SEP24500CE",
  "quantity":        25,
  "price":           0,
  "triggerPrice":    0,
  "boProfitValue":   200,
  "boStopLossValue": 100
}
```

> `boProfitValue` and `boStopLossValue` set Take-Profit and Stop-Loss on the resulting position for automatic square-off on price cross.

**Order Response:**
```json
{ "orderId": "DHN17893015880001", "orderStatus": "PENDING", "orderTimestamp": "2024-09-13 09:15:00" }
```

**Order Types:**
| `orderType` | Behavior |
|---|---|
| `MARKET` | Fills immediately at current LTP |
| `LIMIT` | Fills immediately at limit price (mock doesn't queue by book) |
| `STOP_LOSS` | Stays PENDING until tick crosses `triggerPrice` |
| `STOP_LOSS_MARKET` | Same — fills at LTP when triggered |

---

### Fund Limit

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/v2/fundlimit` | Virtual account balance metrics |

```json
{
  "dhanClientId":        "1000000001",
  "availabelBalance":    98500.0,
  "sodLimit":            100000.0,
  "collateralAmount":    0,
  "receiveableAmount":   0,
  "utilizedAmount":      1500.0,
  "blockedPayoutAmount": 0,
  "withdrawableBalance": 98500.0
}
```

---

### Positions

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/v2/positions` | All positions with real-time MTM |

```json
[{
  "dhanClientId":    "1000000001",
  "tradingSymbol":   "NIFTY24SEP24500CE",
  "securityId":      "49081",
  "positionType":    "LONG",
  "buyAvg":          120.5,
  "buyQty":          25,
  "netQty":          25,
  "realizedProfit":  0,
  "unrealizedProfit": -45.5,
  "stopLoss":        100.0,
  "takeProfit":      200.0,
  "entryTime":       "09:15:32"
}]
```

Position types: `LONG`, `SHORT`, `CLOSED`

---

### Holdings

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/v2/holdings` | Always returns `[]` (FNO intraday only) |

---

### Option Chain

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/v2/optionchain?index=NIFTY` | Live option chain from current Parquet tick |

Supported index values: `NIFTY`, `BANKNIFTY`, `FINNIFTY`, `MIDCPNIFTY`, `SENSEX`

---

## Active Account Endpoint

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/mock/v2/active-account` | Active account telemetry for Marmot dashboard sync |

```json
{
  "success":           true,
  "active_account_id": "1000000001",
  "account_name":      "Primary Algorithmic Trading",
  "broker":            "Dhan",
  "available_balance": 98500.0,
  "sod_limit":         100000.0,
  "utilized_margin":   1500.0
}
```

---

## Account Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/mock/accounts/select?id={id}` | Set active account |
| `POST` | `/mock/accounts/create` | Create new isolated account |
| `POST` | `/mock/accounts/update` | Update name/broker/balance |
| `POST` | `/mock/accounts/delete?id={id}` | Delete account (no open positions) |
| `POST` | `/mock/api/funds/adjust` | Deposit / withdraw virtual funds |

**Adjust Funds body:** `amount=50000` (positive = deposit, negative = withdraw)

**Create Account body:**
```
id=1000000003
name=Swing Strategy Beta
broker=Dhan
initialBalance=200000
```

---

## Streamer Control

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET`  | `/mock/api/streamer/files` | List available Parquet datasets |
| `POST` | `/mock/api/streamer/select?file={path}` | Select dataset (e.g. `1/48/dataset.parquet`) |
| `POST` | `/mock/api/streamer/toggle` | Play / Pause toggle |
| `POST` | `/mock/api/streamer/restart` | Rewind to row 0 and play |
| `POST` | `/mock/api/streamer/speed?val={n}` | Set replay speed (1, 5, 10, 25, 50, 100, 250) |
| `POST` | `/mock/api/tick` | Inject a synthetic tick manually |

**Manual Tick body:**
```json
{
  "securityId":    "49081",
  "tradingSymbol": "NIFTY24SEP24500CE",
  "ltp":    95.0,
  "open":   110.0,
  "high":   125.0,
  "low":    90.0,
  "volume": 12500
}
```

Use manual tick to trigger SL/TP without waiting for Parquet replay.

---

## Risk Controls

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/mock/api/kill-switch` | Cancel ALL pending orders (fires CANCELLED postbacks) |
| `POST` | `/mock/api/session/clear?account={id}` | Reset orders/positions/balance to initial |
| `POST` | `/mock/api/chaos` | Configure chaos simulation |

**Chaos Config body:**
```
mode=NORMAL
rps=100
```

| Mode | Effect |
|---|---|
| `NORMAL` | Standard operation |
| `DROP_WEBHOOKS` | Silently drops all postback webhooks to Marmot |
| `DELAY_WEBHOOKS` | Delays all postbacks by 6 seconds |

> **Note:** The rate limiter (`rps`) no longer applies to order placement. Orders are never rate-limited. `rps` only affects other API calls.

---

## Dashboard & Analytics (HTMX Partials)

| Endpoint | Description |
|----------|-------------|
| `GET /mock/dashboard` | Full dashboard HTML (open in browser) |
| `GET /mock/dashboard/funds` | Available balance widget |
| `GET /mock/dashboard/positions` | Position book table |
| `GET /mock/dashboard/orders` | Order log table |
| `GET /mock/dashboard/progress` | Replay progress bar (sends `HX-Trigger: replayCompleted` at EOF) |
| `GET /mock/dashboard/controls` | Dataset selector + play controls |
| `GET /mock/dashboard/summary?account={id}` | Session performance analytics |
| `GET /mock/dashboard/option-chain?index={idx}` | Option chain table |
| `GET /mock/dashboard/streamer-widget` | Live index spot + strikes widget |

---

## WebSocket

```
ws://localhost:8088/v2/marketfeed/ws
ws://localhost:8088/mock/v2/marketfeed/ws
```

One persistent connection receives **three types of JSON messages**:

### 1. MarketTick (every Parquet row / synthetic tick)
```json
{
  "securityId":    "49081",
  "tradingSymbol": "NIFTY24SEP24500CE",
  "ltp":    120.5,
  "open":   110.0,
  "high":   125.0,
  "low":    90.0,
  "close":  115.0,
  "volume": 15000,
  "oi":     45000,
  "timestamp": "2024-09-13T09:15:30Z"
}
```

### 2. broker_stats (throttled to 250ms, on MTM or account change)
```json
{
  "type":                 "broker_stats",
  "dhanClientId":         "1000000001",
  "availableBalance":     98500.0,
  "available_margin":     98500.0,
  "utilizedMargin":       1500.0,
  "realizedProfit":       250.0,
  "realized_pnl":         250.0,
  "unrealizedProfit":    -45.5,
  "liveNetPnL":           204.5,
  "live_net_pnl":         204.5,
  "openPositionsCount":   1,
  "open_positions":       1,
  "closedPositionsCount": 2,
  "totalOrdersCount":     5,
  "total_orders":         5,
  "tradedOrdersCount":    4,
  "pendingOrdersCount":   1
}
```

### 3. broker_order_event (on every order state change)
```json
{
  "type":            "broker_order_event",
  "dhanClientId":    "1000000001",
  "orderId":         "DHN17893015880001",
  "status":          "TRADED",
  "tradingSymbol":   "NIFTY24SEP24500CE",
  "transactionType": "BUY",
  "price":           120.5,
  "quantity":        25,
  "event":           "",
  "legName":         "SL_HIT"
}
```

---

## Postback Webhook (Marmot ← Mock Broker)

The broker fires `POST http://web:8000/api/mock/dhan/postback/` on every order state change.

```json
{
  "dhanClientId":    "1000000001",
  "orderId":         "DHN17893015880001",
  "exchangeOrderId": "NSE17893015880042",
  "correlationId":   "strat_nifty_leg1",
  "orderStatus":     "TRADED",
  "transactionType": "BUY",
  "exchangeSegment": "NSE_FNO",
  "productType":     "INTRADAY",
  "orderType":       "MARKET",
  "validity":        "DAY",
  "tradingSymbol":   "strat_nifty_leg1",
  "securityId":      "49081",
  "quantity":        25,
  "price":           0,
  "triggerPrice":    0,
  "legName":         "",
  "createTime":      "2024-09-13 09:15:00",
  "updateTime":      "2024-09-13 09:15:00",
  "exchangeTime":    "2024-09-13 09:15:00",
  "tradedPrice":     120.5,
  "tradedQuantity":  25,
  "rejectionReason": ""
}
```

---

## Bug Fixes Applied (v1.1.0)

| # | Bug | Fix |
|---|-----|-----|
| 1 | **Concurrent WS write panic** — `HandleWebSocket` wrote initial snapshot without `writeMu`; concurrent `BroadcastTick` caused gorilla panic and container restart | Wrapped initial write in `ps.writeMu.Lock()`/`Unlock()` |
| 2 | **SL/TP double-trigger** — same pending SL order could fire multiple times across successive ticks before goroutine had a chance to mark it TRADED | Pre-mark `ord.Status = "TRADED"` inside `IngestTick` write-lock before goroutine launch; guard in `executeOrderAsync` changed to `FilledQty > 0` |
| 3 | **Rate limiter blocking 250x trades** — default 20 RPS token bucket was rejecting burst orders at high replay speeds with HTTP 429 | Removed `AllowRequest()` check from `handleOrders`; order placement is never rate-limited |
