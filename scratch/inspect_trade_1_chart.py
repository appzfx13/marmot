import os
import sys

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from playwright.sync_api import sync_playwright

base_url = "http://localhost:8050"
artifacts_dir = r"C:\Users\appzf\.gemini\antigravity-ide\brain\e28ecd14-600a-45af-8887-2d85099f2da8"

print("[INSPECT] Testing Trade 1 Chart Page: /backtest/14/trade/1/chart/...")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1440, "height": 950})
    page = context.new_page()

    console_logs = []
    page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))
    page.on("pageerror", lambda err: console_logs.append(f"[PAGE_ERROR] {err}"))

    # Step 1: Login
    print("[1] Logging in...")
    page.goto(f"{base_url}/admins/login/", wait_until="networkidle")
    page.fill('input[name="username"]', 'marmotadmin')
    page.fill('input[name="password"]', 'marmotadmin@2026')
    page.click('button[type="submit"]')
    page.wait_for_url("**/admins/dashboard/**", timeout=15000)

    # Step 2: Navigate to Trade 1 Chart
    print("[2] Navigating to /backtest/14/trade/1/chart/...")
    resp = page.goto(f"{base_url}/backtest/14/trade/1/chart/", wait_until="networkidle")
    print(f"    HTTP Status: {resp.status}")
    page.wait_for_timeout(3000)

    # Step 3: Inspect chart elements and data
    chart_info = page.evaluate("""() => {
        const spotPane = document.querySelector('#spot-chart-container');
        const optPane = document.querySelector('#option-chart-container');
        const spotHeader = document.querySelector('#spot-crosshair-bar') ? document.querySelector('#spot-crosshair-bar').innerText : '';
        const optHeader = document.querySelector('#option-crosshair-bar') ? document.querySelector('#option-crosshair-bar').innerText : '';
        const rawData = window.tradeChartRawData || null;
        return {
            hasSpotPane: !!spotPane,
            hasOptPane: !!optPane,
            spotHeader: spotHeader,
            optHeader: optHeader,
            candlesLoaded: rawData ? {
                spotCount: (rawData.spot_candles || []).length,
                optCount: (rawData.option_candles || []).length,
                spotError: rawData.spot_error || null,
                optError: rawData.option_error || null,
            } : null
        };
    }""")
    print("[3] Chart Info:", chart_info)

    # Step 4: Screenshot
    screenshot_path = os.path.join(artifacts_dir, "trade_1_chart_inspect.png")
    page.screenshot(path=screenshot_path, full_page=True)
    print(f"[4] Screenshot saved to: {screenshot_path}")

    print("\n--- Console Logs ---")
    for log in console_logs[:30]:
        print(log)

    browser.close()
