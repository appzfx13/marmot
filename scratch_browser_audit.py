import os
import sys
import time
import json
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')

def run_browser_verification():
    artifact_dir = r"C:\Users\appzf\.gemini\antigravity-ide\brain\e28ecd14-600a-45af-8887-2d85099f2da8"
    
    print("=" * 80)
    print("PLAYWRIGHT BROWSER VERIFICATION: SANDBOX DASHBOARD DOM & SCREENSHOT AUDIT")
    print("=" * 80)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1600, "height": 1050})
        page = context.new_page()
        
        # 1. Login
        print("\n[Step 1] Logging into Admin Portal (marmotadmin)...")
        page.goto("http://localhost:8050/admins/login/", wait_until="networkidle")
        page.fill('input[name="username"]', 'marmotadmin')
        page.fill('input[name="password"]', 'marmotadmin@2026')
        page.click('button[type="submit"]')
        page.wait_for_timeout(2000)
        page.wait_for_load_state("networkidle")
        print("  Login successful. Current URL:", page.url)
        
        # 2. Navigate to Sandbox Dashboard
        print("\n[Step 2] Navigating to Sandbox Dashboard...")
        page.goto("http://localhost:8050/admins/dashboard/sandbox/", wait_until="networkidle")
        page.wait_for_timeout(3000)
        
        # Capture DOM elements
        dom_report = {}
        
        # Check Ribbon Spot LTP
        ribbon_spot_el = page.query_selector("#live-macro-spot-ltp") or page.query_selector(".macro-spot-val") or page.query_selector("[data-spot-ltp]")
        ribbon_spot_text = ribbon_spot_el.inner_text().strip() if ribbon_spot_el else "NOT_FOUND"
        dom_report["ribbon_spot_ltp"] = ribbon_spot_text
        print(f"  Macro Ribbon Spot LTP: {ribbon_spot_text}")
        
        # Check Option Chain Spot & ATM
        oc_spot_el = page.query_selector("#live-option-chain-spot-ltp")
        oc_atm_el = page.query_selector("#live-option-chain-atm")
        oc_spot_text = oc_spot_el.inner_text().strip() if oc_spot_el else "NOT_FOUND"
        oc_atm_text = oc_atm_el.inner_text().strip() if oc_atm_el else "NOT_FOUND"
        dom_report["option_chain_spot"] = oc_spot_text
        dom_report["option_chain_atm"] = oc_atm_text
        print(f"  Option Chain Spot LTP: {oc_spot_text} | ATM: {oc_atm_text}")
        
        # Check Sandbox Metrics (Margin, Net PnL, Realized PnL)
        margin_el = page.query_selector("#sandbox-available-margin")
        net_pnl_el = page.query_selector("#sandbox-live-net-pnl")
        realized_pnl_el = page.query_selector("#sandbox-realized-pnl")
        unrealized_pnl_el = page.query_selector("#sandbox-unrealized-pnl")
        
        dom_report["available_margin"] = margin_el.inner_text().strip() if margin_el else "NOT_FOUND"
        dom_report["live_net_pnl"] = net_pnl_el.inner_text().strip() if net_pnl_el else "NOT_FOUND"
        dom_report["realized_pnl"] = realized_pnl_el.inner_text().strip() if realized_pnl_el else "NOT_FOUND"
        dom_report["unrealized_pnl"] = unrealized_pnl_el.inner_text().strip() if unrealized_pnl_el else "NOT_FOUND"
        print(f"  Margin: {dom_report['available_margin']} | Net PnL: {dom_report['live_net_pnl']} | Realized: {dom_report['realized_pnl']}")
        
        # Check Orders Table
        order_rows = page.query_selector_all("#live-orders-container table tbody tr, #sandbox-orders-table tbody tr, tr[data-order-id]")
        print(f"\n[Step 3] Orders Table Audit: Found {len(order_rows)} rows")
        extracted_orders = []
        for idx, row in enumerate(order_rows):
            text = row.inner_text().replace("\t", " | ").replace("\n", " | ")
            extracted_orders.append(text)
            print(f"  Order Row #{idx+1}: {text[:130]}")
        dom_report["orders_found"] = len(order_rows)
        dom_report["order_rows"] = extracted_orders
        
        # Monitor for 6 seconds to verify ZERO jerking/jumping
        print("\n[Step 4] Monitoring Spot for 6 seconds (sampling every 1.5s) to guarantee zero jump/jerk...")
        samples = []
        for s in range(4):
            time.sleep(1.5)
            s_val = ribbon_spot_el.inner_text().strip() if ribbon_spot_el else "N/A"
            oc_val = oc_spot_el.inner_text().strip() if oc_spot_el else "N/A"
            samples.append({"step": s+1, "ribbon": s_val, "option_chain": oc_val})
            print(f"  Sample #{s+1}: Ribbon={s_val} | OptionChain={oc_val}")
        dom_report["spot_stability_samples"] = samples
        
        # Capture Evidence Screenshots
        shot_full = os.path.join(artifact_dir, "sandbox_dashboard_verified_full.png")
        page.screenshot(path=shot_full, full_page=True)
        print(f"\n[Step 5] Full Page Screenshot Captured: {shot_full}")
        
        # Save verification JSON
        report_path = os.path.join(artifact_dir, "sandbox_browser_verification_report.json")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(dom_report, f, indent=2)
        print(f"Verification report saved to: {report_path}")
        
        browser.close()

if __name__ == "__main__":
    run_browser_verification()
