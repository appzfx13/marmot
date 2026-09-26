import requests
from apps.common.models import SiteSettings

def run_tests():
    s = SiteSettings.load()
    headers = {
        'Authorization': f'{s.fyers_app_id}:{s.fyers_access_token}',
        'Accept': 'application/json'
    }
    url = 'https://api-t1.fyers.in/data/history/fno/expired/historical-data'

    # Testing various date ranges and contracts
    test_cases = [
        # (Symbol, Resolution, range_from, range_to, description)
        ("NSE:NIFTY26SEP25000CE", "5S", "2026-09-21", "2026-09-22", "Recent monthly (last 5 days) 5S resolution"),
        ("NSE:NIFTY26SEP25000CE", "1", "2026-09-21", "2026-09-22", "Recent monthly (last 5 days) 1m resolution"),
        ("NSE:NIFTY26SEP25000CE", "5S", "2026-08-25", "2026-08-26", "Monthly 31 days ago 5S resolution (>30 trading days check)"),
        ("NSE:NIFTY26AUG24500CE", "5S", "2026-08-25", "2026-08-26", "August Monthly 5S resolution"),
        ("NSE:NIFTY26AUG24500CE", "1", "2026-08-25", "2026-08-26", "August Monthly 1m resolution"),
        ("NSE:NIFTY2480124500CE", "1", "2024-07-25", "2024-07-26", "2024 weekly 1m resolution"),
        ("NSE:NIFTY24AUG24500CE", "1", "2024-08-20", "2024-08-21", "2024 monthly 1m resolution"),
        ("NSE:NIFTY24AUG24500CE", "5S", "2024-08-20", "2024-08-21", "2024 monthly 5S resolution (Older than 30 days)"),
    ]

    print("=== FYERS EXPIRED FNO HISTORICAL DATA API VERIFICATION ===\n")
    for sym, res, r_from, r_to, desc in test_cases:
        p = {
            'symbol': sym,
            'resolution': res,
            'date_format': '1',
            'range_from': r_from,
            'range_to': r_to,
            'include_oi': '1',
        }
        try:
            r = requests.get(url, params=p, headers=headers, timeout=5)
            data = r.json()
            candles = data.get('candles', [])
            count = len(candles)
            status = data.get('s')
            msg = data.get('message') or data.get('msg')
            first_c = candles[0] if count > 0 else None
            last_c = candles[-1] if count > 0 else None
            print(f"[{desc}]")
            print(f"  Request: {sym} | Res={res} | Range: {r_from} to {r_to}")
            print(f"  Response: HTTP {r.status_code} | Status={status} | Message={msg} | Candles={count}")
            if first_c:
                print(f"  First candle ({len(first_c)} fields): {first_c}")
                print(f"  Last candle: {last_c}")
        except Exception as e:
            print(f"  Error: {e}")
        print()

if __name__ == '__main__':
    run_tests()
