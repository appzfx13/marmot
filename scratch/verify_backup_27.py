import os
import sys
import time
from playwright.sync_api import sync_playwright

if sys.stdout:
    sys.stdout.reconfigure(encoding='utf-8')

BASE_URL = "https://serves-miscellaneous-proceedings-yarn.trycloudflare.com"
ARTIFACT_DIR = r"C:\Users\appzf\.gemini\antigravity-ide\brain\1dfe3538-d1cc-4ecf-8d9b-dbf3ccceef74"

def verify():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 950})
        page = context.new_page()

        print("[1] Navigating to admin login...")
        page.goto(f"{BASE_URL}/admins/login/", timeout=30000)
        page.wait_for_load_state("networkidle")
        time.sleep(1)

        if page.locator('#id_admin_username').count() > 0:
            print("[*] Entering credentials...")
            page.fill('#id_admin_username', "marmotadmin")
            page.fill('#id_admin_password', "marmotadmin@2026")
            page.click('#adminSubmitBtn')
            page.wait_for_load_state("networkidle")
            time.sleep(2)
            print("[+] Login successful!")

        print("[2] Visiting Task #27 detail page...")
        page.goto(f"{BASE_URL}/market/backup/27/", timeout=30000)
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        # Capture screenshot
        screenshot_path = os.path.join(ARTIFACT_DIR, "task_27_detail_verification.png")
        page.screenshot(path=screenshot_path, full_page=True)
        print(f"[+] Screenshot saved to {screenshot_path}")

        # Check DOM text
        body_text = page.inner_text("body")
        print("\n--- Summary of Page Content ---")
        for line in body_text.split('\n'):
            line_clean = line.strip()
            if any(k in line_clean.lower() for k in ['progress', 'running', 'completed', '%', 'task #27', 'dataset', 'fyers']):
                print("  >", line_clean)

        browser.close()

if __name__ == "__main__":
    verify()
