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

print("[TEST] Running Comprehensive E2E Verification for Trade Chart Features...")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1600, "height": 950})
    page = context.new_page()

    console_logs = []
    page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))
    page.on("pageerror", lambda err: console_logs.append(f"[PAGE_ERROR] {err}"))

    # Step 1: Login
    print("[1] Logging in as admin...")
    page.goto(f"{base_url}/admins/login/", wait_until="networkidle")
    page.fill('input[name="username"]', 'marmotadmin')
    page.fill('input[name="password"]', 'marmotadmin@2026')
    page.click('button[type="submit"]')
    page.wait_for_url("**/admins/dashboard/**", timeout=15000)

    # Step 2: Navigate to Trade 1 Chart
    print("[2] Navigating to /backtest/14/trade/1/chart/...")
    resp = page.goto(f"{base_url}/backtest/14/trade/1/chart/", wait_until="networkidle")
    print(f"    HTTP Status: {resp.status}")
    page.wait_for_timeout(3500)

    # Step 3: Check UI Buttons & Initial State
    initial_state = page.evaluate("""() => {
        const btnSync = document.querySelector('#btnToggleScrollSync');
        const btnFocus = document.querySelector('#btnFocusTrade');
        const spotTfBtns = Array.from(document.querySelectorAll('#spotTfGroup .btn-tf')).map(b => ({
            tf: b.getAttribute('data-tf'),
            active: b.classList.contains('active')
        }));
        const optionTfBtns = Array.from(document.querySelectorAll('#optionTfGroup .btn-tf')).map(b => ({
            tf: b.getAttribute('data-tf'),
            active: b.classList.contains('active')
        }));

        const spotRange = window.spotChart ? window.spotChart.timeScale().getVisibleRange() : null;
        const optRange = window.optionChart ? window.optionChart.timeScale().getVisibleRange() : null;

        return {
            hasBtnSync: !!btnSync,
            syncLabel: btnSync ? btnSync.innerText.trim() : null,
            hasBtnFocus: !!btnFocus,
            spotTfBtns: spotTfBtns,
            optionTfBtns: optionTfBtns,
            spotRange: spotRange,
            optRange: optRange,
            rawSpotCount: window.rawTradeData ? (window.rawTradeData.spot_candles || []).length : 0,
            rawOptCount: window.rawTradeData ? (window.rawTradeData.candles || []).length : 0,
        };
    }""")
    print("[3] Initial State:", initial_state)

    # Step 4: Test Independent Horizontal Scrolling on Option Chart
    print("[4] Testing Independent Horizontal Scrolling on Option Pane...")
    # Record ranges before drag
    ranges_before = page.evaluate("""() => ({
        spot: window.spotChart.timeScale().getVisibleRange(),
        option: window.optionChart.timeScale().getVisibleRange()
    })""")
    
    # Drag option chart horizontally by 300px
    opt_box = page.locator('#optionChartContainer').bounding_box()
    if opt_box:
        start_x = opt_box['x'] + opt_box['width'] * 0.7
        start_y = opt_box['y'] + opt_box['height'] * 0.5
        page.mouse.move(start_x, start_y)
        page.mouse.down()
        page.mouse.move(start_x - 300, start_y, steps=10)
        page.mouse.up()
        page.wait_for_timeout(500)

    ranges_after_drag = page.evaluate("""() => ({
        spot: window.spotChart.timeScale().getVisibleRange(),
        option: window.optionChart.timeScale().getVisibleRange()
    })""")

    print(f"    Before drag: Spot={ranges_before['spot']} | Option={ranges_before['option']}")
    print(f"    After drag:  Spot={ranges_after_drag['spot']} | Option={ranges_after_drag['option']}")
    spot_unchanged = (ranges_before['spot']['from'] == ranges_after_drag['spot']['from'])
    option_changed = (ranges_before['option']['from'] != ranges_after_drag['option']['from'])
    print(f"    => Spot range remained untouched: {spot_unchanged}")
    print(f"    => Option range moved independently: {option_changed}")

    # Step 5: Test Independent Timeframe (Switch Option chart to 10s)
    print("[5] Testing Independent Strike Timeframe to 10s...")
    page.click('#optionTfGroup button[data-tf="10s"]')
    page.wait_for_timeout(1000)

    tf_state = page.evaluate("""() => {
        const spotActive = document.querySelector('#spotTfGroup .btn-tf.active');
        const optActive = document.querySelector('#optionTfGroup .btn-tf.active');
        return {
            spotActiveTf: spotActive ? spotActive.getAttribute('data-tf') : null,
            optActiveTf: optActive ? optActive.getAttribute('data-tf') : null,
        };
    }""")
    print(f"    Active Timeframes => Spot: {tf_state['spotActiveTf']} | Option: {tf_state['optActiveTf']}")

    # Step 6: Test Focus Trade Button
    print("[6] Testing Focus Trade Button...")
    page.click('#btnFocusTrade')
    page.wait_for_timeout(800)

    ranges_after_focus = page.evaluate("""() => ({
        spot: window.spotChart.timeScale().getVisibleRange(),
        option: window.optionChart.timeScale().getVisibleRange()
    })""")
    print(f"    After Focus => Spot: {ranges_after_focus['spot']} | Option: {ranges_after_focus['option']}")

    # Step 7: Test Toggle Scroll Sync
    print("[7] Testing Scroll Sync Toggle...")
    page.click('#btnToggleScrollSync')
    page.wait_for_timeout(500)
    sync_btn_text = page.locator('#scrollSyncLabel').inner_text()
    print(f"    Button text after toggle: {sync_btn_text}")

    # Step 8: Capture Screenshot
    screenshot_path = os.path.join(artifacts_dir, "trade_1_dual_chart_10s_verified.png")
    page.screenshot(path=screenshot_path, full_page=True)
    print(f"[8] Verification screenshot saved: {screenshot_path}")

    print("\n--- Console Errors/Logs ---")
    errors = [l for l in console_logs if "error" in l.lower()]
    for e in errors:
        print(e)
    if not errors:
        print("Zero console errors!")

    browser.close()
