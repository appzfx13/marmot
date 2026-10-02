import sys
import os

sys.path.insert(0, '/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'marmot.settings')

import django
django.setup()

import time
from apps.common.services.live_feed_service import get_live_index_option_chain, get_live_contract_market_quote

# 1. Test Mock Option Chain
t0 = time.perf_counter()
chain_mock = get_live_index_option_chain('NIFTY', is_mock=True)
t_mock = (time.perf_counter() - t0) * 1000.0

# 2. Test Live Option Chain
t0 = time.perf_counter()
chain_live = get_live_index_option_chain('NIFTY', is_mock=False)
t_live = (time.perf_counter() - t0) * 1000.0

# 3. Test Contract Quote
t0 = time.perf_counter()
quote = get_live_contract_market_quote('NIFTY 24 OCT 24500 CE')
t_quote = (time.perf_counter() - t0) * 1000.0

print(f"MOCK Chain Latency: {t_mock:.2f} ms | Spot: {chain_mock.get('spot_ltp')} | Strikes: {len(chain_mock.get('strikes', []))}")
print(f"LIVE Chain Latency: {t_live:.2f} ms | Status: {chain_live.get('feed_status')} | Strikes: {len(chain_live.get('strikes', []))}")
print(f"Contract Quote Latency: {t_quote:.2f} ms | LTP: {quote}")
