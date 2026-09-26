import os
import sys
import time
from playwright.sync_api import sync_playwright
BASE_URL = "https://manuals-rhythm-recordings-tracks.trycloudflare.com"
ARTIFACT_DIR = r"C:\Users\appzf\.gemini\antigravity-ide\brain\04588b54-8408-4acb-89e4-8cbf69d157c4"

def verify_5s_e2e():
    print("=" * 60)
    print("STEP: Browser Verification with Playwright")
    print("=" * 60)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 950})
        page = context.new_page()

        # Login
        print("[*] Logging in...")
        page.goto(f"{BASE_URL}/admins/login/", timeout=35000)
        page.wait_for_load_state("networkidle")
        if page.locator('#id_admin_username').count() > 0:
            page.fill('#id_admin_username', "marmotadmin")
            page.fill('#id_admin_password', "marmotadmin@2026")
            page.click('#adminSubmitBtn')
            page.wait_for_load_state("networkidle")
            time.sleep(2)

        # 1. Admin Backup Form
        print("[*] Visiting Admin Backup Form: /market/backup/create/")
        page.goto(f"{BASE_URL}/market/backup/create/", timeout=35000)
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        sw_5s = page.locator('input[name="use_30_days_5s"]')
        is_5s_checked = sw_5s.first.is_checked() if sw_5s.count() > 0 else False
        strike_val = page.locator('input[name="strike_count"]').first.input_value() if page.locator('input[name="strike_count"]').count() > 0 else "N/A"
        print(f"[*] Admin Form - 5S Switch Checked: {is_5s_checked} (Expected: True)")
        print(f"[*] Admin Form - Default Strike Count: {strike_val} (Expected: 15)")

        admin_form_shot = os.path.join(ARTIFACT_DIR, "48_admin_backup_form_default_5s.png")
        page.screenshot(path=admin_form_shot)
        print(f"[+] Saved screenshot: {admin_form_shot}")

        # 2. User Market Backups Page & Modal
        print("[*] Visiting Market Backups Dashboard: /market/backup/")
        page.goto(f"{BASE_URL}/market/backup/", timeout=35000)
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        page_list_shot = os.path.join(ARTIFACT_DIR, "49_market_backup_dashboard_tasks.png")
        page.screenshot(path=page_list_shot)
        print(f"[+] Saved screenshot: {page_list_shot}")

        # 3. View Task #25 Detail & Parquet Inspection
        print("[*] Visiting Task #25 Detail: /market/backup/25/")
        page.goto(f"{BASE_URL}/market/backup/25/", timeout=35000)
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        task_detail_shot = os.path.join(ARTIFACT_DIR, "50_parquet_dataset_inspection.png")
        page.screenshot(path=task_detail_shot)
        print(f"[+] Saved screenshot: {task_detail_shot}")

        browser.close()
        print("\n[Playwright Verification Complete]")

if __name__ == "__main__":
    verify_5s_e2e()
