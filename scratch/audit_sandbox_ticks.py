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
            ws.on("framereceived", lambda payload: ws_messages.append({
                "time": time.time(),
                "dir": "recv"
            }))

        page.on("websocket", handle_ws)

        print("[Verify] Navigating to Sandbox Dashboard...")
        await page.goto(BASE_URL, wait_until="networkidle", timeout=60000)

        # Check if login is needed
        if "login" in page.url or await page.locator("#id_admin_username").count() > 0:
            print("[Verify] Logging in with marmotadmin...")
            await page.fill("#id_admin_username", "marmotadmin")
            await page.fill("#id_admin_password", "marmotadmin@2026")
            await page.click("#adminSubmitBtn")
            await page.wait_for_timeout(3000)
            if "login" in page.url:
                await page.goto(BASE_URL, wait_until="networkidle", timeout=60000)

        print(f"[Verify] Now on URL: {page.url}")
        if page.url != BASE_URL:
            await page.goto(BASE_URL, wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(3000)

        print("[Verify] Monitoring Sandbox Dashboard for 30 seconds...")

        dom_history = []
        start_time = time.time()
        checkpoints = [0, 10, 20, 30]
        captured_checkpoints = set()

        while True:
            elapsed = time.time() - start_time
            if elapsed >= 30:
                break

            for cp in checkpoints:
                if cp not in captured_checkpoints and elapsed >= cp:
                    captured_checkpoints.add(cp)
                    shot_path = os.path.join(ARTIFACT_DIR, f"post_fix_verify_{cp}s.png")
                    await page.screenshot(path=shot_path, full_page=True)
                    print(f"[Verify] Captured screenshot at {cp}s: {shot_path}")

            try:
                state = await page.evaluate("""() => {
                    const spotEl = document.getElementById('live-macro-spot-ltp');
                    const ocSpotEl = document.getElementById('live-option-chain-spot-ltp');
                    const ocAtmEl = document.getElementById('live-option-chain-atm');
                    const visibleRows = document.querySelectorAll('#live-option-chain-container tbody tr:not(.d-none)').length;
                    const totalRows = document.querySelectorAll('#live-option-chain-container tbody tr').length;
                    return {
                        spot_ltp: spotEl ? spotEl.innerText.trim() : null,
                        oc_spot: ocSpotEl ? ocSpotEl.innerText.trim() : null,
                        oc_atm: ocAtmEl ? ocAtmEl.innerText.trim() : null,
                        visible_rows: visibleRows,
                        total_rows: totalRows
                    };
                }""")
                dom_history.append({"elapsed": round(elapsed, 2), "data": state})
                print(f"[Tick {round(elapsed, 1)}s] Spot: {state['spot_ltp']} | OC Spot: {state['oc_spot']} | ATM: {state['oc_atm']} | Visible Rows: {state['visible_rows']}/{state['total_rows']}")
            except Exception as e:
                dom_history.append({"elapsed": round(elapsed, 2), "error": str(e)})

            await asyncio.sleep(1.0)

        if 30 not in captured_checkpoints:
            shot_path = os.path.join(ARTIFACT_DIR, "post_fix_verify_30s.png")
            await page.screenshot(path=shot_path, full_page=True)
            print(f"[Verify] Captured final screenshot at 30s: {shot_path}")

        # Summary of HTTP requests during the 30 seconds
        post_load_reqs = [r for r in http_requests if r["time"] >= (start_time + 3.0)]

        out_data = {
            "elapsed": round(time.time() - start_time, 2),
            "ws_received_count": len(ws_messages),
            "post_load_http_requests_count": len(post_load_reqs),
            "post_load_http_requests": post_load_reqs,
            "dom_history": dom_history
        }

        verify_json_path = os.path.join(ARTIFACT_DIR, "post_fix_verification.json")
        with open(verify_json_path, "w", encoding="utf-8") as f:
            json.dump(out_data, f, indent=2)

        print(f"[Verify] Verification data saved to {verify_json_path}")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run_verification())
