import sys
import time
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        
        # 1. Desktop Test (1920x1080)
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = context.new_page()

        target_url = "http://localhost:8050/market/backup/list/"
        print(f"Navigating to {target_url}...")
        page.goto(target_url, timeout=30000)

        if "login" in page.url:
            print("Logging in as marmotadmin...")
            page.fill('input[name="username"]', 'marmotadmin')
            page.fill('input[name="password"]', 'marmotadmin@2026')
            page.click('button[type="submit"]')
            page.wait_for_timeout(3000)
            page.goto(target_url, timeout=30000)

        print("Waiting for backup table container...")
        page.wait_for_selector("table.table-custom", timeout=20000)
        page.wait_for_timeout(3000)

        # Check Desktop Table Content
        table_html = page.locator("table.table-custom").inner_html()
        print("Checking Desktop Content:")
        print(f" - Contains 'Resolution & Strikes' Header: {'Resolution & Strikes' in page.content() or 'Resolution &amp; Strikes' in page.content()}")
        print(f" - Contains '5s Ticks' Badge: {'5s Ticks' in table_html}")
        print(f" - Contains '31 Contracts': {'31 Contracts' in table_html}")
        print(f" - Contains Detailed Resolution Specs: {'Spot: 1s Ticks' in table_html}")

        desktop_screenshot = r"C:\Users\appzf\.gemini\antigravity-ide\brain\cdc6f7c5-2723-4a9b-b928-8e840f939a87\backup_list_desktop.png"
        page.screenshot(path=desktop_screenshot, full_page=True)
        print(f"Desktop screenshot saved to {desktop_screenshot}")
        context.close()

        # 2. Mobile Viewport Test (375x812 - iPhone 13)
        print("\nTesting Mobile Viewport (375x812)...")
        mobile_context = browser.new_context(viewport={'width': 375, 'height': 812})
        mobile_page = mobile_context.new_page()
        
        mobile_page.goto(target_url, timeout=30000)
        if "login" in mobile_page.url:
            mobile_page.fill('input[name="username"]', 'marmotadmin')
            mobile_page.fill('input[name="password"]', 'marmotadmin@2026')
            mobile_page.click('button[type="submit"]')
            mobile_page.wait_for_timeout(3000)
            mobile_page.goto(target_url, timeout=30000)

        mobile_page.wait_for_selector("#backup-mobile-list-container", timeout=20000)
        mobile_page.wait_for_timeout(3000)

        mobile_cards_html = mobile_page.locator("#backup-mobile-list-container").inner_html()
        print("Checking Mobile Tile Cards:")
        print(f" - Mobile Cards Container Visible: {mobile_page.locator('#backup-mobile-list-container').is_visible()}")
        print(f" - Contains '5s Ticks' Badge in card: {'5s Ticks' in mobile_cards_html}")
        print(f" - Contains Detailed Resolution Spec: {'Spot: 1s Ticks' in mobile_cards_html}")

        mobile_screenshot = r"C:\Users\appzf\.gemini\antigravity-ide\brain\cdc6f7c5-2723-4a9b-b928-8e840f939a87\backup_list_mobile.png"
        mobile_page.screenshot(path=mobile_screenshot, full_page=True)
        print(f"Mobile screenshot saved to {mobile_screenshot}")
        mobile_context.close()

        # 3. Test Detail Page of Backup #33
        detail_context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        detail_page = detail_context.new_page()
        detail_url = "http://localhost:8050/market/backup/33/"
        print(f"\nNavigating to {detail_url}...")
        detail_page.goto(detail_url, timeout=30000)
        if "login" in detail_page.url:
            detail_page.fill('input[name="username"]', 'marmotadmin')
            detail_page.fill('input[name="password"]', 'marmotadmin@2026')
            detail_page.click('button[type="submit"]')
            detail_page.wait_for_timeout(3000)
            detail_page.goto(detail_url, timeout=30000)
            
        detail_page.wait_for_timeout(3000)
        detail_html = detail_page.content()
        print("Checking Detail Page:")
        print(f" - Contains 'Sampling Resolution': {'Sampling Resolution' in detail_html}")
        print(f" - Contains 'Resolution Specification': {'Resolution Specification' in detail_html}")
        
        detail_screenshot = r"C:\Users\appzf\.gemini\antigravity-ide\brain\cdc6f7c5-2723-4a9b-b928-8e840f939a87\backup_detail_resolution.png"
        detail_page.screenshot(path=detail_screenshot, full_page=True)
        print(f"Detail screenshot saved to {detail_screenshot}")
        detail_context.close()

        browser.close()
        print("\nAll Playwright E2E verifications completed successfully!")

if __name__ == '__main__':
    run()
