import os
import sys
from playwright.sync_api import sync_playwright

artifacts_dir = r"C:\Users\appzf\.gemini\antigravity-ide\brain\cdc6f7c5-2723-4a9b-b928-8e840f939a87"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width': 1600, 'height': 900})
    
    # Login
    page.goto('http://127.0.0.1:8050/admins/login/')
    page.fill('input[name="username"]', 'marmotadmin')
    page.fill('input[name="password"]', 'marmotadmin@2026')
    page.click('button[type="submit"]')
    page.wait_for_timeout(2000)
    
    # 1. Backtest Chart Tabs (Image 3)
    page.goto('http://127.0.0.1:8050/backtest/11/')
    page.wait_for_timeout(2000)
    el = page.locator('#btnModePnl').locator('..')
    el.scroll_into_view_if_needed()
    el.screenshot(path=os.path.join(artifacts_dir, 'crop_backtest_chart_tabs.png'))
    
    # 2. Sandbox Journal Year Tabs & Badges (Image 4)
    page.goto('http://127.0.0.1:8050/admins/dashboard/sandbox/journal/')
    page.wait_for_timeout(2000)
    # Header year toggle
    year_toggle = page.locator('.page-header .btn-group').first
    if year_toggle:
        year_toggle.screenshot(path=os.path.join(artifacts_dir, 'crop_journal_year_toggle.png'))
    
    # 3. Live Dashboard top right actions (Image 1)
    page.goto('http://127.0.0.1:8050/admins/dashboard/live/')
    page.wait_for_timeout(2000)
    live_header_actions = page.locator('.page-header-actions').first
    if live_header_actions:
        live_header_actions.screenshot(path=os.path.join(artifacts_dir, 'crop_live_header_actions.png'))
        
    browser.close()
    print("Done cropping targets!")
