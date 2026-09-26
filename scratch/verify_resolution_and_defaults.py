import os
import sys
import time
from playwright.sync_api import sync_playwright

if sys.stdout:
    sys.stdout.reconfigure(encoding='utf-8')

BASE_URL = "https://manuals-rhythm-recordings-tracks.trycloudflare.com"
ARTIFACT_DIR = r"C:\Users\appzf\.gemini\antigravity-ide\brain\04588b54-8408-4acb-89e4-8cbf69d157c4"

def verify_resolution_and_defaults():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 950})
        page = context.new_page()

        print("[1] Logging into Marmot Admin...")
        page.goto(f"{BASE_URL}/admins/login/", timeout=35000)
        page.wait_for_load_state("networkidle")
        if page.locator('#id_admin_username').count() > 0:
            page.fill('#id_admin_username', "marmotadmin")
            page.fill('#id_admin_password', "marmotadmin@2026")
            page.click('#adminSubmitBtn')
            page.wait_for_load_state("networkidle")
            time.sleep(2)

        # 2. Check Backup Download Form (/market/backup/create/)
        print("[2] Visiting Market Backups create page (/market/backup/create/)...")
        page.goto(f"{BASE_URL}/market/backup/create/", timeout=35000)
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        # Look for strike_count input
        strike_input = page.locator('input[name="strike_count"]')
        if strike_input.count() > 0:
            val = strike_input.first.input_value()
            print(f"[*] Default Strike Count Input Value: '{val}' (Expected: '15')")
        else:
            print("[-] strike_count input not found directly, checking modal or page content")

        page.screenshot(path=os.path.join(ARTIFACT_DIR, "34_backup_download_form_strike15.png"))
        print("[+] Saved 34_backup_download_form_strike15.png")

        # 3. Check Live Mock Dashboard & Strategy / Replay consistency
        print("[3] Visiting Mock Dashboard (/admins/dashboard/live-mock/)...")
        page.goto(f"{BASE_URL}/admins/dashboard/live-mock/", timeout=35000)
        page.wait_for_load_state("networkidle")
        time.sleep(3)

        clock_val = page.locator("#live-exchange-clock-time").inner_text().strip() if page.locator("#live-exchange-clock-time").count() > 0 else "N/A"
        speed_val = page.locator("#mock-feed-speed-val").inner_text().strip() if page.locator("#mock-feed-speed-val").count() > 0 else "N/A"
        feed_status = page.locator("#mock-feed-status-badge").inner_text().strip() if page.locator("#mock-feed-status-badge").count() > 0 else "N/A"

        print(f"[*] Replay Clock Time: '{clock_val}'")
        print(f"[*] Replay Speed: '{speed_val}x'")
        print(f"[*] Feed Status: '{feed_status}'")

        page.screenshot(path=os.path.join(ARTIFACT_DIR, "35_quant_engine_consistent_replay.png"))
        print("[+] Saved 35_quant_engine_consistent_replay.png")

        browser.close()
        print("\n[VERIFICATION COMPLETE]")

if __name__ == "__main__":
    verify_resolution_and_defaults()
