import requests
import json
import time
import redis

def run_test():
    r = redis.Redis(host='redis_broker', port=6379, db=0)

    # 1. Set streamer speed to 5x
    resp_speed = requests.post('http://mock_broker:8088/mock/api/streamer/speed?speed=5', timeout=5)
    print("Speed set response:", resp_speed.status_code)

    # 2. Restart streamer from beginning
    resp_restart = requests.post('http://mock_broker:8088/mock/api/streamer/restart', timeout=5)
    print("Streamer restart response:", resp_restart.status_code)

    # 3. Monitor strategy_602 orders
    start_time = time.time()
    print("Monitoring strategy_602 telemetry for 4 sequential mock orders...")

    selected_orders = []
    while time.time() - start_time < 90:
        raw = r.get("marmot:mock:telemetry:strategy:602")
        if raw:
            data = json.loads(raw)
            orders = data.get("orders", [])
            spot = data.get("spot_price", 0)
            pnl = data.get("live_net_pnl", 0)
            eval_time = data.get("last_eval_time", "")
            print(f"[{time.time()-start_time:.1f}s] Orders: {len(orders)} | Spot: {spot} | Eval Time: {eval_time} | PnL: ₹{pnl:,.2f}")
            if len(orders) >= 4:
                selected_orders = orders[:4]
                print("\nSUCCESS: Captured 4 sequential mock orders!")
                break
        time.sleep(2)

    if not selected_orders:
        raw = r.get("marmot:mock:telemetry:strategy:602")
        if raw:
            data = json.loads(raw)
            selected_orders = data.get("orders", [])

    print("\n" + "="*90)
    print("4 SEQUENTIAL MOCK ORDERS EXECUTION AUDIT TABLE")
    print("="*90)
    print(f"{'#':<3} | {'Order ID':<14} | {'Feed Timestamp':<15} | {'Symbol':<24} | {'Side':<4} | {'Price':<8} | {'Status':<8}")
    print("-" * 90)
    for idx, o in enumerate(selected_orders[:4], 1):
        oid = o.get("order_id") or o.get("orderId")
        sym = o.get("trading_symbol") or o.get("tradingSymbol")
        side = o.get("transaction_type") or o.get("transactionType")
        price = o.get("price") or o.get("averagePrice") or 0.0
        status = o.get("order_status") or o.get("orderStatus")
        exec_time = o.get("execution_time") or o.get("create_time") or o.get("signal_time") or ""
        print(f"{idx:<3} | {oid:<14} | {exec_time:<15} | {sym:<24} | {side:<4} | ₹{float(price):<7.2f} | {status:<8}")

if __name__ == "__main__":
    run_test()
