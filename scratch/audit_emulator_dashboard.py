import os
from playwright.sync_api import sync_playwright

SCREENSHOT_DIR = r"C:\Users\appzf\.gemini\antigravity-ide\brain\04588b54-8408-4acb-89e4-8cbf69d157c4"

def audit_emulator_dashboard():
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

        print("2. Navigating to Gateway Emulator...")
        page.goto("http://localhost:8050/admins/dashboard/gateway-emulator/", wait_until="networkidle")
        page.wait_for_timeout(3000)

        # Expand 31 strikes if button exists
        expand_btn = page.query_selector('#btn-toggle-option-chain-strikes')
        if expand_btn:
            print("Expanding 31 strikes...")
            expand_btn.click()
            page.wait_for_timeout(1000)

        # Start replay
        play_btn = page.query_selector('button:has-text("Play Replay"), button:has-text("Start"), button:has-text("Resume")')
        if play_btn:
            print("Starting playback...")
            play_btn.click()
            page.wait_for_timeout(3000)

        shot = os.path.join(SCREENSHOT_DIR, "40_dhan_gateway_emulator_page.png")
        page.screenshot(path=shot, full_page=True)
        print(f"Captured: {shot}")

        # Capture specifically the option chain table / card
        chain_el = page.query_selector('#live-option-chain-container')
        if chain_el:
            shot_chain = os.path.join(SCREENSHOT_DIR, "41_dhan_gateway_option_chain_card.png")
            chain_el.screenshot(path=shot_chain)
            print(f"Captured chain card: {shot_chain}")

        browser.close()

if __name__ == '__main__':
    audit_emulator_dashboard()
