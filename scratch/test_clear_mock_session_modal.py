import asyncio
import os
import sys
import urllib.request
import json

sys.stdout.reconfigure(encoding='utf-8')

from playwright.async_api import async_playwright

def place_mock_order():
    url = "http://127.0.0.1:8088/mock/v2/orders"
    payload = {
        "dhanClientId": "1000000001",
        "correlationId": "TEST_CLEAR_SESSION_MODAL_01",
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
    print("Step 1: Place mock order...")
    place_mock_order()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1600, 'height': 1100})
        page = await context.new_page()

        print("Step 2: Login to Marmot Admin...")
        await page.goto("http://127.0.0.1:8050/users/login/", wait_until="networkidle")
        await page.fill('input[name="username"]', 'marmotadmin')
        await page.fill('input[name="password"]', 'marmotadmin@2026')
        await page.click('button[type="submit"]')
        await page.wait_for_timeout(2000)

        print("Step 3: Open Live Mock Dashboard...")
        await page.goto("http://127.0.0.1:8050/admins/dashboard/live-mock/", wait_until="networkidle")
        await page.wait_for_timeout(3000)

        artifact_dir = r"C:\Users\appzf\.gemini\antigravity-ide\brain\bfd3c300-7f7f-4ba6-b309-50d2a70195da"
        shot_before = os.path.join(artifact_dir, "clear_session_step1_before.png")
        await page.screenshot(path=shot_before, full_page=True)
        print("Pre-clear screenshot saved:", shot_before)

        margin_before = await page.evaluate('''() => {
            const el = document.querySelector("#live-summary-available-margin");
            return el ? el.innerText : "NOT_FOUND";
        }''')
        print("Available Margin BEFORE clear:", margin_before)

        # Step 4: Click 'Clear Mock Session' button
        print("Step 4: Clicking 'Clear Mock Session' button...")
        clear_btn = await page.query_selector("button:has-text('Clear Mock Session')")
        if not clear_btn:
            raise Exception("Clear Mock Session button not found!")
        await clear_btn.click()
        await page.wait_for_timeout(1000)

        # Step 5: Check if custom modal opened
        modal_visible = await page.evaluate('''() => {
            const modal = document.querySelector("#globalHtmxModal");
            return modal && modal.classList.contains("show");
        }''')
        print("Global modal is visible:", modal_visible)

        shot_modal = os.path.join(artifact_dir, "clear_session_step2_modal.png")
        await page.screenshot(path=shot_modal, full_page=True)
        print("Modal screenshot saved:", shot_modal)

        # Step 6: Click Confirm button in modal
        print("Step 6: Clicking Confirm in modal...")
        confirm_btn = await page.query_selector("#global-modal-confirm-btn, button:has-text('Confirm')")
        if confirm_btn:
            await confirm_btn.click()
            await page.wait_for_timeout(4000)
        else:
            print("Confirm button not found in modal!")

        # Step 7: Check post-clear state
        margin_after = await page.evaluate('''() => {
            const el = document.querySelector("#live-summary-available-margin");
            return el ? el.innerText : "NOT_FOUND";
        }''')
        print("Available Margin AFTER clear:", margin_after)

        toast_text = await page.evaluate('''() => {
            const el = document.querySelector(".toast, .toast-body");
            return el ? el.innerText : "NONE";
        }''')
        print("Toast notification text:", toast_text.replace('\n', ' '))

        shot_after = os.path.join(artifact_dir, "clear_session_step3_cleared.png")
        await page.screenshot(path=shot_after, full_page=True)
        print("Post-clear screenshot saved:", shot_after)

        await browser.close()
        print("Verification completed successfully!")

if __name__ == '__main__':
    asyncio.run(run())
