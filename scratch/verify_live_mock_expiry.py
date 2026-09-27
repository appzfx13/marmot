import asyncio
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1600, 'height': 1100})
        page = await context.new_page()

        print("Navigating to login page...")
        await page.goto("http://127.0.0.1:8050/users/login/", wait_until="networkidle")

        # Fill credentials
        await page.fill('input[name="username"]', 'marmotadmin')
        await page.fill('input[name="password"]', 'marmotadmin@2026')
        await page.click('button[type="submit"]')
        await page.wait_for_timeout(2000)

        print("Navigating to live-mock dashboard...")
        await page.goto("http://127.0.0.1:8050/admins/dashboard/live-mock/", wait_until="networkidle")
        await page.wait_for_timeout(4000)

        # Let's inspect the option chain widget
        expiry_badge = await page.query_selector("#live-option-chain-container, [id*='option-chain']")
        if expiry_badge:
            print("Option chain container found.")

        # Let's see all text inside the option chain card
        card_text = await page.evaluate('''() => {
            const el = document.querySelector("#live-option-chain-container") || document.querySelector(".card:has(table)");
            return el ? el.innerText : "NOT_FOUND";
        }''')
        print("Card text preview:\n", card_text[:500])

        # Screenshot paths
        artifact_dir = r"C:\Users\appzf\.gemini\antigravity-ide\brain\bfd3c300-7f7f-4ba6-b309-50d2a70195da"
        full_shot = os.path.join(artifact_dir, "live_mock_weekly_expiry_verified.png")
        await page.screenshot(path=full_shot, full_page=True)
        print("Saved full screenshot:", full_shot)

        # Save option chain card screenshot
        oc_card = await page.query_selector("#live-option-chain-container")
        if not oc_card:
            oc_card = await page.query_selector(".card:has(table)")
        if oc_card:
            card_shot = os.path.join(artifact_dir, "live_option_chain_weekly_expiry.png")
            await oc_card.screenshot(path=card_shot)
            print("Saved option chain card screenshot:", card_shot)

        await browser.close()

if __name__ == '__main__':
    asyncio.run(run())
