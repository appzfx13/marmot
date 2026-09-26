import os
import sys
import time
from playwright.sync_api import sync_playwright

if sys.stdout:
    sys.stdout.reconfigure(encoding='utf-8')

BASE_URL = "https://manuals-rhythm-recordings-tracks.trycloudflare.com"
ARTIFACT_DIR = r"C:\Users\appzf\.gemini\antigravity-ide\brain\04588b54-8408-4acb-89e4-8cbf69d157c4"

def verify_all():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 950})
        page = context.new_page()

        print("[1] Logging into Marmot Admin (/admins/login/)...")
        page.goto(f"{BASE_URL}/admins/login/", timeout=35000)
        page.wait_for_load_state("networkidle")
        time.sleep(1)

        if page.locator('#id_admin_username').count() > 0:
            page.fill('#id_admin_username', "marmotadmin")
            page.fill('#id_admin_password', "marmotadmin@2026")
            page.click('#adminSubmitBtn')
            page.wait_for_load_state("networkidle")
            time.sleep(3)
            print("[+] Successfully logged into Marmot Admin!")

        print("[2] Visiting Gateway Emulator (/admins/dashboard/gateway-emulator/)...")
        page.goto(f"{BASE_URL}/admins/dashboard/gateway-emulator/", timeout=35000)
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        # Check button states
        start_btn = page.locator('button:has-text("Start Replay")')
        pause_btn = page.locator('button:has-text("Pause Replay")')
        stop_btn = page.locator('button:has-text("Stop & Rewind")')

        print(f"[*] Gateway Buttons -> Start: {start_btn.count()}, Pause: {pause_btn.count()}, Stop: {stop_btn.count()}")

        # Stop feed to ensure stopped state renders the green Start Replay button
        if stop_btn.count() > 0 and stop_btn.first.is_visible():
            print("[*] Clicking Stop & Rewind to test stopped state...")
            stop_btn.first.click()
            time.sleep(2)
            page.reload()
            page.wait_for_load_state("networkidle")
            time.sleep(1)

        start_btn_visible = page.locator('button:has-text("Start Replay")').first.is_visible() if page.locator('button:has-text("Start Replay")').count() > 0 else False
        print(f"[*] Is Start Replay button visible when stopped? {start_btn_visible}")
        page.screenshot(path=os.path.join(ARTIFACT_DIR, "29_gateway_emulator_stopped_state.png"))
        print("[+] Saved 29_gateway_emulator_stopped_state.png")

        # Now start replay
        print("[3] Clicking Start Replay...")
        if page.locator('button:has-text("Start Replay")').count() > 0:
            page.locator('button:has-text("Start Replay")').first.click()
            time.sleep(4)

        page.screenshot(path=os.path.join(ARTIFACT_DIR, "30_gateway_emulator_playing.png"))
        print("[+] Saved 30_gateway_emulator_playing.png")

        # Navigate to Mock Dashboard
        print("[4] Navigating to Mock Dashboard (/admins/dashboard/live-mock/)...")
        page.goto(f"{BASE_URL}/admins/dashboard/live-mock/", timeout=35000)
        page.wait_for_load_state("networkidle")
        time.sleep(4) # Let WebSocket ticks arrive

        # Inspect Top Clock HUD
        clock_time_el = page.locator("#live-exchange-clock-time")
        clock_time = clock_time_el.inner_text().strip() if clock_time_el.count() > 0 else "N/A"
        clock_zone_el = page.locator("#live-exchange-clock-zone")
        clock_zone = clock_zone_el.inner_text().strip() if clock_zone_el.count() > 0 else "N/A"
        clock_status_el = page.locator("#live-exchange-clock-status")
        clock_status = clock_status_el.inner_text().strip() if clock_status_el.count() > 0 else "N/A"
        clock_speed_badge = page.locator("#live-replay-speed-badge")
        clock_speed_text = clock_speed_badge.inner_text().strip() if clock_speed_badge.count() > 0 else "N/A"
        clock_speed_visible = clock_speed_badge.is_visible() if clock_speed_badge.count() > 0 else False

        print(f"[*] Clock HUD Time: '{clock_time}'")
        print(f"[*] Clock Zone: '{clock_zone}'")
        print(f"[*] Clock Status: '{clock_status}'")
        print(f"[*] Clock Speed Badge: '{clock_speed_text}' (visible={clock_speed_visible})")

        # Inspect Simulation Telemetry Card Widget
        telemetry_card = page.locator(".card:has-text('Historical Replay Telemetry')")
        has_telemetry_card = telemetry_card.count() > 0
        speed_val = page.locator("#mock-feed-speed-val").inner_text().strip() if page.locator("#mock-feed-speed-val").count() > 0 else "N/A"
        dataset_file = page.locator("#mock-feed-file-val").inner_text().strip() if page.locator("#mock-feed-file-val").count() > 0 else "N/A"
        rows_val = page.locator("#mock-feed-rows-val").inner_text().strip() if page.locator("#mock-feed-rows-val").count() > 0 else "N/A"
        pct_val = page.locator("#mock-feed-pct-val").inner_text().strip() if page.locator("#mock-feed-pct-val").count() > 0 else "N/A"
        feed_status = page.locator("#mock-feed-status-badge").inner_text().strip() if page.locator("#mock-feed-status-badge").count() > 0 else "N/A"

        print(f"[*] Historical Replay Telemetry Card Present: {has_telemetry_card}")
        print(f"[*] Speed Value: '{speed_val}'")
        print(f"[*] Dataset File: '{dataset_file}'")
        print(f"[*] Rows Processed: '{rows_val}'")
        print(f"[*] Progress Pct: '{pct_val}%'")
        print(f"[*] Feed Status Badge: '{feed_status}'")

        # Inspect Option Chain strike badges
        partial_badge = page.locator("span:has-text('Partial Dataset')")
        print(f"[*] Partial Dataset Badge Count: {partial_badge.count()} (Text: '{partial_badge.first.inner_text().strip() if partial_badge.count() > 0 else 'None'}')")

        page.screenshot(path=os.path.join(ARTIFACT_DIR, "31_live_mock_dashboard_time_sync.png"))
        print("[+] Saved 31_live_mock_dashboard_time_sync.png")

        # Scroll to telemetry card & option chain for high-res card capture
        page.evaluate("window.scrollTo(0, 150)")
        time.sleep(1)
        page.screenshot(path=os.path.join(ARTIFACT_DIR, "32_live_mock_speed_widget.png"))
        print("[+] Saved 32_live_mock_speed_widget.png")

        browser.close()
        print("\n[VERIFICATION COMPLETE]")

if __name__ == "__main__":
    verify_all()
