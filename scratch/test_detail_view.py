import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'marmot.settings')
django.setup()

from django.test import RequestFactory
from django.contrib.auth import get_user_model
from apps.backtest.views import BacktestDetailView

User = get_user_model()
user = User.objects.filter(is_superuser=True).first()
rf = RequestFactory()
req = rf.get('/backtest/24/')
req.user = user

resp = BacktestDetailView.as_view()(req, pk=24)
print('Detail View Response Status:', resp.status_code)
resp.render()
content = resp.content.decode('utf-8')
print('Has Optimizer Widget:', 'id="backtest-optimizer-widget"' in content)
print('Has Winner in Detail page:', 'RANK #1 WINNER' in content)
print('Has Apply Button in Detail page:', 'Apply Winner & Re-Run Backtest' in content)
print('Has Header Button:', 'Strategy Optimizer' in content)
