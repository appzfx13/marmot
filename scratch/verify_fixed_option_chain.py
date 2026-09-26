import os
import time
from playwright.sync_api import sync_playwright

SCREENSHOT_DIR = r"C:\Users\appzf\.gemini\antigravity-ide\brain\04588b54-8408-4acb-89e4-8cbf69d157c4"

def audit_fixed_option_chain():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1600, 'height': 1200})
        page = context.new_page()

        print("1. Logging in as admin...")
        page.goto("http://localhost:8050/users/login/", wait_until="networkidle")
        page.fill('input[name="username"]', 'marmotadmin')
        page.fill('input[name="password"]', 'marmotadmin@2026')
        page.click('button[type="submit"]')
        page.wait_for_timeout(2000)

        print("2. Navigating to Gateway Emulator...")
        page.goto("http://localhost:8050/admins/dashboard/gateway-emulator/", wait_until="networkidle")
        page.wait_for_timeout(2000)

        # Select file 1/20/dataset.parquet if not already running
        # Capture screenshot of emulator page
        shot_em = os.path.join(SCREENSHOT_DIR, "43_gateway_emulator_running_fixed.png")
        page.screenshot(path=shot_em, full_page=True)
        print(f"Captured: {shot_em}")

        print("3. Navigating to Live Mock Dashboard...")
        page.goto("http://localhost:8050/admins/dashboard/live-mock/", wait_until="networkidle")
        page.wait_for_timeout(3000)

        # Scroll to option chain container
        chain_el = page.query_selector('#live-option-chain-container')
        if chain_el:
            chain_el.scroll_into_view_if_needed()
            page.wait_for_timeout(1000)

            # Click Expand (31 strikes) button
            expand_btn = page.query_selector('#btn-toggle-option-chain-strikes')
            if expand_btn:
                expand_btn.click()
                page.wait_for_timeout(1500)

            shot_chain = os.path.join(SCREENSHOT_DIR, "44_live_mock_option_chain_fixed.png")
            chain_el.screenshot(path=shot_chain)
            print(f"Captured fixed option chain screenshot: {shot_chain}")

            shot_full = os.path.join(SCREENSHOT_DIR, "45_live_mock_dashboard_full_fixed.png")
            page.screenshot(path=shot_full, full_page=True)
            print(f"Captured full page screenshot: {shot_full}")

            rows = page.query_selector_all('#live-option-chain-tbody tr:not(.d-none)')
            print(f"Active visible strikes rendered: {len(rows)}")
            for idx, r in enumerate(rows):
                txt = r.inner_text().replace('\t', ' | ').replace('\n', ' | ')
                print(f"  Strike {idx+1}: {txt}")

        browser.close()

if __name__ == '__main__':
    audit_fixed_option_chain()
