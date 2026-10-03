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

        console_errors = []
        all_logs = []
        def on_console(msg):
            all_logs.append(f"[{msg.type}] {msg.text}")
            if "targetError" in msg.text or msg.type == "error":
                console_errors.append(f"[{msg.type}] {msg.text}")

        page.on("console", on_console)

        # 1. Login
        print("Logging in...")
        await page.goto(f"{BASE_URL}/admins/login/", wait_until="networkidle", timeout=30000)
        await page.fill('input[name="username"]', 'marmotadmin')
        await page.fill('input[name="password"]', 'marmotadmin@2026')
        await page.click('button[type="submit"]')
        await page.wait_for_timeout(3000)

        # 2. Go to Sandbox Dashboard first to simulate SPA user flow
        print("Navigating to Sandbox Dashboard first...")
        await page.goto(f"{BASE_URL}/admins/dashboard/sandbox/", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)

        # 3. Click "Mock Broker" in the sidebar via HTMX SPA navigation
        print("Clicking Mock Broker in sidebar (HTMX SPA navigation)...")
        sidebar_link = page.locator('#admin-menu-gateway-emulator')
        await sidebar_link.click()
        await page.wait_for_timeout(3000)

        # 4. Check if #gateway-emulator-container exists
        container_exists = await page.evaluate('''() => {
            const el = document.getElementById('gateway-emulator-container');
            return {
                exists: !!el,
                tag: el ? el.tagName : null,
                classes: el ? el.className : null
            };
        }''')
        print(f"Container check after SPA navigation: {json.dumps(container_exists)}")

        # 5. Capture screenshot of page loaded via SPA
        shot1 = os.path.join(ARTIFACT_DIR, "gateway_emulator_spa_loaded.png")
        await page.screenshot(path=shot1, full_page=False)
        print(f"Saved SPA loaded screenshot to {shot1}")

        # 6. Click Start Replay / Pause Replay button in #gateway-toggle-form
        print("Looking for toggle form button...")
        toggle_btn = page.locator('#gateway-toggle-form button')
        btn_count = await toggle_btn.count()
        print(f"Found {btn_count} button(s) in #gateway-toggle-form")

        if btn_count > 0:
            btn_text = await toggle_btn.inner_text()
            print(f"Button text before click: '{btn_text}'")
            print("Clicking toggle button...")
            await toggle_btn.click()
            await page.wait_for_timeout(3000)

            # Re-read button text after click
            btn_after = await page.locator('#gateway-toggle-form button').inner_text()
            print(f"Button text after click: '{btn_after}'")

        # 7. Capture screenshot after click
        shot2 = os.path.join(ARTIFACT_DIR, "gateway_emulator_after_toggle.png")
        await page.screenshot(path=shot2, full_page=False)
        print(f"Saved post-click screenshot to {shot2}")

        # 8. Check for target errors
        print(f"\nTarget / Console Errors count: {len(console_errors)}")
        for err in console_errors:
            print(f"  ERROR: {err}")

        has_target_error = any("targetError" in e for e in console_errors)
        if has_target_error:
            print("FAILED: htmx:targetError detected!")
        else:
            print("SUCCESS: ZERO htmx:targetError detected!")

        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
