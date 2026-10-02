import os
from playwright.sync_api import sync_playwright

artifacts_dir = r"C:\Users\appzf\.gemini\antigravity-ide\brain\cdc6f7c5-2723-4a9b-b928-8e840f939a87"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width': 1600, 'height': 900})
    page.goto('http://127.0.0.1:8050/admins/login/')
    page.fill('input[name="username"]', 'marmotadmin')
    page.fill('input[name="password"]', 'marmotadmin@2026')
    page.click('button[type="submit"]')
    page.wait_for_timeout(2000)
    page.goto('http://127.0.0.1:8050/admins/journal/')
    page.wait_for_timeout(2500)
    page.screenshot(path=os.path.join(artifacts_dir, 'journal_full.png'))
    
    # Crop year toggle and badge
    yt = page.locator('.page-header .btn-group').first
    if yt:
        yt.screenshot(path=os.path.join(artifacts_dir, 'crop_journal_year.png'))
    browser.close()
    print("Saved journal_full.png and crop_journal_year.png")
