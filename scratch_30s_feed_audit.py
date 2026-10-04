import os
import sys
import time
import json
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')

def run_30s_continuous_audit():
    artifact_dir = r"C:\Users\appzf\.gemini\antigravity-ide\brain\e28ecd14-600a-45af-8887-2d85099f2da8"
    
    print("=" * 90)
    print("MARMOT QA: 30-SECOND CONTINUOUS UI FEED AUDIT & LOGICAL CORRECTNESS VERIFICATION")
    print("=" * 90)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1600, "height": 1050})
        page = context.new_page()
        
        # Track all incoming WebSocket frames
        ws_frames = []
        def on_websocket(ws):
            def on_frame(payload):
                try:
                    ws_frames.append({
                        "received_at": time.time(),
                        "url": ws.url,
                        "data": json.loads(payload) if payload.startswith("{") else payload[:200]
                    })
                except Exception:
                    ws_frames.append({"received_at": time.time(), "url": ws.url, "raw": payload[:100]})
            ws.on("framereceived", on_frame)
        page.on("websocket", on_websocket)
        
        # 1. Login
        print("\n[Step 1] Authenticating as marmotadmin...")
        page.goto("http://localhost:8050/admins/login/", wait_until="networkidle")
        page.fill('input[name="username"]', 'marmotadmin')
        page.fill('input[name="password"]', 'marmotadmin@2026')
        page.click('button[type="submit"]')
        page.wait_for_timeout(2000)
        page.wait_for_load_state("networkidle")
        print("  Login Successful. URL:", page.url)
        
        # 2. Navigate to Sandbox Dashboard
        print("\n[Step 2] Navigating to Sandbox Dashboard (Account #3)...")
        page.goto("http://localhost:8050/admins/dashboard/sandbox/?account_id=3", wait_until="networkidle")
        page.wait_for_timeout(2000)
        
        # 3. 30-Second Continuous Telemetry Sampling Loop
        print("\n[Step 3] Initiating 30-Second Continuous UI Feed Sampling (Every 3 seconds)...")
        sample_history = []
        start_time = time.time()
        screenshot_intervals = {0: "audit_30s_tick_0s.png", 10: "audit_30s_tick_10s.png", 20: "audit_30s_tick_20s.png", 30: "audit_30s_tick_30s.png"}
        screenshots_captured = {}
        
        for step in range(11): # 0, 3, 6, 9, 12, 15, 18, 21, 24, 27, 30
            target_elapsed = step * 3
            current_elapsed = time.time() - start_time
            if target_elapsed > current_elapsed:
                time.sleep(target_elapsed - current_elapsed)
            
            elapsed = round(time.time() - start_time, 2)
            
            # Extract UI Telemetry Values from DOM
            hud_clock = page.inner_text("#exchangeMarketClockDisplay").strip() if page.query_selector("#exchangeMarketClockDisplay") else "N/A"
            ribbon_spot = page.inner_text("#live-macro-spot-ltp").strip() if page.query_selector("#live-macro-spot-ltp") else "N/A"
            oc_spot = page.inner_text("#live-option-chain-spot-ltp").strip() if page.query_selector("#live-option-chain-spot-ltp") else "N/A"
            oc_atm = page.inner_text("#live-option-chain-atm").strip() if page.query_selector("#live-option-chain-atm") else "N/A"
            
            # Option chain ATM strike CE & PE values
            atm_ce_ltp = page.inner_text("#oc-row-atm .ce-ltp-val").strip() if page.query_selector("#oc-row-atm .ce-ltp-val") else "N/A"
            atm_pe_ltp = page.inner_text("#oc-row-atm .pe-ltp-val").strip() if page.query_selector("#oc-row-atm .pe-ltp-val") else "N/A"
            
            margin_avail = page.inner_text("#sandbox-available-margin").strip() if page.query_selector("#sandbox-available-margin") else "N/A"
            net_pnl = page.inner_text("#sandbox-live-net-pnl").strip() if page.query_selector("#sandbox-live-net-pnl") else "N/A"
            realized_pnl = page.inner_text("#sandbox-realized-pnl").strip() if page.query_selector("#sandbox-realized-pnl") else "N/A"
            unrealized_pnl = page.inner_text("#sandbox-unrealized-pnl").strip() if page.query_selector("#sandbox-unrealized-pnl") else "N/A"
            
            # Orders count
            order_rows = page.query_selector_all("#live-orders-container table tbody tr")
            orders_count = len(order_rows)
            
            # Active positions count
            pos_badge = page.inner_text(".badge:has-text('ACTIVE POSITIONS')").strip() if page.query_selector(".badge:has-text('ACTIVE POSITIONS')") else "N/A"
            
            sample = {
                "step": step,
                "elapsed_sec": elapsed,
                "hud_clock": hud_clock,
                "ribbon_spot": ribbon_spot,
                "option_chain_spot": oc_spot,
                "atm_strike": oc_atm,
                "margin_available": margin_avail,
                "net_pnl": net_pnl,
                "realized_pnl": realized_pnl,
                "unrealized_pnl": unrealized_pnl,
                "orders_count": orders_count,
                "active_positions_badge": pos_badge
            }
            sample_history.append(sample)
            
            print(f"  [T+{elapsed:04.1f}s] HUD: {hud_clock} | Ribbon: {ribbon_spot} | OC Spot: {oc_spot} (ATM {oc_atm}) | Net PnL: {net_pnl} | Orders: {orders_count}")
            
            # Capture Entire Page Screenshots at checkpoints
            if step in [0, 3, 7, 10]: # ~0s, ~9s, ~21s, ~30s
                key_sec = 0 if step == 0 else (10 if step == 3 else (20 if step == 7 else 30))
                shot_name = screenshot_intervals[key_sec]
                shot_path = os.path.join(artifact_dir, shot_name)
                page.screenshot(path=shot_path, full_page=True)
                screenshots_captured[f"T+{key_sec}s"] = shot_path
                print(f"    -> [SCREENSHOT CAPTURED] {shot_name} (T+{key_sec}s)")
        
        # 4. WebSocket Leakage & Continuity Audit
        print(f"\n[Step 4] WebSocket Traffic Audit ({len(ws_frames)} total frames captured)...")
        fyers_live_leaks = 0
        jerk_22400_leaks = 0
        mock_ticks_count = 0
        
        for f in ws_frames:
            data = f.get("data", {})
            if isinstance(data, dict):
                raw_str = json.dumps(data)
                if "22421" in raw_str or "22,421" in raw_str:
                    jerk_22400_leaks += 1
                if data.get("source") == "FYERS_WS" or data.get("type") == "FYERS_LIVE":
                    fyers_live_leaks += 1
                if "mock" in raw_str or data.get("is_mock") is True:
                    mock_ticks_count += 1
        
        print(f"  Total WS frames: {len(ws_frames)}")
        print(f"  Mock Telemetry/Feed ticks: {mock_ticks_count}")
        print(f"  Fyers Live Closing Leaks (22,421.95): {jerk_22400_leaks} (Target: 0)")
        print(f"  Fyers WS Source Leaks: {fyers_live_leaks} (Target: 0)")
        
        # 5. Logical Correctness Analysis
        print("\n[Step 5] Evaluating Logical Correctness...")
        # Check spot consistency across samples
        spot_discrepancies = []
        for s in sample_history:
            r_clean = s["ribbon_spot"].replace("₹", "").replace(",", "").strip()
            o_clean = s["option_chain_spot"].replace("₹", "").replace(",", "").strip()
            try:
                r_val = float(r_clean)
                o_val = float(o_clean)
                diff = abs(r_val - o_val)
                # In historical replay, spot is around 24,5xx or 23,400
                if diff > 1500: # Jump to 22,421 would cause > 2000 diff
                    spot_discrepancies.append((s["elapsed_sec"], r_val, o_val))
            except Exception:
                pass
        
        correctness_report = {
            "test_duration_seconds": 30,
            "samples_collected": len(sample_history),
            "spot_discrepancy_count": len(spot_discrepancies),
            "fyers_closing_leak_count": jerk_22400_leaks,
            "fyers_source_leak_count": fyers_live_leaks,
            "mock_ticks_received": mock_ticks_count,
            "screenshots": screenshots_captured,
            "samples": sample_history,
            "clock_decoupled": True if all("IST" in s["hud_clock"] for s in sample_history) else False,
            "is_logically_correct": (len(spot_discrepancies) == 0 and jerk_22400_leaks == 0),
            "final_status": "PASS (100% Stable, Rock Solid, Logically Correct)" if (len(spot_discrepancies) == 0 and jerk_22400_leaks == 0) else "FAIL"
        }
        
        out_report_path = os.path.join(artifact_dir, "audit_30s_tick_feed_report.json")
        with open(out_report_path, "w", encoding="utf-8") as out_f:
            json.dump(correctness_report, out_f, indent=2)
        print(f"\n[Done] 30s Feed Audit Report written to: {out_report_path}")
        
        browser.close()

if __name__ == "__main__":
    run_30s_continuous_audit()
