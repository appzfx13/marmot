import sys
from playwright.sync_api import sync_playwright

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('http://127.0.0.1:8050/admins/login/')
    page.fill('input[name="username"]', 'marmotadmin')
    page.fill('input[name="password"]', 'marmotadmin@2026')
    page.click('button[type="submit"]')
    page.wait_for_url('**/admins/dashboard/**')
    page.goto('http://127.0.0.1:8050/admins/dashboard/gateway-emulator/')
    page.wait_for_selector('#gateway-emulator-container')
    
    # unlock if locked
    unlock = page.query_selector('button:has-text("Unlock")')
    if unlock:
        print("Clicking unlock...")
        unlock.click()
        page.wait_for_timeout(1000)
    
    # open dropdown
    print("Opening dropdown...")
    page.click('#backupDatasetDropdownBtn')
    page.wait_for_timeout(500)
    
    # attach request logger
    requests_made = []
    page.on('request', lambda r: requests_made.append((r.method, r.url, r.post_data)))
    
    # find task 33 button
    btn = page.query_selector('button:has-text("Task #33")')
    print('Found Task 33 button:', bool(btn))
    if btn:
        print("Clicking button for Task 33...")
        btn.click()
        page.wait_for_timeout(3000)
    print('Requests made on click:', requests_made)

    # Check active task in bento
    bento = page.query_selector(".col-12.col-xl-5")
    if bento:
        print("Bento content:")
        for line in bento.inner_text().splitlines():
            if line.strip():
                print("  ", line.strip())

    browser.close()
