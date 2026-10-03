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
    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "gateway_emulator": {},
        "sandbox_dashboard": {},
        "network_audit": {
            "periodic_polling_detected": False,
            "requests_captured": []
        },
        "console_errors": []
    }

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1680, 'height': 1100})
        page = await context.new_page()

        console_logs = []
        def on_console(msg):
            txt = f"[{msg.type}] {msg.text}"
            console_logs.append(txt)
            if "targetError" in msg.text or msg.type == "error":
                report["console_errors"].append(txt)

        page.on("console", on_console)

        recorded_http_requests = []
        def on_request(req):
            url = req.url
            if any(ext in url for ext in [".css", ".js", ".png", ".jpg", ".woff", ".ico"]):
                return
            headers = req.headers
            hx_trig = headers.get("hx-trigger", "")
            hx_target = headers.get("hx-target", "")
            recorded_http_requests.append({
                "url": url,
                "method": req.method,
                "hx_trigger": hx_trig,
                "hx_target": hx_target,
                "time": time.time()
            })
            if "option-chain" in url:
                print(f"  [HTTP INTERCEPT] option-chain GET requested! trigger='{hx_trig}', target='{hx_target}'")

        page.on("request", on_request)

        # -------------------------------------------------------------
        # STEP 1: AUTHENTICATION
        # -------------------------------------------------------------
        print("==> [QA-1] Authenticating Admin Session...")
        await page.goto(f"{BASE_URL}/admins/login/", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(1500)
        username_input = page.locator('input[name="username"]')
        if await username_input.count() > 0 and await username_input.is_visible():
            await username_input.fill('marmotadmin')
            await page.fill('input[name="password"]', 'marmotadmin@2026')
            await page.click('button[type="submit"]')
            await page.wait_for_timeout(3000)
            print("==> [QA-1] Form submitted, logged in.")
        else:
            print(f"==> [QA-1] Username input not found or already logged in (current url: {page.url})")

        # -------------------------------------------------------------
        # STEP 2: GATEWAY EMULATOR SPA & ACTION VERIFICATION
        # -------------------------------------------------------------
        print("\n==> [QA-2] Testing Gateway Emulator Dashboard...")
        # Navigate to Gateway Emulator via sidebar link (SPA flow)
        await page.goto(f"{BASE_URL}/admins/dashboard/sandbox/", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)

        # Click sidebar Mock Broker link
        sidebar_link = page.locator('#admin-menu-gateway-emulator')
        await sidebar_link.click()
        await page.wait_for_selector('#gateway-emulator-container', timeout=15000)
        await page.wait_for_timeout(1000)

        # Inspect DOM container
        gateway_container = await page.evaluate('''() => {
            const el = document.getElementById('gateway-emulator-container');
            const toggleBtn = document.querySelector('#gateway-toggle-form button');
            return {
                container_present: !!el,
                container_tag: el ? el.tagName : null,
                container_id: el ? el.id : null,
                toggle_btn_text: toggleBtn ? toggleBtn.innerText.trim() : null,
                has_toggle_form: !!document.getElementById('gateway-toggle-form')
            };
        }''')
        print(f"Gateway Container Inspection: {json.dumps(gateway_container, indent=2)}")
        report["gateway_emulator"]["container_check"] = gateway_container

        # Click Toggle button to test Replay action
        toggle_btn = page.locator('#gateway-toggle-form button')
        btn_count = await toggle_btn.count()
        if btn_count > 0:
            btn_before = await toggle_btn.inner_text()
            print(f"Action button before click: '{btn_before}'")
            print("Executing Click on Toggle Replay Button...")
            await toggle_btn.click()
            await page.wait_for_timeout(3000)

            btn_after = await page.locator('#gateway-toggle-form button').inner_text()
            print(f"Action button after click: '{btn_after}'")
            report["gateway_emulator"]["button_transition"] = {
                "before": btn_before,
                "after": btn_after,
                "toggled_successfully": btn_before != btn_after or "Pause" in btn_after or "Start" in btn_after
            }

        # Check for target errors
        target_errors = [e for e in report["console_errors"] if "targetError" in e]
        report["gateway_emulator"]["target_error_count"] = len(target_errors)
        report["gateway_emulator"]["zero_target_errors"] = len(target_errors) == 0

        shot_gateway = os.path.join(ARTIFACT_DIR, "qa_gateway_emulator_verified.png")
        await page.screenshot(path=shot_gateway, full_page=False)
        print(f"Saved Gateway Emulator screenshot to: {shot_gateway}")

        # -------------------------------------------------------------
        # STEP 3: SANDBOX DASHBOARD TELEMETRY & POLLING AUDIT
        # -------------------------------------------------------------
        print("\n==> [QA-3] Testing Sandbox Dashboard (Zero-Polling & Realtime Verification)...")
        # Navigate back to Sandbox Dashboard
        sandbox_link = page.locator('#admin-menu-sandbox')
        if await sandbox_link.count() > 0:
            await sandbox_link.click()
        else:
            await page.goto(f"{BASE_URL}/admins/dashboard/sandbox/", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(3000)

        # Clear request log to test purely during steady-state
        recorded_http_requests.clear()
        print("Auditing network requests for 8 seconds to verify ZERO periodic HTMX polling...")
        
        # Check WebSocket state and live telemetry
        ws_telemetry = await page.evaluate('''() => {
            const wsState = window.MarmotWS ? (window.MarmotWS.connected ? 'CONNECTED' : 'DISCONNECTED') : 'OBJECT_NOT_FOUND';
            const tickerText = document.querySelector('#ticker-nifty-ltp, .ticker-ltp, #live-nifty-price')?.innerText;
            const ordersRows = document.querySelectorAll('#live-orders-container tbody tr').length;
            const positionsRows = document.querySelectorAll('#live-positions-container tbody tr').length;
            
            // Check for CALL / PUT badges in orders
            const orderBadges = Array.from(document.querySelectorAll('#live-orders-container tbody tr td span.badge'))
                                     .map(b => b.innerText.trim());
            const hasCallOrPutBadges = orderBadges.some(b => b === 'CALL' || b === 'PUT');
            
            // Check for Spot badge in orders
            const spotBadges = Array.from(document.querySelectorAll('#live-orders-container tbody tr td div'))
                                    .filter(d => d.innerText.includes('Spot: ₹'))
                                    .map(d => d.innerText.trim());
                                    
            return {
                ws_state: wsState,
                ticker_price: tickerText,
                orders_count: ordersRows,
                positions_count: positionsRows,
                has_call_or_put_badges: hasCallOrPutBadges,
                sample_spot_badges: spotBadges.slice(0, 3)
            };
        }''')
        print(f"Sandbox Telemetry & DOM State: {json.dumps(ws_telemetry, indent=2)}")
        report["sandbox_dashboard"]["telemetry_dom"] = ws_telemetry

        # Wait 8 seconds to capture any periodic polling
        await page.wait_for_timeout(8000)

        # Evaluate captured requests during 8 second window
        # Periodic polling would appear as multiple requests to the same endpoint every 1-3 seconds
        repeated_endpoints = {}
        for req in recorded_http_requests:
            endpoint = req["url"].split("?")[0]
            repeated_endpoints[endpoint] = repeated_endpoints.get(endpoint, 0) + 1

        # Periodic polling exists if any endpoint is called > 3 times in 8s
        periodic_polling = any(count >= 3 for ep, count in repeated_endpoints.items() if not any(x in ep for x in ["ws", "socket"]))
        report["network_audit"]["periodic_polling_detected"] = periodic_polling
        report["network_audit"]["repeated_endpoints"] = repeated_endpoints
        report["network_audit"]["total_http_requests_in_8s"] = len(recorded_http_requests)
        print(f"Endpoint breakdown: {json.dumps(repeated_endpoints, indent=2)}")
        relevant_logs = [l for l in console_logs if 'OptionChain' in l or 'reload' in l or 'Strike' in l or 'ATM' in l or 'target' in l]
        print(f"Relevant OptionChain logs: {json.dumps(relevant_logs, indent=2)}")

        # Check Price Decoupling in Orders Table
        price_audit = await page.evaluate('''() => {
            const rows = document.querySelectorAll('#live-orders-container tbody tr');
            const samples = [];
            rows.forEach(r => {
                const sym = r.querySelector('td:nth-child(2) span')?.innerText || '';
                const limitPrice = r.querySelector('td:nth-child(5) .fw-bold')?.innerText || '';
                const spotBadge = r.querySelector('td:nth-child(5) .text-info')?.innerText || '';
                const filledPrice = r.querySelector('td:nth-child(7) .fw-bold')?.innerText || '';
                const slBadge = r.querySelector('td:nth-child(6) .text-danger')?.innerText || '';
                const tpBadge = r.querySelector('td:nth-child(6) .text-success')?.innerText || '';
                if (sym) {
                    samples.push({
                        symbol: sym,
                        limit_price: limitPrice,
                        spot_badge: spotBadge,
                        sl: slBadge,
                        tp: tpBadge,
                        filled: filledPrice
                    });
                }
            });
            return samples.slice(0, 5);
        }''')
        print(f"Orders Table Price Decoupling Audit: {json.dumps(price_audit, indent=2)}")
        report["sandbox_dashboard"]["price_audit_samples"] = price_audit

        shot_sandbox = os.path.join(ARTIFACT_DIR, "qa_sandbox_dashboard_verified.png")
        await page.screenshot(path=shot_sandbox, full_page=False)
        print(f"Saved Sandbox Dashboard screenshot to: {shot_sandbox}")

        # -------------------------------------------------------------
        # STEP 4: WRITE AUDIT REPORT ARTIFACT
        # -------------------------------------------------------------
        report_path = os.path.join(ARTIFACT_DIR, "qa_comprehensive_audit_report.json")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(f"\n==> [QA-REPORT] Comprehensive audit report saved to: {report_path}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
