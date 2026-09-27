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

        print("1. Logging into Marmot Admin...")
        await page.goto("http://127.0.0.1:8050/users/login/", wait_until="networkidle")
        await page.fill('input[name="username"]', 'marmotadmin')
        await page.fill('input[name="password"]', 'marmotadmin@2026')
        await page.click('button[type="submit"]')
        await page.wait_for_timeout(2000)

        print("2. Navigating to Live Mock Dashboard...")
        await page.goto("http://127.0.0.1:8050/admins/dashboard/live-mock/", wait_until="networkidle")
        await page.wait_for_timeout(3000)

        artifact_dir = r"C:\Users\appzf\.gemini\antigravity-ide\brain\bfd3c300-7f7f-4ba6-b309-50d2a70195da"
        before_shot = os.path.join(artifact_dir, "live_mock_before_clear.png")
        await page.screenshot(path=before_shot, full_page=True)
        print("Captured pre-clear screenshot:", before_shot)

        # 3. Locate Clear Mock Session button
        clear_btn = await page.query_selector("button:has-text('Clear Mock Session')")
        if not clear_btn:
            raise Exception("Clear Mock Session button not found!")
        print("Found Clear Mock Session button.")

        # 4. Set up dialog handler to auto-accept the confirmation dialog
        dialog_handled = False
        def handle_dialog(dialog):
            nonlocal dialog_handled
            print(f"Dialog triggered: '{dialog.message}' -> Accepting...")
            dialog_handled = True
            asyncio.create_task(dialog.accept())

        page.on("dialog", handle_dialog)

        # 5. Click the button
        print("Clicking 'Clear Mock Session' button...")
        await clear_btn.click()
        await page.wait_for_timeout(3500)

        print(f"Confirmation dialog handled: {dialog_handled}")

        # 6. Check for toast message
        toast_el = await page.query_selector(".toast, .toast-body, [class*='toast']")
        if toast_el:
            toast_text = await toast_el.inner_text()
            print("Toast notification displayed:", toast_text.replace('\n', ' '))

        # 7. Check Available Margin text
        margin_el = await page.query_selector("#live-summary-available-margin")
        if margin_el:
            margin_text = await margin_el.inner_text()
            print("Available Margin after clear:", margin_text)

        # 8. Capture post-clear screenshot
        after_shot = os.path.join(artifact_dir, "live_mock_after_clear_verified.png")
        await page.screenshot(path=after_shot, full_page=True)
        print("Captured post-clear verified screenshot:", after_shot)

        await browser.close()
        print("Automation verification finished successfully!")

if __name__ == '__main__':
    asyncio.run(run())
