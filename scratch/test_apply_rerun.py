import os
import django
import json

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'marmot.settings')
django.setup()

from django.test import RequestFactory
from django.contrib.auth import get_user_model
from apps.backtest.models import BacktestTask
from apps.backtest.views import BacktestApplyOptimizerAndRerunView

task_before = BacktestTask.objects.get(id=24)
print("Before Apply:")
print("  SL:", task_before.parameters.get('stop_loss_points'))
print("  RR:", task_before.parameters.get('rr_ratio'))
print("  Trailing:", task_before.parameters.get('enable_trailing_sl'))

User = get_user_model()
user = User.objects.filter(is_superuser=True).first()
rf = RequestFactory()
req = rf.post('/backtest/24/apply-optimizer-rerun/')
req.user = user

resp = BacktestApplyOptimizerAndRerunView.as_view()(req, pk=24)
print("Response Status:", resp.status_code)
print("HX-Trigger:", resp.headers.get('HX-Trigger'))

task_after = BacktestTask.objects.get(id=24)
print("After Apply:")
print("  SL:", task_after.parameters.get('stop_loss_points'))
print("  RR:", task_after.parameters.get('rr_ratio'))
print("  Trailing:", task_after.parameters.get('enable_trailing_sl'))
print("  Trail R:", task_after.parameters.get('trailing_sl_trigger_r'))
print("  Status:", task_after.status)
print("  Progress:", task_after.progress)
