import os
import sys
import time
import json
import django

# Set up Django environment
sys.path.insert(0, '/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'marmot.settings')
django.setup()

from apps.backtest.models import BacktestTask
from apps.market.models import MarketBackupTask
from apps.backtest.services import send_backtest_control_command
from django.contrib.auth import get_user_model

User = get_user_model()
admin_user = User.objects.filter(is_superuser=True).first() or User.objects.first()

backup_task = MarketBackupTask.objects.filter(id=49).first()
if not backup_task:
    print("❌ Backup task #49 not found!")
    sys.exit(1)

print(f"✅ Found Backup Task #49: {backup_task.index_name} | {backup_task.parquet_file_path}")

# Create new Backtest Task for ict_sweep_choch
task = BacktestTask.objects.create(
    strategy_name="ict_sweep_choch",
    index_name="NIFTY",
    start_date="2026-10-08",
    end_date="2026-10-09",
    initial_capital=100000.0,
    parameters={
        "strategy_name": "ict_sweep_choch",
        "rule_type": "ict_sweep_choch",
        "ema_fast": 9,
        "ema_slow": 21,
        "rr_ratio": 2.5,
        "sl_pts": 12.0,
        "min_displacement": 0.45,
        "order_type": "LIMIT",
        "enable_retest_layering": True,
        "layer_count": 3,
        "retest_percentages": [25.0, 50.0, 75.0],
        "layer_lots": [1, 1, 1],
        "cooldown_seconds": 120,
    },
    backup_task=backup_task,
    status="created",
    created_by=admin_user
)

print(f"🚀 Created Backtest Task #{task.id}. Dispatching START command...")
send_backtest_control_command(task.id, "START")

# Monitor until complete
for _ in range(60):
    time.sleep(2)
    task.refresh_from_db()
    print(f"⏳ Task #{task.id} Status: {task.status} | Progress: {task.progress}%")
    if task.status in ['completed', 'error', 'failed', 'cancelled']:
        break

task.refresh_from_db()
print(f"\n🏁 Task #{task.id} Final Status: {task.status}")
if task.error_logs:
    print(f"Error logs: {task.error_logs}")

print("Metrics:", json.dumps(task.metrics, indent=2))

possible_paths = [
    task.result_file_path,
    f"/app/go-app/data/users/{task.created_by_id}/backtests/backtest_{task.id}.json",
    f"/app/data/users/{task.created_by_id}/backtests/backtest_{task.id}.json",
]
result_file = next((p for p in possible_paths if p and os.path.exists(p)), None)
if result_file:
    print(f"\n📋 Reading trades from {result_file}:")
    with open(result_file, 'r', encoding='utf-8') as f:
        for idx, line in enumerate(f, 1):
            if line.strip():
                tr = json.loads(line.strip())
                sig_t = tr.get('signal_timestamp', 'N/A')
                ent_t = tr.get('timestamp', 'N/A')
                ex_t = tr.get('exit_timestamp', 'N/A')
                strike = tr.get('strike', 'N/A')
                en_p = tr.get('entry_price', 0)
                ex_p = tr.get('exit_price', 0)
                pnl = tr.get('pnl', 0)
                stat = tr.get('status', 'N/A')
                retest_dur = tr.get('retest_duration_minutes', 0)
                print(f"  #{idx}: Strike={strike} | Signal={sig_t} -> Entry={ent_t} (Retest: {retest_dur}m) -> Exit={ex_t} | Entry=₹{en_p} | Exit=₹{ex_p} | PnL=₹{pnl} ({stat})")
else:
    print(f"⚠️ Result file {result_file} not found on disk.")
