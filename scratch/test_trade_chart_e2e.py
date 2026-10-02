import sys
import time
from playwright.sync_api import sync_playwright

# Ensure utf-8 output so emojis & unicode characters don't fail on Windows cp1252
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = context.new_page()

        console_logs = []
        page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))

        target_url = "http://localhost:8050/backtest/10/trade/2/chart/"
        print(f"Navigating to {target_url}...")
        page.goto(target_url, timeout=30000)

        # Handle login if redirected
        if "login" in page.url:
            print("Logging in as marmotadmin...")
            page.fill('input[name="username"]', 'marmotadmin')
            page.fill('input[name="password"]', 'marmotadmin@2026')
            page.click('button[type="submit"]')
            page.wait_for_timeout(3000)
            print(f"Post-login URL: {page.url}")
            print(f"Navigating to target URL: {target_url}")
            page.goto(target_url, timeout=30000)

        print("Waiting for chart containers (#spotChartContainer, #optionChartContainer)...")
        page.wait_for_selector("#spotChartContainer", timeout=20000)
        page.wait_for_selector("#optionChartContainer", timeout=20000)

        # Wait 8 seconds for data fetch and LightweightCharts rendering
        print("Waiting 8 seconds for data fetch and chart render...")
        page.wait_for_timeout(8000)

        # Verify scenario banner
        banner_text = page.locator("#scenarioBanner").inner_text()
        print(f"\n--- SCENARIO BANNER CONTENT ---\n{banner_text}\n------------------------------")

        # Verify date badge
        date_badge = page.locator("#dateRangeBadge").inner_text()
        print(f"Date Badge: {date_badge}")

        # Check console logs
        print(f"\nCaptured {len(console_logs)} console logs. Last 10:")
        for log in console_logs[-10:]:
            print(log)

        screenshot_path = r"C:\Users\appzf\.gemini\antigravity-ide\brain\cdc6f7c5-2723-4a9b-b928-8e840f939a87\trade_chart_verified.png"
        page.screenshot(path=screenshot_path, full_page=True)
        print(f"\nScreenshot saved successfully to {screenshot_path}")

        browser.close()

if __name__ == '__main__':
    run()
