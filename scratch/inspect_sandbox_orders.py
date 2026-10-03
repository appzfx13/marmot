import asyncio
import sys
from playwright.async_api import async_playwright

sys.stdout.reconfigure(encoding='utf-8')

async def inspect():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        await context.add_cookies([{
            "name": "sessionid",
            "value": "hy7gismskyubte7dcr7dfq5czhlsshrg",
            "domain": "127.0.0.1",
            "path": "/"
        }])
        page = await context.new_page()
        try:
            await page.goto("http://127.0.0.1:8050/admins/dashboard/sandbox/", timeout=15000)
            await page.wait_for_timeout(3000)
            
            print("CURRENT URL:", page.url)
            
            # Check strategy cards
            cards = await page.query_selector_all('[data-strategy-id]')
            card_info = []
            for c in cards:
                s_id = await c.get_attribute("data-strategy-id")
                text = (await c.inner_text()).replace("\n", " | ")
                card_info.append(f"ID {s_id}: {text}")
            
            # Check strategy section HTML
            strat_section = await page.query_selector("#strategy-telemetry-container, #deployed-strategies-container, .deployed-strategies")
            if strat_section:
                print("STRAT SECTION TEXT:", (await strat_section.inner_text()).replace("\n", " | ")[:300])
            
            # Check orders count
            orders = await page.query_selector_all("table tbody tr")
            order_rows = []
            for r in orders[:15]:
                order_rows.append((await r.inner_text()).replace("\n", " | "))
            
            print("CARDS COUNT:", len(card_info))
            for ci in card_info:
                print("  CARD:", ci)
            print("TABLE ROWS COUNT:", len(orders))
            for r in order_rows:
                print("  ROW:", r)
                
            await page.screenshot(path=r"C:\Users\appzf\.gemini\antigravity-ide\brain\e28ecd14-600a-45af-8887-2d85099f2da8\sandbox_orders_inspection.png", full_page=True)
            print("Screenshot saved to sandbox_orders_inspection.png")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(inspect())
