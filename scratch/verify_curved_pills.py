import os
import sys
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')

artifacts_dir = r"C:\Users\appzf\.gemini\antigravity-ide\brain\cdc6f7c5-2723-4a9b-b928-8e840f939a87"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={'width': 1600, 'height': 900})
    page = context.new_page()

    # Login
    print("Logging in...")
    page.goto("http://127.0.0.1:8050/admins/login/")
    page.fill('input[name="username"]', 'marmotadmin')
    page.fill('input[name="password"]', 'marmotadmin@2026')
    page.click('button[type="submit"]')
    page.wait_for_timeout(2000)

    # 1. Backtest Detail (Image 3: Trade P&L, Cumulative Equity, Opening Balance)
    print("Navigating to Backtest Detail 11...")
    page.goto("http://127.0.0.1:8050/backtest/11/")
    page.wait_for_timeout(2500)
    page.screenshot(path=os.path.join(artifacts_dir, "curved_backtest_detail.png"))

    # 2. Sandbox Journal (Image 4: Year filter outline & Executed badge)
    print("Navigating to Sandbox Journal...")
    page.goto("http://127.0.0.1:8050/admins/dashboard/sandbox/journal/")
    page.wait_for_timeout(2500)
    page.screenshot(path=os.path.join(artifacts_dir, "curved_sandbox_journal.png"))

    # 3. Live Dashboard close-up (Image 1: Accounts & Tokens)
    print("Navigating to Live Dashboard...")
    page.goto("http://127.0.0.1:8050/admins/dashboard/live/")
    page.wait_for_timeout(2000)
    # Grab header actions bounding box if possible
    header_el = page.locator('.page-header-actions, .d-flex.align-items-center.gap-2.flex-wrap').first
    if header_el:
        header_el.screenshot(path=os.path.join(artifacts_dir, "crop_live_header.png"))

    # 4. Saved Sessions filter section close-up (Image 2: Mode & Rating filter)
    print("Navigating to Saved Sessions...")
    page.goto("http://127.0.0.1:8050/admins/dashboard/gateway-emulator/sessions/")
    page.wait_for_timeout(2000)
    filter_el = page.locator('.card-filter').first
    if filter_el:
        filter_el.screenshot(path=os.path.join(artifacts_dir, "crop_saved_sessions_filter.png"))

    browser.close()
    print("Verification complete! All screenshots captured.")
