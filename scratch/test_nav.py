from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context()
    page = ctx.new_page()
    page.goto('http://localhost:8050/admins/login/')
    page.fill('input[name="username"]', 'marmotadmin')
    page.fill('input[name="password"]', 'marmotadmin@2026')
    page.click('button[type="submit"]')
    page.wait_for_timeout(3000)
    print('After login URL:', page.url)
    resp = page.goto('http://localhost:8050/admins/dashboard/sandbox/?account_id=3')
    print('Sandbox status:', resp.status, 'URL:', page.url)
    print('Has live-positions-container:', bool(page.query_selector('#live-positions-container')))
    if not page.query_selector('#live-positions-container'):
        print('Page title:', page.title())
        print('Heading:', page.inner_text('h1, h2, h3, .card-title') if page.query_selector('h1, h2, h3, .card-title') else 'None')
    b.close()
