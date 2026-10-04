from playwright.sync_api import sync_playwright

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
    bento = page.query_selector('.col-12.col-xl-5')
    if bento:
        with open('scratch/bento_dump.html', 'w', encoding='utf-8') as f:
            f.write(bento.inner_html())
        print("Wrote bento_dump.html successfully")
    browser.close()
