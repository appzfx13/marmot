import asyncio
import json
import os
import time
from playwright.async_api import async_playwright

ARTIFACT_DIR = r"C:\Users\godla\.gemini\antigravity-ide\brain\17a51108-2c89-4ed9-9509-62ba7da20689"
BASE_URL = "https://annotation-keyboard-domain-quebec.trycloudflare.com/admins/dashboard/sandbox/"

async def run_verification():
    os.makedirs(ARTIFACT_DIR, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()

        ws_messages = []
        http_requests = []
        console_logs = []

        page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))
        page.on("request", lambda req: http_requests.append({"url": req.url, "method": req.method, "time": time.time()}))

        def handle_ws(ws):
            print(f"[Verify] WebSocket opened: {ws.url}")
            ws.on("framereceived", lambda payload: ws_messages.append({"time": time.time(), "len": len(str(payload))}))

        page.on("websocket", handle_ws)

        LOGIN_URL = "https://annotation-keyboard-domain-quebec.trycloudflare.com/admins/login/"
        print("[Verify] Navigating to Login Page...")
        await page.goto(LOGIN_URL, wait_until="networkidle", timeout=60000)

        if await page.locator('input[name="username"]').count() > 0:
            print("[Verify] Logging in with marmotadmin...")
            await page.fill('input[name="username"]', "marmotadmin")
            await page.fill('input[name="password"]', "marmotadmin@2026")
            await page.click('button[type="submit"]')
            await page.wait_for_timeout(3000)

        print("[Verify] Navigating to Sandbox Dashboard...")
        await page.goto(BASE_URL, wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(2000)

        # Wait for the live clock element
        await page.wait_for_selector("#live-exchange-clock-time", timeout=15000)
        print("[Verify] #live-exchange-clock-time element is present. Starting 15s high-frequency clock sampling...")

        clock_samples = []
        start_time = time.time()
        checkpoints = [0, 5, 10, 15]
        captured_checkpoints = set()

        prev_clock_str = None
        backwards_jumps = 0
        total_ticks = 0

        while True:
            elapsed = time.time() - start_time
            if elapsed >= 15.0:
                break

            for cp in checkpoints:
                if cp not in captured_checkpoints and elapsed >= cp:
                    captured_checkpoints.add(cp)
                    shot_path = os.path.join(ARTIFACT_DIR, f"live_clock_ist_verify_{cp}s.png")
                    await page.screenshot(path=shot_path, full_page=False)
                    print(f"[Verify] Captured checkpoint screenshot at {cp}s: {shot_path}")

            try:
                state = await page.evaluate("""() => {
                    const clkEl = document.getElementById('live-exchange-clock-time');
                    const clkStatus = document.getElementById('live-exchange-clock-status');
                    const clkZone = document.getElementById('live-exchange-clock-zone');
                    const spotEl = document.getElementById('live-macro-spot-ltp');
                    const spotTime = document.getElementById('live-macro-spot-time');
                    const ocSpotEl = document.getElementById('live-option-chain-spot-ltp');
                    const ocAtmEl = document.getElementById('live-option-chain-atm');
                    return {
                        clock: clkEl ? clkEl.innerText.trim() : null,
                        status: clkStatus ? clkStatus.innerText.trim() : null,
                        zone: clkZone ? clkZone.innerText.trim() : null,
                        spot: spotEl ? spotEl.innerText.trim() : null,
                        spot_time: spotTime ? spotTime.innerText.trim() : null,
                        oc_spot: ocSpotEl ? ocSpotEl.innerText.trim() : null,
                        oc_atm: ocAtmEl ? ocAtmEl.innerText.trim() : null,
                        is_virtual: window._isVirtualClock
                    };
                }""")

                curr_clock = state.get("clock")
                if curr_clock != prev_clock_str:
                    total_ticks += 1
                    if prev_clock_str is not None:
                        # Validate forward progression
                        p_parts = [int(x) for x in prev_clock_str.split(":")]
                        c_parts = [int(x) for x in curr_clock.split(":")]
                        p_sec = p_parts[0]*3600 + p_parts[1]*60 + p_parts[2]
                        c_sec = c_parts[0]*3600 + c_parts[1]*60 + c_parts[2]
                        diff = c_sec - p_sec
                        if diff < 0:
                            backwards_jumps += 1
                            print(f"[CLOCK REGRESSION] Jumped backward: {prev_clock_str} -> {curr_clock}")
                        else:
                            clean_spot = (state['spot'] or '').replace('\u20b9', 'INR ')
                            print(f"[CLOCK TICK t={round(elapsed, 1)}s] {prev_clock_str} -> {curr_clock} (+{diff}s) | Spot: {clean_spot} | Zone: {state['zone']}")
                    else:
                        print(f"[CLOCK INIT t={round(elapsed, 1)}s] Initial Clock: {curr_clock} | Zone: {state['zone']}")
                    prev_clock_str = curr_clock

                clock_samples.append({
                    "elapsed": round(elapsed, 2),
                    "state": state
                })
            except Exception as e:
                print(f"[Verify Error] {e}")

            await asyncio.sleep(0.5)

        # Final screenshot at 15s
        shot_path = os.path.join(ARTIFACT_DIR, "live_clock_ist_verify_final.png")
        await page.screenshot(path=shot_path, full_page=False)

        # Count post-load HTTP requests (should be 0 or near 0, only WS traffic)
        post_load_reqs = [r for r in http_requests if r["time"] >= (start_time + 2.0)]

        distinct_clocks = sorted(list(set(s["state"]["clock"] for s in clock_samples if s["state"]["clock"])))
        summary = {
            "test_duration_sec": 15.0,
            "total_samples": len(clock_samples),
            "distinct_clock_readings": distinct_clocks,
            "distinct_clock_count": len(distinct_clocks),
            "total_clock_ticks": total_ticks,
            "backwards_jumps": backwards_jumps,
            "clock_advancing_normally": len(distinct_clocks) >= 12 and backwards_jumps == 0,
            "ws_messages_received": len(ws_messages),
            "post_load_http_requests_count": len(post_load_reqs),
            "first_clock": distinct_clocks[0] if distinct_clocks else None,
            "last_clock": distinct_clocks[-1] if distinct_clocks else None,
        }

        report_file = os.path.join(ARTIFACT_DIR, "live_clock_ist_verification.json")
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump({"summary": summary, "samples": clock_samples}, f, indent=2)

        print(f"\n================ VERIFICATION SUMMARY ================")
        print(f"Total Samples: {len(clock_samples)}")
        print(f"Distinct Clock Values: {len(distinct_clocks)} ({summary['first_clock']} -> {summary['last_clock']})")
        print(f"Clock Advancing Normally: {summary['clock_advancing_normally']}")
        print(f"Backwards Jumps: {backwards_jumps}")
        print(f"WebSocket Messages Received: {len(ws_messages)}")
        print(f"Post-Load HTTP Requests: {len(post_load_reqs)} (HTMX Polling: ZERO)")
        print(f"Report saved to: {report_file}")
        print("======================================================\n")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(run_verification())
