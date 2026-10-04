import time
import os
import sys
import json
import urllib.request

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from playwright.sync_api import sync_playwright

base_url = "http://localhost:8050"
artifacts_dir = r"C:\Users\appzf\.gemini\antigravity-ide\brain\e28ecd14-600a-45af-8887-2d85099f2da8"

print("[STEP 1] Querying current active option chain strikes from mock broker...")
try:
    chain_req = urllib.request.urlopen("http://localhost:8088/mock/v2/optionchain?index=NIFTY")
    chain_data = json.loads(chain_req.read().decode('utf-8'))
    active_strikes = [s for s in chain_data.get('strikes', []) if s.get('is_active_window')]
    if not active_strikes:
        active_strikes = chain_data.get('strikes', [])[:5]
    target_strike = active_strikes[len(active_strikes)//2]
    strike_val = target_strike['strike']
    target_sym = f"NIFTY {strike_val} CE"
    target_sec_id = f"{strike_val}_CE"
    target_ltp = target_strike['ce_ltp']
    print(f"[TARGET] Selected Strike: {strike_val}, Symbol: {target_sym}, Mock LTP: {target_ltp}")
except Exception as e:
    print(f"[WARN] Error querying option chain: {e}")
    strike_val = 24600
    target_sym = "NIFTY 24600 CE"
    target_sec_id = "24600_CE"
    target_ltp = 58.0

print(f"[STEP 2] Placing test MARKET BUY order for {target_sym}...")
try:
    order_payload = {
        "dhanClientId": "1000000001",
        "correlationId": f"VERIFY_SYNC_{strike_val}_CE",
        "transactionType": "BUY",
        "exchangeSegment": "NSE_FNO",
        "productType": "INTRADAY",
        "orderType": "MARKET",
        "validity": "DAY",
        "securityId": target_sec_id,
        "tradingSymbol": target_sym,
        "quantity": 50,
        "price": target_ltp
    }
    req = urllib.request.Request(
        "http://localhost:8088/mock/v2/orders",
        data=json.dumps(order_payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    with urllib.request.urlopen(req) as resp:
        res = json.loads(resp.read().decode('utf-8'))
        print(f"[ORDER] Placed order result: {res}")
except Exception as e:
    print(f"[ERROR] Failed to place order: {e}")

# Wait 2 seconds for mock broker tick matching
time.sleep(2)

print("[STEP 3] Launching Playwright browser to test Sandbox Dashboard in real-time...")
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1440, "height": 950})
    page = context.new_page()

    print("[LOGIN] Authenticating Admin...")
    page.goto(f"{base_url}/admins/login/", wait_until="networkidle")
    page.fill('input[name="username"]', 'marmotadmin')
    page.fill('input[name="password"]', 'marmotadmin@2026')
    page.click('button[type="submit"]')
    page.wait_for_url("**/admins/dashboard/**", timeout=15000)
    print("[LOGIN] Authentication successful!")

    url = f"{base_url}/admins/dashboard/sandbox/?account_id=3"
    print(f"[NAV] Loading {url} ...")
    page.goto(url, wait_until="networkidle")
    page.wait_for_selector("#live-positions-container", timeout=10000)

    # Initial screenshot
    shot_0 = os.path.join(artifacts_dir, "sandbox_sync_0s.png")
    page.screenshot(path=shot_0)
    print(f"[SHOT] Captured initial screenshot: {shot_0}")

    def inspect_sync_state():
        return page.evaluate("""(targetStrike) => {
            const getTxt = (sel) => (document.querySelector(sel)?.textContent || '').trim();
            const openRows = [];
            document.querySelectorAll('#live-positions-container tbody tr[data-status="OPEN"]').forEach(tr => {
                const sym = tr.getAttribute('data-symbol') || '';
                const buyAvg = tr.getAttribute('data-buy-avg') || '';
                const qty = tr.getAttribute('data-qty') || '';
                const ltp = tr.querySelector('.pos-live-ltp')?.textContent.trim() || '';
                const unrl = tr.querySelector('.pos-live-unrealized')?.textContent.trim() || '';
                const total = tr.querySelector('.pos-live-total')?.textContent.trim() || '';
                const lastTick = tr.querySelector('.pos-live-ltp')?.getAttribute('data-last-tick') || '';
                openRows.push({ sym, buyAvg, qty, ltp, unrl, total, lastTick });
            });

            const closedRows = [];
            document.querySelectorAll('#live-positions-container tbody tr[data-status="CLOSED"]').forEach(tr => {
                const sym = tr.getAttribute('data-symbol') || '';
                const pnl = tr.getAttribute('data-pnl') || '';
                closedRows.push({ sym, pnl });
            });

            // Option chain lookup for target strike
            const ocCeLtp = getTxt(`[data-tick-key="ce_${targetStrike}"]`) || getTxt(`#oc-ltp-ce-${targetStrike}`);
            const ocPeLtp = getTxt(`[data-tick-key="pe_${targetStrike}"]`) || getTxt(`#oc-ltp-pe-${targetStrike}`);

            const cardNet = getTxt('#sandbox-live-net-pnl');
            const cardUnrealized = getTxt('#sandbox-unrealized-pnl');
            const cardRealized = getTxt('#sandbox-realized-pnl');
            const subNet = getTxt('#live-positions-net-pnl');
            const subUnrealized = getTxt('#live-positions-unrealized-pnl');

            return {
                openRows,
                closedRows,
                ocCeLtp,
                ocPeLtp,
                cardNet,
                cardUnrealized,
                cardRealized,
                subNet,
                subUnrealized
            };
        }""", strike_val)

    print("\n" + "="*80)
    print(f"OBSERVING REAL-TIME 1-MINUTE SIMULATION (60 SECONDS)")
    print("="*80)

    start_t = time.time()
    observations = []

    while time.time() - start_t < 60:
        elapsed = int(time.time() - start_t)
        state = inspect_sync_state()
        observations.append({"elapsed": elapsed, "state": state})

        # Find matching open position
        matching_pos = None
        for p_row in state['openRows']:
            if str(strike_val) in p_row['sym']:
                matching_pos = p_row
                break
        if not matching_pos and state['openRows']:
            matching_pos = state['openRows'][0]

        pos_ltp_str = matching_pos['ltp'] if matching_pos else 'None'
        pos_sym_str = matching_pos['sym'] if matching_pos else 'None'
        pos_unrl_str = matching_pos['unrl'] if matching_pos else 'None'
        oc_ltp_str = state['ocCeLtp']

        print(f"[{elapsed:02d}s/60s] Open: {len(state['openRows'])} | Pos: {pos_sym_str} | Pos LTP: {pos_ltp_str} | OC CE LTP: {oc_ltp_str} | Unrl PnL: {pos_unrl_str} | Net: {state['cardNet']}")

        if elapsed >= 30 and not any(o.get('shot30') for o in observations):
            observations[-1]['shot30'] = True
            shot_30 = os.path.join(artifacts_dir, "sandbox_sync_30s.png")
            page.screenshot(path=shot_30)
            print(f"[SHOT] Captured 30s screenshot: {shot_30}")

        page.wait_for_timeout(5000)

    shot_60 = os.path.join(artifacts_dir, "sandbox_sync_60s.png")
    page.screenshot(path=shot_60)
    print(f"[SHOT] Captured 60s screenshot: {shot_60}")

    browser.close()

print("\n" + "="*80)
print("VERIFICATION RUN COMPLETE")
print("="*80)
