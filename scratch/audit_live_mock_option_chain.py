import os
import time
import urllib.request
from playwright.sync_api import sync_playwright

SCREENSHOT_DIR = r"C:\Users\appzf\.gemini\antigravity-ide\brain\04588b54-8408-4acb-89e4-8cbf69d157c4"

def audit_live_mock_option_chain():
    # First select dataset 1/20/dataset.parquet and start play
    print("Selecting 1/20/dataset.parquet and playing...")
    try:
        req = urllib.request.Request('http://localhost:8088/mock/api/streamer/select?file=1/20/dataset.parquet', data=b'', method='POST')
        urllib.request.urlopen(req)
        req2 = urllib.request.Request('http://localhost:8088/mock/api/streamer/toggle', data=b'', method='POST')
        urllib.request.urlopen(req2)
    except Exception as e:
        print("Streamer start error:", e)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1600, 'height': 1200})
        page = context.new_page()

        print("Logging in...")
        page.goto("http://localhost:8050/users/login/", wait_until="networkidle")
        page.fill('input[name="username"]', 'marmotadmin')
        page.fill('input[name="password"]', 'marmotadmin@2026')
        page.click('button[type="submit"]')
        page.wait_for_timeout(2000)

        print("Navigating to live-mock...")
        page.goto("http://localhost:8050/admins/dashboard/live-mock/", wait_until="networkidle")
        page.wait_for_timeout(4000)

        # Scroll to option chain container
        chain_el = page.query_selector('#live-option-chain-container')
        if chain_el:
            chain_el.scroll_into_view_if_needed()
            page.wait_for_timeout(1000)

            # Click expand strikes button if available
            expand_btn = page.query_selector('#btn-toggle-option-chain-strikes')
            if expand_btn:
                expand_btn.click()
                page.wait_for_timeout(1000)

            shot = os.path.join(SCREENSHOT_DIR, "42_live_mock_option_chain_expanded.png")
            chain_el.screenshot(path=shot)
            print(f"Captured option chain screenshot: {shot}")

            rows = page.query_selector_all('#live-option-chain-tbody tr')
            print(f"Total rows rendered: {len(rows)}")
            for idx, r in enumerate(rows):
                txt = r.inner_text().replace('\t', ' | ').replace('\n', ' | ')
                print(f"Row {idx+1}: {txt}")

        # Stop streamer
        try:
            req_stop = urllib.request.Request('http://localhost:8088/mock/api/streamer/toggle', data=b'', method='POST')
            urllib.request.urlopen(req_stop)
        except Exception:
            pass

        browser.close()

if __name__ == '__main__':
    audit_live_mock_option_chain()
