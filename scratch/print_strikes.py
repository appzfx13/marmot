from apps.common.services.live_feed_service import get_mock_index_option_chain
from django.utils import timezone

res = get_mock_index_option_chain('NIFTY', 50, 'NIFTY 50', timezone.localdate())
print("Spot: %s | ATM: %s | Time: %s" % (res.get('spot_ltp'), res.get('atm_strike'), res.get('last_updated')))
print("%-8s | %-10s | %-12s | %-10s | %-12s" % ("Strike", "CE LTP", "CE OI", "PE LTP", "PE OI"))
print("-" * 60)
for s in res.get('strikes', []):
    print("%-8s | %-10s | %-12s | %-10s | %-12s" % (
        str(s.get('strike')),
        str(s.get('ce_ltp')),
        str(s.get('ce_oi')),
        str(s.get('pe_ltp')),
        str(s.get('pe_oi')),
    ))
