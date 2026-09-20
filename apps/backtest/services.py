import json
import os
import threading
import time
import redis
from django.conf import settings
from apps.common.constants import REDIS_CHANNEL
from apps.common.logger import Logger
from .models import BacktestTask

logger = Logger(section="BACKTEST", app="backtest", log_type="services")

REDIS_URL = settings.REDIS_URL
redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)


class BacktestControlRegistry:
    """Thread-safe in-memory controller for coordinating Pause, Resume, and Cancel signals."""
    _lock = threading.Lock()
    _controllers = {}

    @classmethod
    def register(cls, task_id: int):
        with cls._lock:
            pause_event = threading.Event()
            pause_event.set()
            cancel_event = threading.Event()
            cls._controllers[int(task_id)] = {
                "pause_event": pause_event,
                "cancel_event": cancel_event,
            }
            return cancel_event, pause_event

    @classmethod
    def get(cls, task_id: int):
        with cls._lock:
            return cls._controllers.get(int(task_id))

    @classmethod
    def pause(cls, task_id: int):
        with cls._lock:
            ctrl = cls._controllers.get(int(task_id))
            if ctrl:
                ctrl["pause_event"].clear()
                return True
            return False

    @classmethod
    def resume(cls, task_id: int):
        with cls._lock:
            ctrl = cls._controllers.get(int(task_id))
            if ctrl:
                ctrl["pause_event"].set()
                return True
            return False

    @classmethod
    def cancel(cls, task_id: int):
        with cls._lock:
            ctrl = cls._controllers.get(int(task_id))
            if ctrl:
                ctrl["cancel_event"].set()
                ctrl["pause_event"].set()
                return True
            return False

    @classmethod
    def cleanup(cls, task_id: int):
        with cls._lock:
            cls._controllers.pop(int(task_id), None)


def broadcast_backtest_progress(task_id, progress: int, status: str, net_pnl: float = 0.0, total_trades: int = 0, step_info: str = ""):
    """Broadcasts live progress update to Redis Pub/Sub and WebSocket clients."""
    try:
        payload = {
            "type": "progress",
            "task_id": str(task_id),
            "progress": int(progress),
            "status": status,
            "net_pnl": float(net_pnl),
            "total_trades": int(total_trades),
            "step_info": str(step_info),
        }
        t_qs = BacktestTask.objects.filter(id=task_id)
        curr_status = t_qs.values_list('status', flat=True).first()
        if curr_status in [BacktestTask.StatusChoices.PAUSED, BacktestTask.StatusChoices.CANCELLED] and status == BacktestTask.StatusChoices.RUNNING:
            return
        t_qs.update(progress=progress, status=status)
        pub_count = redis_client.publish(REDIS_CHANNEL, json.dumps(payload))
        print(f"📡 [BROADCAST-PROGRESS] Task #{task_id} -> {progress}% ({status}) | Step: {step_info} | PnL: ₹{net_pnl:,.2f} | Trades: {total_trades} | Redis Pub Subscribed Clients: {pub_count}", flush=True)
    except Exception as e:
        print(f"❌ [BROADCAST-PROGRESS ERROR] Task #{task_id}: {e}", flush=True)
        logger.error("Failed to broadcast backtest progress", exc=e, extra={"task_id": task_id})


def create_and_start_backtest_task(strategy_name, index_name, start_date, end_date, initial_capital, parameters, user, backup_task=None, use_macro_assist=False, macro_timeframe='1h', macro_backup_task=None, enable_ai_lot_sizing=False, auto_risk_management=True, max_risk_per_trade_pct=2.00, max_capital_utilization_pct=60.00, max_lots_cap=10):
    """Creates a BacktestTask DB entry in CREATED status without auto-starting."""
    task = BacktestTask.objects.create(
        strategy_name=strategy_name,
        index_name=index_name,
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
        parameters=parameters or {},
        backup_task=backup_task,
        use_macro_assist=use_macro_assist,
        macro_timeframe=macro_timeframe or '1h',
        macro_backup_task=macro_backup_task,
        enable_ai_lot_sizing=enable_ai_lot_sizing,
        auto_risk_management=auto_risk_management,
        max_risk_per_trade_pct=max_risk_per_trade_pct,
        max_capital_utilization_pct=max_capital_utilization_pct,
        max_lots_cap=max_lots_cap,
        status=BacktestTask.StatusChoices.CREATED,
        created_by=user
    )
    return task


def send_backtest_control_command(task_id, command):
    """Sends START_BACKTEST, PAUSE, RESUME, or CANCEL command to Go Engine or Python RL worker."""
    task = BacktestTask.objects.get(id=task_id)
    cmd = command.upper()

    if cmd in ['START', 'START_BACKTEST', 'RERUN', 'RESTART']:
        if task.results and isinstance(task.results, dict) and task.metrics:
            from .models import BacktestRunLog
            run_num = task.run_logs.count() + 1
            BacktestRunLog.objects.create(
                task=task,
                run_number=run_num,
                status=task.status,
                metrics=task.metrics,
                applied_rules=[r.name for r in task.rules.all()],
                notes=f"Snapshot of run #{run_num} before re-run execution.",
                created_by=task.created_by
            )
        # Sync task.parameters['rules'] from current M2M so Go always receives
        # the latest attached rules, not the stale snapshot from task creation.
        current_params = dict(task.parameters or {})
        current_params['use_macro_assist'] = bool(task.use_macro_assist)
        current_params['rules'] = [
            {
                'id': r.id,
                'name': r.name,
                'rule_type': r.rule_type,
                'prompt_directive': r.prompt_directive or '',
                'parameters': r.parameters or {},
            }
            for r in task.rules.filter(is_active=True)
        ]
        task.parameters = current_params
        task.status = BacktestTask.StatusChoices.RUNNING
        task.progress = 5
        task.error_logs = ""
        task.results = {}
        task.metrics = {}

        # Cleanly purge stale trade result file on disk from previous runs
        user_id = str(task.created_by_id or '1')
        candidate_files = [
            task.result_file_path,
            f"/app/go-app/data/users/{user_id}/backtests/backtest_{task.id}.json",
            f"/app/data/users/{user_id}/backtests/backtest_{task.id}.json",
            os.path.join(settings.BASE_DIR, 'go-app', 'data', 'users', user_id, 'backtests', f'backtest_{task.id}.json'),
            os.path.join(settings.BASE_DIR, 'data', 'users', user_id, 'backtests', f'backtest_{task.id}.json'),
        ]
        for c_file in candidate_files:
            if c_file and os.path.exists(c_file):
                try:
                    os.remove(c_file)
                except Exception:
                    pass
        task.result_file_path = ""

        task.save(update_fields=['status', 'progress', 'error_logs', 'results', 'metrics', 'parameters', 'result_file_path'])
        broadcast_backtest_progress(task.id, 5, BacktestTask.StatusChoices.RUNNING, step_info="Starting Go Quantitative Rule Engine backtest execution...")
    elif cmd == 'RESUME':
        BacktestControlRegistry.resume(task.id)
        task.status = BacktestTask.StatusChoices.RUNNING
        task.save(update_fields=['status'])
        broadcast_backtest_progress(task.id, task.progress or 10, BacktestTask.StatusChoices.RUNNING, step_info="Resuming backtest execution...")
    elif cmd == 'PAUSE':
        task.status = BacktestTask.StatusChoices.PAUSED
        task.save(update_fields=['status'])
        BacktestControlRegistry.pause(task.id)
        broadcast_backtest_progress(task.id, task.progress or 0, BacktestTask.StatusChoices.PAUSED, step_info="Backtest paused by user.")
    elif cmd in ['CANCEL', 'STOP']:
        task.status = BacktestTask.StatusChoices.CANCELLED
        task.save(update_fields=['status'])
        BacktestControlRegistry.cancel(task.id)
        broadcast_backtest_progress(task.id, task.progress or 0, BacktestTask.StatusChoices.CANCELLED, step_info="Backtest cancelled by user.")

    # Also notify Redis for Go service or external subscribers
    payload = {
        "task_id": str(task.id),
        "command": cmd,
        "params": {
            "strategy_name": task.strategy_name,
            "index_name": task.index_name,
            "start_date": task.start_date.isoformat(),
            "end_date": task.end_date.isoformat(),
            "initial_capital": task.initial_capital,
            "user_id": str(task.created_by.id if getattr(task, 'created_by', None) else 1),
            "backup_task_id": str(task.backup_task.id) if task.backup_task else "",
            "params": task.parameters or {}
        }
    }
    try:
        redis_client.publish(REDIS_CHANNEL, json.dumps(payload))
    except Exception as e:
        logger.warning(f"Redis publish warning: {e}")

    return task
