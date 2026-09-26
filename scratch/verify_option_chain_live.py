import os
import sys
import time
from playwright.sync_api import sync_playwright

SCREENSHOT_DIR = r"C:\Users\appzf\.gemini\antigravity-ide\brain\04588b54-8408-4acb-89e4-8cbf69d157c4"

def audit_option_chain():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1600, 'height': 1200})
        page = context.new_page()

        print("1. Logging into Marmot Admin...")
        page.goto("http://localhost:8050/users/login/", wait_until="networkidle")
        page.fill('input[name="username"]', 'marmotadmin')
        page.fill('input[name="password"]', 'marmotadmin@2026')
        page.click('button[type="submit"]')
        page.wait_for_timeout(2000)

        print("2. Navigating to Gateway Emulator / Live Mock...")
        page.goto("http://localhost:8050/admins/dashboard/live-mock/", wait_until="networkidle")
        page.wait_for_timeout(3000)

        # Capture initial screenshot
        shot1 = os.path.join(SCREENSHOT_DIR, "36_live_mock_option_chain_before.png")
        page.screenshot(path=shot1, full_page=True)
        print(f"Captured: {shot1}")

        # Start emulator replay if standby
        play_btn = page.query_selector('button:has-text("Play Replay"), button:has-text("Start"), button:has-text("Resume")')
        if play_btn:
            print("Clicking play button...")
            play_btn.click()
            page.wait_for_timeout(3000)

        # Let it stream at 1x speed for several ticks
        print("Observing option chain updates...")
        for i in range(5):
            page.wait_for_timeout(2000)
            rows = page.query_selector_all('#live-option-chain-tbody tr')
            print(f"\n--- Minute observation {i+1} (Rows: {len(rows)}) ---")
            for r in rows[8:22]: # Sample 14 strikes around ATM
                text = r.inner_text().replace('\n', ' | ')
                print("  ", text)

        # Capture final observation screenshot
        shot2 = os.path.join(SCREENSHOT_DIR, "37_live_mock_option_chain_scrambled.png")
        page.screenshot(path=shot2, full_page=True)
        print(f"\nCaptured final screenshot: {shot2}")

        browser.close()

if __name__ == '__main__':
    audit_option_chain()
