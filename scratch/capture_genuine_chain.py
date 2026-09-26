import os
import time
from playwright.sync_api import sync_playwright

SCREENSHOT_DIR = r"C:\Users\appzf\.gemini\antigravity-ide\brain\04588b54-8408-4acb-89e4-8cbf69d157c4"

def capture():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1600, 'height': 1200})
        page = context.new_page()

        print("1. Logging in...")
        page.goto("http://localhost:8050/users/login/", wait_until="networkidle")
        page.fill('input[name="username"]', 'marmotadmin')
        page.fill('input[name="password"]', 'marmotadmin@2026')
        page.click('button[type="submit"]')
        page.wait_for_timeout(2000)

        print("2. Navigating to Live Mock Dashboard...")
        page.goto("http://localhost:8050/admins/dashboard/live-mock/", wait_until="networkidle")
        page.wait_for_timeout(3000)

        chain_el = page.query_selector('#live-option-chain-container')
        if chain_el:
            chain_el.scroll_into_view_if_needed()
            page.wait_for_timeout(1000)

            expand_btn = page.query_selector('#btn-toggle-option-chain-strikes')
            if expand_btn:
                expand_btn.click()
                page.wait_for_timeout(1500)

            shot_chain = os.path.join(SCREENSHOT_DIR, "46_live_mock_option_chain_genuine_data.png")
            chain_el.screenshot(path=shot_chain)
            print("Saved:", shot_chain)

        shot_full = os.path.join(SCREENSHOT_DIR, "47_live_mock_dashboard_full_genuine.png")
        page.screenshot(path=shot_full, full_page=True)
        print("Saved full:", shot_full)

        browser.close()

if __name__ == '__main__':
    capture()
