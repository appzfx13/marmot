import os
import sys
import time
from playwright.sync_api import sync_playwright

if sys.stdout:
    sys.stdout.reconfigure(encoding='utf-8')

BASE_URL = "https://manuals-rhythm-recordings-tracks.trycloudflare.com"
ARTIFACT_DIR = r"C:\Users\appzf\.gemini\antigravity-ide\brain\04588b54-8408-4acb-89e4-8cbf69d157c4"

def capture_oc():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1100})
        page = context.new_page()

        page.goto(f"{BASE_URL}/admins/login/", timeout=35000)
        page.wait_for_load_state("networkidle")
        if page.locator('#id_admin_username').count() > 0:
            page.fill('#id_admin_username', "marmotadmin")
            page.fill('#id_admin_password', "marmotadmin@2026")
            page.click('#adminSubmitBtn')
            page.wait_for_load_state("networkidle")
            time.sleep(2)

        page.goto(f"{BASE_URL}/admins/dashboard/live-mock/", timeout=35000)
        page.wait_for_load_state("networkidle")
        time.sleep(3)

        oc_el = page.locator("#live-option-chain-container")
        if oc_el.count() > 0:
            oc_el.scroll_into_view_if_needed()
            time.sleep(1)

        page.screenshot(path=os.path.join(ARTIFACT_DIR, "33_live_mock_option_chain_badge.png"))
        print("[+] Saved 33_live_mock_option_chain_badge.png")
        browser.close()

if __name__ == "__main__":
    capture_oc()
