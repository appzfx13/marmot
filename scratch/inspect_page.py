from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('http://localhost:8050/backtest/10/trade/2/chart/')
    print('URL 1:', page.url)
    if 'login' in page.url:
        page.fill('input[name="username"]', 'marmotadmin')
        page.fill('input[name="password"]', 'marmotadmin@2026')
        page.click('button[type="submit"]')
        page.wait_for_timeout(3000)
        print('URL 2:', page.url)
        res = page.goto('http://localhost:8050/backtest/10/trade/2/chart/')
        print('URL 3:', page.url, 'Status:', res.status if res else None)
        print('Title:', page.title())
        print('Snippet:', page.content()[:800])
        # Save screenshot
        page.screenshot(path=r'C:\Users\appzf\.gemini\antigravity-ide\brain\cdc6f7c5-2723-4a9b-b928-8e840f939a87\inspect_page.png')
    browser.close()
