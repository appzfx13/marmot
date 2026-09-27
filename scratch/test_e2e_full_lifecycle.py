import asyncio
import os
import sys
import urllib.request
import json

sys.stdout.reconfigure(encoding='utf-8')

from playwright.async_api import async_playwright

def place_mock_order():
    # Post a BUY order to Dhan mock broker
    url = "http://127.0.0.1:8088/mock/v2/orders"
    payload = {
        "dhanClientId": "1000000001",
        "correlationId": "TEST_CLEAR_SESSION_01",
        "transactionType": "BUY",
        "exchangeSegment": "NSE_FNO",
        "productType": "INTRADAY",
        "orderType": "MARKET",
        "validity": "DAY",
        "securityId": "21700_CE",
        "tradingSymbol": "NIFTY 21700 CE",
        "quantity": 50,
        "price": 250.00
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            print("Placed test mock order:", data)
            return data
    except Exception as e:
        print("Error placing mock order:", e)
        return None

async def run():
    print("Step 1: Place a mock order to populate positions & orders...")
    place_mock_order()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1600, 'height': 1100})
        page = await context.new_page()

        # Handle any browser dialog automatically
        page.on("dialog", lambda dialog: asyncio.create_task(dialog.accept()))

        print("Step 2: Login and open Live Mock Dashboard...")
        await page.goto("http://127.0.0.1:8050/users/login/", wait_until="networkidle")
        await page.fill('input[name="username"]', 'marmotadmin')
        await page.fill('input[name="password"]', 'marmotadmin@2026')
        await page.click('button[type="submit"]')
        await page.wait_for_timeout(2000)

        await page.goto("http://127.0.0.1:8050/admins/dashboard/live-mock/", wait_until="networkidle")
        await page.wait_for_timeout(3000)

        artifact_dir = r"C:\Users\appzf\.gemini\antigravity-ide\brain\bfd3c300-7f7f-4ba6-b309-50d2a70195da"
        shot_with_trades = os.path.join(artifact_dir, "mock_session_with_active_orders.png")
        await page.screenshot(path=shot_with_trades, full_page=True)
        print("Saved screenshot with active orders:", shot_with_trades)

        # Check table contents
        pos_table_text = await page.evaluate('''() => {
            const el = document.querySelector("#live-positions-table-container");
            return el ? el.innerText : "NOT_FOUND";
        }''')
        print("Positions table before clear snippet:\n", pos_table_text[:200])

        # Step 3: Click Clear Mock Session
        print("Step 3: Clicking 'Clear Mock Session' button...")
        clear_btn = await page.query_selector("button:has-text('Clear Mock Session')")
        if clear_btn:
            await clear_btn.click()
            await page.wait_for_timeout(4000)

        # Step 4: Verify cleared state
        pos_after = await page.evaluate('''() => {
            const el = document.querySelector("#live-positions-table-container");
            return el ? el.innerText : "NOT_FOUND";
        }''')
        print("Positions table after clear:\n", pos_after.strip())

        orders_after = await page.evaluate('''() => {
            const el = document.querySelector("#live-orders-table-container");
            return el ? el.innerText : "NOT_FOUND";
        }''')
        print("Orders table after clear:\n", orders_after.strip())

        margin_after = await page.evaluate('''() => {
            const el = document.querySelector("#live-summary-available-margin");
            return el ? el.innerText : "NOT_FOUND";
        }''')
        print("Available Margin after clear:", margin_after)

        shot_cleared = os.path.join(artifact_dir, "mock_session_cleared_verified.png")
        await page.screenshot(path=shot_cleared, full_page=True)
        print("Saved screenshot after clear verified:", shot_cleared)

        await browser.close()

if __name__ == '__main__':
    asyncio.run(run())
