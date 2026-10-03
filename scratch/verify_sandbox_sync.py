import asyncio
import os
import sys
import json
import time
from playwright.async_api import async_playwright

sys.stdout.reconfigure(encoding='utf-8')

ARTIFACT_DIR = r"C:\Users\appzf\.gemini\antigravity-ide\brain\e28ecd14-600a-45af-8887-2d85099f2da8"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1600, 'height': 1100})
        page = await context.new_page()

        console_logs = []
        page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))
        
        # 1. Login
        print("Navigating to login page...")
        await page.goto("http://127.0.0.1:8050/admins/login/", wait_until="networkidle")
        await page.fill('input[name="username"]', 'marmotadmin')
        await page.fill('input[name="password"]', 'marmotadmin@2026')
        await page.click('button[type="submit"]')
        await page.wait_for_timeout(2000)

        # 2. Navigate to Admin Sandbox Dashboard
        print("Navigating to Sandbox Dashboard (/admins/dashboard/sandbox/)...")
        await page.goto("http://127.0.0.1:8050/admins/dashboard/sandbox/", wait_until="networkidle")
        await page.wait_for_timeout(1500)

        # Verify initial page elements
        page_title = await page.title()
        print(f"Page title: {page_title}")

        # 3. Capture 5 snapshots over 5 seconds (1 screenshot per second)
        snapshots = []
        for i in range(1, 6):
            timestamp = time.strftime('%H:%M:%S')
            shot_name = f"sandbox_sync_sec_{i}.png"
            shot_path = os.path.join(ARTIFACT_DIR, shot_name)
            await page.screenshot(path=shot_path, full_page=False)

            # Extract DOM state at this exact moment
            dom_data = await page.evaluate('''() => {
                const getTxt = (id) => {
                    const el = document.getElementById(id);
                    return el ? el.textContent.trim() : null;
                };
                const getQueryTxt = (sel) => {
                    const el = document.querySelector(sel);
                    return el ? el.textContent.trim() : null;
                };

                return {
                    url: window.location.href,
                    net_pnl: getTxt('sandbox-live-net-pnl') || getTxt('live-portfolio-net-pnl'),
                    unrealized_pnl: getTxt('sandbox-unrealized-pnl'),
                    realized_pnl: getTxt('sandbox-realized-pnl'),
                    available_margin: getTxt('sandbox-available-margin'),
                    margin_utilized: getTxt('sandbox-margin-utilized'),
                    open_positions_badge: getTxt('sandbox-open-positions-badge'),
                    latency_ms: getTxt('latency-ms-val'),
                    macro_spot: getTxt('live-macro-spot-ltp') || getQueryTxt('.spot-ltp'),
                    option_chain_spot: getTxt('live-option-chain-spot-ltp'),
                    positions_row_count: document.querySelectorAll('#live-positions-container tbody tr').length,
                    orders_row_count: document.querySelectorAll('#live-orders-container tbody tr').length,
                    marmot_ws_status: window.MarmotWS ? (window.MarmotWS.ws ? window.MarmotWS.ws.readyState : 'NO_WS') : 'NO_MARMOT_WS',
                    dhan_ws_status: window._DhanEmulatorWS ? window._DhanEmulatorWS.readyState : 'NO_DHAN_WS',
                    is_mock_mode_flag: typeof isMockMode !== 'undefined' ? isMockMode : null,
                };
            }''')

            snapshots.append({
                "second": i,
                "timestamp": timestamp,
                "screenshot": shot_name,
                "dom": dom_data
            })
            print(f"Captured Snapshot {i}/5 at {timestamp}: NetPnL={dom_data.get('net_pnl')}, Spot={dom_data.get('macro_spot')}, Latency={dom_data.get('latency_ms')}, WS={dom_data.get('marmot_ws_status')}")
            if i < 5:
                await asyncio.sleep(1.0)

        # Also let's check /admins/dashboard/live-mock/ to compare!
        print("\nNavigating to Live-Mock Dashboard (/admins/dashboard/live-mock/)...")
        await page.goto("http://127.0.0.1:8050/admins/dashboard/live-mock/", wait_until="networkidle")
        await page.wait_for_timeout(1500)
        live_mock_shot = os.path.join(ARTIFACT_DIR, "live_mock_dashboard.png")
        await page.screenshot(path=live_mock_shot, full_page=False)

        live_mock_dom = await page.evaluate('''() => {
            const getTxt = (id) => {
                const el = document.getElementById(id);
                return el ? el.textContent.trim() : null;
            };
            return {
                net_pnl: getTxt('sandbox-live-net-pnl') || getTxt('live-portfolio-net-pnl'),
                macro_spot: getTxt('live-macro-spot-ltp'),
                marmot_ws_status: window.MarmotWS ? (window.MarmotWS.ws ? window.MarmotWS.ws.readyState : 'NO_WS') : 'NO_MARMOT_WS',
                dhan_ws_status: window._DhanEmulatorWS ? window._DhanEmulatorWS.readyState : 'NO_DHAN_WS',
            };
        }''')
        print(f"Live-Mock Snapshot: {live_mock_dom}")

        # Dump summary results
        result = {
            "snapshots": snapshots,
            "live_mock_dom": live_mock_dom,
            "console_logs_tail": console_logs[-30:] if console_logs else []
        }
        with open(os.path.join(ARTIFACT_DIR, "verification_data.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)

        print("\nAll snapshots and data saved successfully.")
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
