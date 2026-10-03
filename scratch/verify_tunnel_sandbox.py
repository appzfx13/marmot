import asyncio
import os
import sys
import json
import time
from playwright.async_api import async_playwright

sys.stdout.reconfigure(encoding='utf-8')

ARTIFACT_DIR = r"C:\Users\appzf\.gemini\antigravity-ide\brain\e28ecd14-600a-45af-8887-2d85099f2da8"
BASE_URL = "https://mercy-litigation-knock-rotation.trycloudflare.com"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1600, 'height': 1100})
        page = await context.new_page()

        console_logs = []
        page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))

        network_requests = []
        page.on("request", lambda req: network_requests.append({"url": req.url, "method": req.method}))
        
        # 1. Login via Cloudflare Tunnel
        print(f"Navigating to login page on Cloudflare tunnel: {BASE_URL}/admins/login/...")
        await page.goto(f"{BASE_URL}/admins/login/", wait_until="networkidle", timeout=30000)
        await page.fill('input[name="username"]', 'marmotadmin')
        await page.fill('input[name="password"]', 'marmotadmin@2026')
        await page.click('button[type="submit"]')
        await page.wait_for_timeout(3000)

        # 2. Navigate to Sandbox Dashboard
        target_url = f"{BASE_URL}/admins/dashboard/sandbox/"
        print(f"Navigating to Sandbox Dashboard: {target_url}...")
        await page.goto(target_url, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)

        page_title = await page.title()
        print(f"Page Title: {page_title}")

        # 3. Monitor for 6 seconds and capture multiple snapshots
        snapshots = []
        for i in range(1, 6):
            timestamp = time.strftime('%H:%M:%S')
            shot_name = f"tunnel_sandbox_sec_{i}.png"
            shot_path = os.path.join(ARTIFACT_DIR, shot_name)
            await page.screenshot(path=shot_path, full_page=False)

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
                    available_margin: getTxt('sandbox-available-margin'),
                    latency_ms: getTxt('latency-ms-val'),
                    macro_spot: getTxt('live-macro-spot-ltp') || getQueryTxt('.spot-ltp'),
                    option_chain_spot: getTxt('live-option-chain-spot-ltp'),
                    positions_row_count: document.querySelectorAll('#live-positions-container tbody tr').length,
                    orders_row_count: document.querySelectorAll('#live-orders-container tbody tr').length,
                    ws_url: window.MarmotWS ? window.MarmotWS.url : 'NO_WS',
                    ws_ready_state: window.MarmotWS && window.MarmotWS.ws ? window.MarmotWS.ws.readyState : 'NO_WS_OBJ',
                    open_positions_badge: getTxt('sandbox-open-positions-badge'),
                };
            }''')

            snapshots.append({
                "second": i,
                "timestamp": timestamp,
                "screenshot": shot_name,
                "dom": dom_data
            })
            print(f"Tunnel Snapshot {i}/5 at {timestamp}: Spot={dom_data.get('macro_spot')}, Latency={dom_data.get('latency_ms')}, WS_URL={dom_data.get('ws_url')}, WS_STATE={dom_data.get('ws_ready_state')}")
            if i < 5:
                await asyncio.sleep(1.2)

        # 4. Save detailed audit result
        audit_res = {
            "tunnel_base": BASE_URL,
            "page_title": page_title,
            "snapshots": snapshots,
            "console_logs": console_logs,
            "network_requests_count": len(network_requests)
        }
        with open(os.path.join(ARTIFACT_DIR, "tunnel_verification_audit.json"), "w", encoding="utf-8") as f:
            json.dump(audit_res, f, indent=2)

        print("Verification audit completed successfully.")
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
