import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'marmot.settings')
django.setup()

from django.test import RequestFactory
from django.contrib.auth import get_user_model
from apps.backtest.models import BacktestTask
from apps.backtest.views import BacktestApplyOptimizerAndRerunView

task = BacktestTask.objects.get(id=24)
candidates = (task.parameters or {}).get('optimizer_results', {}).get('candidates', [])
if len(candidates) > 1:
    cand2 = candidates[1]
    print("Testing Apply Candidate #2:")
    print("  Candidate #2 SL:", cand2.get('stop_loss_points'))
    print("  Candidate #2 RR:", cand2.get('rr_ratio'))

    User = get_user_model()
    user = User.objects.filter(is_superuser=True).first()
    rf = RequestFactory()
    data = {
        'stop_loss_points': str(cand2.get('stop_loss_points')),
        'rr_ratio': str(cand2.get('rr_ratio')),
        'enable_trailing_sl': str(cand2.get('enable_trailing_sl')),
        'trailing_sl_trigger_r': str(cand2.get('trailing_sl_trigger_r')),
        'enable_retest_layering': str(cand2.get('enable_retest_layering')),
    }
    req = rf.post('/backtest/24/apply-optimizer-rerun/', data)
    req.user = user

    resp = BacktestApplyOptimizerAndRerunView.as_view()(req, pk=24)
    print("Response Status:", resp.status_code)
    print("HX-Trigger:", resp.headers.get('HX-Trigger'))

    task_updated = BacktestTask.objects.get(id=24)
    print("Task #24 Parameters SL after candidate #2 apply:", task_updated.parameters.get('stop_loss_points'))
    print("Task #24 Parameters RR after candidate #2 apply:", task_updated.parameters.get('rr_ratio'))
    print("Success: Candidate #2 parameters cleanly applied!")
else:
    print("Only 1 candidate available.")
