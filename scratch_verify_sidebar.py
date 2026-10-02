import os
from playwright.sync_api import sync_playwright

output_dir = r"C:\Users\appzf\.gemini\antigravity-ide\brain\cdc6f7c5-2723-4a9b-b928-8e840f939a87"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width': 1400, 'height': 900})
    page.goto('http://127.0.0.1:8050/admins/login/')
    
    # Check if already logged in or needs login
    if 'login' in page.url:
        page.fill('input[name="username"]', 'marmotadmin')
        page.fill('input[name="password"]', 'marmotadmin@2026')
        page.click('button[type="submit"]')
        page.wait_for_timeout(2000)
    
    page.goto('http://127.0.0.1:8050/admins/dashboard/')
    page.wait_for_timeout(2000)
    
    # Take screenshot of sidebar
    sidebar = page.locator('.sidebar-wrapper, .sidebar, #adminSidebarNav').first
    sidebar.screenshot(path=os.path.join(output_dir, "verified_sidebar.png"))
    
    # Also take screenshot of the entire page
    page.screenshot(path=os.path.join(output_dir, "verified_admin_full.png"))
    print("Screenshots captured successfully!")
    browser.close()
