import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'marmot.settings')
django.setup()

from apps.common.models import PostbackLog

print("=== POSTBACK WEBHOOK AUDIT ===")
total = PostbackLog.objects.count()
print(f"Total Postback Logs: {total}")

recent = PostbackLog.objects.order_by('-id')[:15]
for p in recent:
    pl = p.payload or {}
    status = pl.get('orderStatus') or p.status
    sym = pl.get('tradingSymbol', 'N/A')
    side = pl.get('transactionType', 'N/A')
    price = pl.get('tradedPrice') or pl.get('price', 0)
    qty = pl.get('tradedQuantity') or pl.get('quantity', 0)
    leg = pl.get('legName', 'ENTRY')
    reason = pl.get('rejectionReason', '')
    print(f"ID: {p.id:4d} | Status: {status:8s} | Side: {side:4s} | Leg: {leg:10s} | Price: {price:7.2f} | Qty: {qty:3d} | Sym: {sym} | Reason: {reason}")
