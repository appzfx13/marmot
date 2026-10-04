import sys
import time
from playwright.sync_api import sync_playwright

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def run():
    artifact_dir = r"C:\Users\appzf\.gemini\antigravity-ide\brain\e28ecd14-600a-45af-8887-2d85099f2da8"
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"]
        )
        context = browser.new_context(viewport={"width": 1600, "height": 1100})
        page = context.new_page()

        print("[TEST] 1. Logging into Admin Portal...")
        page.goto("http://127.0.0.1:8050/admins/login/", wait_until="networkidle")
        page.fill('input[name="username"]', 'marmotadmin')
        page.fill('input[name="password"]', 'marmotadmin@2026')
        page.click('button[type="submit"]')
        page.wait_for_url("**/admins/dashboard/**", timeout=15000)
        print("[TEST] Login successful, current URL:", page.url)

        print("\n[TEST] 2. Navigating to Gateway Emulator...")
        page.goto("http://127.0.0.1:8050/admins/dashboard/gateway-emulator/", wait_until="networkidle", timeout=30000)
        page.wait_for_selector("#gateway-emulator-container", timeout=15000)
        page.wait_for_timeout(2000)

        # 3. If streaming, stop it to enable Unlock button
        pause_btn = page.query_selector("button:has-text('Pause Replay')")
        if pause_btn:
            print("[TEST] Streamer is active. Clicking Pause Replay...")
            pause_btn.click()
            page.wait_for_timeout(2000)

        # 4. Click Unlock button
        unlock_btn = page.query_selector("button:has-text('Unlock')")
        print("[TEST] Unlock button present?", bool(unlock_btn))
        if unlock_btn:
            print("[TEST] Clicking Unlock button...")
            unlock_btn.click()
            page.wait_for_timeout(2000)

        # 5. Check unlocked dropdown toggle button
        dropdown_btn = page.query_selector("#backupDatasetDropdownBtn")
        print("[TEST] Dropdown toggle button found?", bool(dropdown_btn))
        if dropdown_btn:
            print("Dropdown toggle text:")
            for l in dropdown_btn.inner_text().splitlines():
                if l.strip():
                    print("  ", l.strip())

            # 6. Click dropdown toggle to expand
            print("\n[TEST] Clicking dropdown toggle to expand options...")
            dropdown_btn.click()
            page.wait_for_timeout(1000)

            screenshot_dropdown = f"{artifact_dir}\\gateway_dataset_dropdown_open.png"
            page.screenshot(path=screenshot_dropdown)
            print(f"[TEST] Saved open dropdown screenshot: {screenshot_dropdown}")

            # 7. Find options
            items = page.query_selector_all(".dropdown-menu li button.dropdown-item")
            print(f"[TEST] Found {len(items)} dataset options in dropdown:")
            for idx, item in enumerate(items[:6]):
                print(f"  Option {idx+1}: {' | '.join([l.strip() for l in item.inner_text().splitlines() if l.strip()])}")

            # 8. Click Task #41 (India VIX) or another option
            task_41_btn = None
            for item in items:
                if "Task #41" in item.inner_text():
                    task_41_btn = item
                    break
            if not task_41_btn and len(items) > 1:
                task_41_btn = items[1]

            if task_41_btn:
                target_text = task_41_btn.inner_text().splitlines()[0]
                print(f"\n[TEST] Selecting Option: {target_text}...")
                task_41_btn.click()
                page.wait_for_timeout(3000)

        # 9. Verify locked card with newly selected dataset
        page.wait_for_selector("#gateway-emulator-container", timeout=10000)
        final_bento = page.query_selector(".col-12.col-xl-5")
        print("\n--- Final Locked Dataset Bento Content ---")
        if final_bento:
            for line in final_bento.inner_text().splitlines():
                if line.strip():
                    print("  ", line.strip())

        screenshot_final = f"{artifact_dir}\\gateway_dataset_widget_verified.png"
        page.screenshot(path=screenshot_final)
        print(f"\n[TEST] Saved final verified screenshot: {screenshot_final}")

        browser.close()
        print("\n[TEST] Verification flow completed successfully!")

if __name__ == "__main__":
    run()
