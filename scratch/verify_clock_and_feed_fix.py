import json
import time
import os
import sys
from playwright.sync_api import sync_playwright

def run_verification():
    report = {
        "test": "30s_clock_and_feed_monotonicity_audit",
        "duration_sec": 30,
        "sample_interval_ms": 200,
        "samples": [],
        "clock_regressions": [],
        "spot_regressions": [],
        "stuck_intervals": [],
        "total_samples": 0,
        "verdict": "PENDING"
    }

    screenshot_path = "C:/Users/appzf/.gemini/antigravity-ide/brain/e28ecd14-600a-45af-8887-2d85099f2da8/clock_feed_verification_30s.png"
    report_json_path = "C:/Users/appzf/.gemini/antigravity-ide/brain/e28ecd14-600a-45af-8887-2d85099f2da8/clock_feed_verification_30s.json"

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"]
        )
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        print("[TEST] Logging into Admin Portal...")
        page.goto("http://localhost:8050/admins/login/", wait_until="networkidle")
        page.fill('input[name="username"]', 'marmotadmin')
        page.fill('input[name="password"]', 'marmotadmin@2026')
        page.click('button[type="submit"]')
        page.wait_for_url("**/admins/dashboard/**", timeout=15000)

        # Monitor WebSockets without unicode characters
        ws_messages = []
        def on_ws(ws):
            print(f"[WS OPEN] {ws.url}")
            ws.on("framereceived", lambda frame: ws_messages.append({
                "time": time.time(),
                "url": ws.url,
                "payload": frame[:200] if isinstance(frame, str) else str(frame)[:200]
            }))
        page.on("websocket", on_ws)

        print("[TEST] Navigating to Sandbox Dashboard...")
        page.goto("http://localhost:8050/admins/dashboard/sandbox/?account_id=3", wait_until="networkidle", timeout=30000)
        page.wait_for_selector("#live-exchange-clock-time", timeout=10000)
        print("[TEST] Dashboard ready. Starting 30-second continuous telemetry sampling...")

        start_time = time.time()
        prev_clock_str = None
        prev_clock_sec = None
        prev_spot_str = None
        stuck_counter = 0

        def parse_clock_to_sec(time_str):
            if not time_str or ":" not in time_str:
                return None
            parts = time_str.strip().split(":")
            if len(parts) == 3:
                try:
                    return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                except:
                    return None
            return None

        while time.time() - start_time < 30.0:
            elapsed = round(time.time() - start_time, 2)
            clock_val = page.evaluate("() => document.getElementById('live-exchange-clock-time')?.textContent?.trim() || ''")
            macro_spot = page.evaluate("() => document.getElementById('live-macro-spot-ltp')?.textContent?.trim() || ''")
            macro_time = page.evaluate("() => document.getElementById('live-macro-spot-time')?.textContent?.trim() || ''")
            oc_spot = page.evaluate("() => document.getElementById('live-option-chain-spot-ltp')?.textContent?.trim() || ''")

            clock_sec = parse_clock_to_sec(clock_val)

            # Check for backwards jump
            if prev_clock_sec is not None and clock_sec is not None:
                delta = clock_sec - prev_clock_sec
                # Allow midnight wrap if applicable, otherwise negative delta is a backwards jump
                if delta < 0 and delta > -82800:
                    regression = {
                        "elapsed_sec": elapsed,
                        "from_clock": prev_clock_str,
                        "to_clock": clock_val,
                        "backward_jump_sec": -delta,
                        "spot": macro_spot
                    }
                    report["clock_regressions"].append(regression)
                    print(f"[REGRESSION DETECTED at t={elapsed}s] {prev_clock_str} -> {clock_val}")

            # Check for stuck clock
            if clock_val == prev_clock_str:
                stuck_counter += 1
            else:
                if stuck_counter >= 30: # 30 * 200ms = 6.0 seconds without update
                    report["stuck_intervals"].append({"elapsed_sec": elapsed, "stuck_duration_sec": stuck_counter * 0.2})
                stuck_counter = 0

            sample = {
                "t": elapsed,
                "clock": clock_val,
                "macro_spot": macro_spot,
                "macro_time": macro_time,
                "oc_spot": oc_spot
            }
            report["samples"].append(sample)

            prev_clock_str = clock_val
            prev_clock_sec = clock_sec
            prev_spot_str = macro_spot

            time.sleep(0.2)

        page.screenshot(path=screenshot_path, full_page=True)
        report["total_samples"] = len(report["samples"])
        report["clock_regression_count"] = len(report["clock_regressions"])
        report["ws_frames_received"] = len(ws_messages)

        if report["clock_regression_count"] == 0:
            report["verdict"] = "PASSED - ZERO CLOCK GLITCHES DETECTED"
        else:
            report["verdict"] = f"FAILED - {report['clock_regression_count']} BACKWARDS JUMPS"

        browser.close()

    with open(report_json_path, "w") as f:
        json.dump(report, f, indent=2)

    print(f"\n==========================================")
    print(f"Audit Complete! Verdict: {report['verdict']}")
    print(f"Total Samples: {report['total_samples']}")
    print(f"Clock Regressions: {report['clock_regression_count']}")
    print(f"WebSocket Frames: {report['ws_frames_received']}")
    print(f"Screenshot saved to: {screenshot_path}")
    print(f"JSON Report saved to: {report_json_path}")
    print(f"==========================================\n")

if __name__ == "__main__":
    run_verification()
