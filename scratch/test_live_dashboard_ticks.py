import os
import sys
import time
import json
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')

artifact_dir = r"C:\Users\godla\.gemini\antigravity-ide\brain\49f0315a-ed2c-4efb-8fd9-52818c554eb9"
screenshots_dir = os.path.join(artifact_dir, "verified_screenshots")
os.makedirs(screenshots_dir, exist_ok=True)

ws_messages = []
console_logs = []
option_chain_snaps = []

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1600, 'height': 1000})
        page = context.new_page()

        def on_console(msg):
            text = f"[{msg.type}] {msg.text}"
            console_logs.append(text)
            if 'Option' in text or 'WS' in text or 'Tick' in text or 'error' in msg.type.lower():
                print(f"CONSOLE: {text}")

        page.on("console", on_console)

        def on_websocket(ws):
            print(f"--> WebSocket opened: {ws.url}")
            def on_frame_received(payload):
                try:
                    data = json.loads(payload)
                    ws_messages.append({"time": time.time(), "data": data})
                    mtype = data.get("type")
                    sym = data.get("symbol") or data.get("fyers_sym") or ""
                    ltp = data.get("spot_price") or data.get("ltp") or ""
                    if mtype in ["live_tick", "mock_tick", "tick"]:
                        if any(x in sym for x in ["CE", "PE", "INDEX"]):
                            pass
                except Exception as e:
                    ws_messages.append({"time": time.time(), "raw": str(payload)[:200]})
            ws.on("framereceived", on_frame_received)

        page.on("websocket", on_websocket)

        base_url = "https://frequently-daughters-departmental-implement.trycloudflare.com"
        target_url = f"{base_url}/admins/dashboard/live/"

        print(f"Navigating to {target_url}...")
        page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)

        # Check if redirected to login
        if "/admins/login/" in page.url or "login" in page.url:
            print("Detected login page, logging in...")
            page.fill('input[name="username"]', 'marmotadmin')
            page.fill('input[name="password"]', 'marmotadmin@2026')
            page.click('button[type="submit"]')
            page.wait_for_timeout(4000)
            if page.url != target_url:
                page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(3000)

        print(f"Current page URL: {page.url}")
        page.screenshot(path=os.path.join(screenshots_dir, "initial_page.png"), full_page=True)

        oc_el = page.locator("#live-option-chain-container")
        print(f"Option chain container exists: {oc_el.count() > 0}")

        if oc_el.count() > 0:
            oc_el.first.screenshot(path=os.path.join(screenshots_dir, "oc_initial.png"))

        print("Starting 30-second verification monitoring window...")
        start_time = time.time()
        tick_count = 0
        last_snap_time = 0

        while time.time() - start_time < 30:
            elapsed = time.time() - start_time
            now = time.time()

            strike_data = page.evaluate("""() => {
                const rows = document.querySelectorAll('#live-option-chain-container tbody tr');
                const res = [];
                rows.forEach(r => {
                    const strike = r.getAttribute('data-strike');
                    const ceSym = r.getAttribute('data-ce-sym');
                    const peSym = r.getAttribute('data-pe-sym');
                    const ceLtpEl = r.querySelector('[id^="oc-ltp-ce-"]') || r.querySelector('[data-tick-key="ce_' + strike + '"]');
                    const peLtpEl = r.querySelector('[id^="oc-ltp-pe-"]') || r.querySelector('[data-tick-key="pe_' + strike + '"]');
                    const ceChgEl = r.querySelector('[id^="oc-chg-ce-"]');
                    const peChgEl = r.querySelector('[id^="oc-chg-pe-"]');
                    res.push({
                        strike: strike,
                        ce_sym: ceSym,
                        pe_sym: peSym,
                        ce_ltp: ceLtpEl ? ceLtpEl.textContent.trim() : null,
                        ce_tick_price: ceLtpEl ? ceLtpEl.getAttribute('data-tick-price') : null,
                        ce_chg: ceChgEl ? ceChgEl.textContent.trim() : null,
                        pe_ltp: peLtpEl ? peLtpEl.textContent.trim() : null,
                        pe_tick_price: peLtpEl ? peLtpEl.getAttribute('data-tick-price') : null,
                        pe_chg: peChgEl ? peChgEl.textContent.trim() : null
                    });
                });
                return res;
            }""")

            if now - last_snap_time >= 3:
                tick_count += 1
                last_snap_time = now
                snap_path = os.path.join(screenshots_dir, f"tick_snap_{tick_count:02d}_{int(elapsed)}s.png")
                if oc_el.count() > 0:
                    oc_el.first.screenshot(path=snap_path)
                
                # Check active ATM strikes
                active_rows = [r for r in strike_data if r['strike'] in ['22400', '22450', '22500']]
                summary_str = ", ".join([f"{r['strike']}: CE={r['ce_ltp']}({r['ce_chg']}) PE={r['pe_ltp']}({r['pe_chg']})" for r in active_rows])
                print(f"[{elapsed:.1f}s] Snap #{tick_count} | {summary_str}")
                option_chain_snaps.append({"elapsed": elapsed, "data": strike_data})

            page.wait_for_timeout(500)

        page.screenshot(path=os.path.join(screenshots_dir, "final_page.png"), full_page=True)
        if oc_el.count() > 0:
            oc_el.first.screenshot(path=os.path.join(screenshots_dir, "oc_final.png"))

        browser.close()

    with open(os.path.join(artifact_dir, "verified_snaps.json"), "w", encoding="utf-8") as f:
        json.dump(option_chain_snaps, f, indent=2, default=str)

    with open(os.path.join(artifact_dir, "verified_ws_messages.json"), "w", encoding="utf-8") as f:
        json.dump(ws_messages, f, indent=2, default=str)

    print("Verification run completed!")

if __name__ == "__main__":
    run()
