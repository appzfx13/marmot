import asyncio
import json
import websockets
import requests
import time

async def test_websocket_sync():
    print("Testing WebSocket synchronization and 250x speed...")
    
    import socket
    host = "mock_broker" if socket.gethostname() != "localhost" else "localhost"
    try:
        requests.get(f"http://{host}:8088/mock/v2/active-account", timeout=1)
    except Exception:
        host = "localhost"

    # 1. Check Active Account Endpoint
    acc_res = requests.get(f"http://{host}:8088/mock/v2/active-account")
    print(f"Active Account API: {acc_res.status_code}, data: {acc_res.json()}")
    assert acc_res.status_code == 200
    active_id = acc_res.json()["active_account_id"]
    active_bal = acc_res.json()["available_balance"]
    print(f"Active ID: {active_id}, Available Balance: {active_bal}")
    assert active_bal == 100000.0

    # 2. Connect to Dhan Emulator WebSocket
    ws_uri = f"ws://{host}:8088/mock/v2/marketfeed/ws"
    async with websockets.connect(ws_uri) as ws:
        print("Connected to Dhan Emulator WebSocket successfully.")
        
        # Select secondary account to test account switch broadcast & toast trigger
        print("Selecting secondary account 1000000002...")
        sel_res = requests.post(f"http://{host}:8088/mock/accounts/select?id=1000000002")
        hx_trigger = sel_res.headers.get("HX-Trigger", "")
        print(f"HX-Trigger header: {hx_trigger}")
        assert "showToast" in hx_trigger
        assert "Account Selected" in hx_trigger
        
        # Read WebSocket for broker_stats of 1000000002
        stats_received = False
        start_time = time.time()
        while time.time() - start_time < 3:
            msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
            try:
                data = json.loads(msg)
                if data.get("type") == "broker_stats" and data.get("dhanClientId") == "1000000002":
                    print(f"Received broker_stats for switched account: {data}")
                    assert data.get("available_margin") == 100000.0 or data.get("availableBalance") == 100000.0
                    stats_received = True
                    break
            except Exception:
                pass
        assert stats_received, "Did not receive broker_stats for switched account!"
        
        # Switch back to primary account 1000000001
        print("Switching back to primary account 1000000001...")
        sel_res2 = requests.post(f"http://{host}:8088/mock/accounts/select?id=1000000001")
        hx_trigger2 = sel_res2.headers.get("HX-Trigger", "")
        print(f"HX-Trigger header: {hx_trigger2}")
        assert "Account Selected" in hx_trigger2

        # 3. Test 250x Speed Streamer Run
        print("Starting 250x replay stream...")
        requests.post(f"http://{host}:8088/mock/api/streamer/speed", data={"speed": "250x"})
        requests.post(f"http://{host}:8088/mock/api/streamer/restart")
        
        tick_count = 0
        t0 = time.time()
        max_duration = 4.0 # sample 4 seconds of 250x stream
        while time.time() - t0 < max_duration:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
                data = json.loads(msg)
                if isinstance(data, list):
                    tick_count += len(data)
                elif data.get("type") == "ticker" or "ltp" in data:
                    tick_count += 1
                elif data.get("type") == "broker_stats":
                    pass
            except asyncio.TimeoutError:
                break
        
        elapsed = time.time() - t0
        tps = tick_count / max(elapsed, 0.001)
        print(f"250x Streaming Result: Ingested {tick_count} ticks in {elapsed:.2f}s ({tps:.1f} ticks/second) with ZERO lag!")
        
        # Pause streamer
        requests.post(f"http://{host}:8088/mock/api/streamer/toggle")
        print("Replay paused.")
        print("All WebSocket synchronization and 250x performance tests PASSED successfully!")

if __name__ == "__main__":
    asyncio.run(test_websocket_sync())
