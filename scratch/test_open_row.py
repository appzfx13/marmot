from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context()
    page = ctx.new_page()
    page.goto('http://localhost:8050/admins/login/')
    page.fill('input[name="username"]', 'marmotadmin')
    page.fill('input[name="password"]', 'marmotadmin@2026')
    page.click('button[type="submit"]')
    page.wait_for_timeout(2000)
    page.goto('http://localhost:8050/admins/dashboard/sandbox/?account_id=3')
    page.wait_for_timeout(2000)

    rows = page.evaluate("""() => {
        const list = [];
        document.querySelectorAll('#live-positions-container tbody tr').forEach(tr => {
            list.push({
                sym: tr.getAttribute('data-symbol'),
                status: tr.getAttribute('data-status'),
                buyAvg: tr.getAttribute('data-buy-avg'),
                qty: tr.getAttribute('data-qty')
            });
        });
        return list;
    }""")
    for r in rows:
        print(r)
    b.close()
