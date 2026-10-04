import json
import time
import os
import sys
from playwright.sync_api import sync_playwright

def run_pnl_widgets_verification():
    screenshot_path = "C:/Users/appzf/.gemini/antigravity-ide/brain/e28ecd14-600a-45af-8887-2d85099f2da8/pnl_widgets_verified.png"
    report_json_path = "C:/Users/appzf/.gemini/antigravity-ide/brain/e28ecd14-600a-45af-8887-2d85099f2da8/pnl_widgets_verified.json"

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"]
        )
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        print("[TEST] Logging into Admin Portal...")
        page.goto("http://localhost:8050/admins/login/", wait_until="networkidle")
        page.fill('input[name="username"]', 'marmotadmin')
        page.fill('input[name="password"]', 'marmotadmin@2026')
        page.click('button[type="submit"]')
        page.wait_for_url("**/admins/dashboard/**", timeout=15000)

        print("[TEST] Navigating to Sandbox Dashboard...")
        page.goto("http://localhost:8050/admins/dashboard/sandbox/?account_id=3", wait_until="networkidle", timeout=30000)
        page.wait_for_selector("#live-positions-container", timeout=10000)
        page.wait_for_timeout(3000)

        # 1. Summary Cards
        net_pnl_card = page.inner_text("#sandbox-live-net-pnl") if page.query_selector("#sandbox-live-net-pnl") else "N/A"
        realized_pnl_card = page.inner_text("#sandbox-realized-pnl") if page.query_selector("#sandbox-realized-pnl") else "N/A"
        unrealized_pnl_card = page.inner_text("#sandbox-unrealized-pnl") if page.query_selector("#sandbox-unrealized-pnl") else "N/A"

        # 2. Positions Table Sub-header
        pos_header_realized = page.inner_text("#live-positions-realized-pnl") if page.query_selector("#live-positions-realized-pnl") else "N/A"
        pos_header_unrealized = page.inner_text("#live-positions-unrealized-pnl") if page.query_selector("#live-positions-unrealized-pnl") else "N/A"
        pos_header_net = page.inner_text("#live-positions-net-pnl") if page.query_selector("#live-positions-net-pnl") else "N/A"

        # 3. Position Rows Data
        rows_data = page.evaluate("""() => {
            const rows = document.querySelectorAll('#live-positions-container tbody tr[data-symbol]');
            const data = [];
            rows.forEach(r => {
                const sym = r.getAttribute('data-symbol') || '';
                const ltpEl = r.querySelector('.pos-live-ltp');
                const unrlEl = r.querySelector('.pos-live-unrealized');
                const totEl = r.querySelector('.pos-live-total');
                const tds = r.querySelectorAll('td');
                const realizedText = tds.length > 5 ? tds[5].innerText.trim() : '';
                data.push({
                    symbol: sym,
                    ltp: ltpEl ? ltpEl.innerText.trim() : '',
                    realized: realizedText,
                    unrealized: unrlEl ? unrlEl.innerText.trim() : '',
                    total: totEl ? totEl.innerText.trim() : '',
                    totalClass: totEl ? totEl.className : ''
                });
            });
            return data;
        }""")

        # 4. Position P&L Distribution Bar Chart instance
        chart_data = page.evaluate("""() => {
            if (window._positionPnlBarChartInstance) {
                return {
                    labels: window._positionPnlBarChartInstance.data.labels,
                    data: window._positionPnlBarChartInstance.data.datasets[0].data,
                    bgColors: window._positionPnlBarChartInstance.data.datasets[0].backgroundColor
                };
            }
            return null;
        }""")

        # 5. Intraday Equity Curve Chart instance & Badges
        intraday_data = page.evaluate("""() => {
            const cardHeader = document.querySelector('.card:has(#liveIntradayEquityChart)');
            const pnlText = cardHeader ? (cardHeader.querySelector('.fw-extrabold') ? cardHeader.querySelector('.fw-extrabold').innerText.trim() : '') : '';
            const badgeText = cardHeader ? (cardHeader.querySelector('.badge') ? cardHeader.querySelector('.badge').innerText.trim() : '') : '';
            let chartInfo = null;
            if (window._intradayChartInstance) {
                chartInfo = {
                    labels: window._intradayChartInstance.data.labels,
                    data: window._intradayChartInstance.data.datasets[0].data
                };
            }
            return {
                headerPnl: pnlText,
                badge: badgeText,
                chart: chartInfo
            };
        }""")

        # Take full page screenshot
        page.screenshot(path=screenshot_path, full_page=True)
        print(f"[TEST] Full page screenshot saved to {screenshot_path}")

        result = {
            "summary_cards": {
                "net_pnl": net_pnl_card,
                "realized_pnl": realized_pnl_card,
                "unrealized_pnl": unrealized_pnl_card
            },
            "positions_table_header": {
                "realized": pos_header_realized,
                "unrealized": pos_header_unrealized,
                "net": pos_header_net
            },
            "position_rows": rows_data,
            "distribution_chart": chart_data,
            "intraday_equity_curve": intraday_data
        }

        with open(report_json_path, "w") as f:
            json.dump(result, f, indent=2)

        print("[TEST RESULT JSON]:")
        print(json.dumps(result, indent=2))
        browser.close()

if __name__ == "__main__":
    run_pnl_widgets_verification()
