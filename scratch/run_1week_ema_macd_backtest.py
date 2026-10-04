import os
import sys
import time
import json
import datetime
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'marmot.settings')
django.setup()

from apps.users.models import User
from apps.market.models import MarketBackupTask
from apps.backtest.models import BacktestTask, BacktestRule
from apps.backtest.services import create_and_start_backtest_task, send_backtest_control_command


def run_1week_test():
    user = User.objects.filter(is_superuser=True).first()
    if not user:
        user = User.objects.first()
    print(f"👤 Using user: {user.username} (id={user.id})")

    backup_task = MarketBackupTask.objects.filter(id=33).first()
    if not backup_task:
        backup_task = MarketBackupTask.objects.filter(is_deleted=False, status='completed').order_by('-id').first()
    print(f"📦 Backup Task: #{backup_task.id} ({backup_task.index_name}) from {backup_task.start_date} to {backup_task.end_date} (file: {backup_task.parquet_file_path})")

    rule = BacktestRule.objects.filter(rule_type='ema_macd_retest').first()
    if not rule:
        print("❌ Error: BacktestRule for ema_macd_retest not found!")
        return

    print(f"⚙️ Strategy Rule: {rule.name} (id={rule.id})")
    params = dict(rule.parameters or {})
    params['strategy_name'] = 'ema_macd_retest'
    params['order_type'] = 'LIMIT'

    start_date = datetime.date(2026, 9, 24)
    end_date = datetime.date(2026, 10, 1)

    print(f"🚀 Creating BacktestTask for {start_date} to {end_date}...")
    task = create_and_start_backtest_task(
        strategy_name='ema_macd_retest',
        index_name='NIFTY',
        start_date=start_date,
        end_date=end_date,
        initial_capital=100000.0,
        parameters=params,
        user=user,
        backup_task=backup_task,
        use_macro_assist=False,
        use_vix_assist=False,
        enable_ai_lot_sizing=False,
        auto_risk_management=True,
    )
    task.rules.add(rule)
    print(f"✅ Created BacktestTask #{task.id} in status: {task.status}")

    print(f"📡 Dispatching START_BACKTEST command to Go engine via Redis...")
    send_backtest_control_command(task.id, 'START_BACKTEST')

    # Monitor progress
    max_wait = 60
    start_time = time.time()
    print("⏳ Waiting for Go engine execution...")

    while time.time() - start_time < max_wait:
        task.refresh_from_db()
        print(f"   [+{int(time.time() - start_time)}s] Status: {task.status} | Progress: {task.progress}%")
        if task.status in ['completed', 'failed', 'cancelled']:
            break
        time.sleep(2)

    task.refresh_from_db()
    print("\n" + "="*60)
    print(f"🏁 FINAL STATUS: {task.status.upper()} (Progress: {task.progress}%)")
    print("="*60)

    if task.error_logs:
        print(f"⚠️ Error Logs:\n{task.error_logs}")

    print(f"📊 Metrics:\n{json.dumps(task.metrics, indent=2)}")
    print(f"📁 Result File Path: {task.result_file_path}")

    # Inspect trade records from disk or DB
    trades = []
    if task.result_file_path and os.path.exists(task.result_file_path):
        with open(task.result_file_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line:
                    trades.append(json.loads(line))
    elif task.results and isinstance(task.results, dict) and 'trades' in task.results:
        trades = task.results['trades']

    print(f"\n📋 Total Executed Trades: {len(trades)}")
    for idx, tr in enumerate(trades, 1):
        print(f"  Trade #{idx}: {tr.get('Timestamp')} | {tr.get('Strike')} | {tr.get('TradeType')} | Entry: ₹{tr.get('EntryPrice')} | Exit: ₹{tr.get('ExitPrice')} | PnL: ₹{tr.get('PnL')} | Status: {tr.get('Status')} | Reason: {tr.get('Reason')}")

    return task.id


if __name__ == '__main__':
    run_1week_test()
