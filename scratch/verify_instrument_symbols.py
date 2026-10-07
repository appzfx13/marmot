import asyncio
from playwright.async_api import async_playwright
import os

ARTIFACT_DIR = r"C:\Users\godla\.gemini\antigravity-ide\brain\17a51108-2c89-4ed9-9509-62ba7da20689"
os.makedirs(ARTIFACT_DIR, exist_ok=True)

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1600, 'height': 1000})
        page = await context.new_page()

        login_url = "https://annotation-keyboard-domain-quebec.trycloudflare.com/admins/login/"
        print(f"Navigating to {login_url}...")
        await page.goto(login_url, wait_until="networkidle", timeout=30000)

        # Login
        await page.fill('#id_admin_username', 'marmotadmin')
        await page.fill('#id_admin_password', 'marmotadmin@2026')
        print("Submitting login form...")
        await page.click('#adminSubmitBtn')
        await page.wait_for_timeout(4000)

        dashboard_url = "https://annotation-keyboard-domain-quebec.trycloudflare.com/admins/dashboard/sandbox/"
        print(f"Navigating to {dashboard_url}...")
        await page.goto(dashboard_url, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(3000)

        # Locate the orders table
        orders_card = page.locator('.card:has-text("Live Orders & Execution Book")')
        if await orders_card.count() > 0:
            await orders_card.first.scroll_into_view_if_needed()
            await page.wait_for_timeout(1000)
            shot_path = os.path.join(ARTIFACT_DIR, "live_orders_instrument_verified.png")
            await orders_card.first.screenshot(path=shot_path)
            print(f"Orders card screenshot saved to: {shot_path}")
        else:
            shot_path = os.path.join(ARTIFACT_DIR, "live_orders_instrument_verified.png")
            await page.screenshot(path=shot_path, full_page=True)
            print(f"Full page screenshot saved to: {shot_path}")

        # Extract text in the Instrument column
        table_rows = await page.locator('.card:has-text("Live Orders & Execution Book") table tbody tr').all()
        print(f"\nFound {len(table_rows)} rows in Live Orders & Execution Book:")
        for idx, row in enumerate(table_rows, 1):
            text = await row.inner_text()
            lines = [l.strip() for l in text.split('\n') if l.strip()]
            print(f"Row {idx}: {lines}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
