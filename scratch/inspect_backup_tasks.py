import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'marmot.settings')
django.setup()

from apps.market.models import MarketBackupTask
for t in MarketBackupTask.objects.all().order_by('-id')[:5]:
    fields = {k: str(v) for k, v in t.__dict__.items() if not k.startswith('_')}
    print(fields)

