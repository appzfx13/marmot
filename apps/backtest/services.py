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
        task.status = BacktestTask.StatusChoices.RUNNING
        task.progress = 5
        task.error_logs = ""
        task.results = {}
        task.metrics = {}
        task.save(update_fields=['status', 'progress', 'error_logs', 'results', 'metrics'])
        broadcast_backtest_progress(task.id, 5, BacktestTask.StatusChoices.RUNNING, step_info="Starting RL backtest execution...")
        threading.Thread(target=execute_python_rl_backtest, args=(task.id,), daemon=True).start()
    elif cmd == 'RESUME':
        resumed = BacktestControlRegistry.resume(task.id)
        task.status = BacktestTask.StatusChoices.RUNNING
        task.save(update_fields=['status'])
        broadcast_backtest_progress(task.id, task.progress or 10, BacktestTask.StatusChoices.RUNNING, step_info="Resuming backtest execution...")
        if not resumed:
            threading.Thread(target=execute_python_rl_backtest, args=(task.id,), daemon=True).start()
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


def execute_python_rl_backtest(task_id):
    """Executes TensorTrade RL engine over task Parquet backup directory asynchronously."""
    from .rl_engine import TensorTradeRLEngine
    cancel_event, pause_event = BacktestControlRegistry.register(task_id)
    try:
        task = BacktestTask.objects.get(id=task_id)
        if task.backup_task and task.backup_task.is_macro_assist and task.backup_task.linked_backup_task:
            if not task.macro_backup_task:
                task.macro_backup_task = task.backup_task
            task.backup_task = task.backup_task.linked_backup_task
            task.save(update_fields=["backup_task", "macro_backup_task"])

        b_user_id = str(task.backup_task.created_by_id or task.created_by_id or 1) if task.backup_task else str(task.created_by_id or 1)
        backup_id = str(task.backup_task.id) if task.backup_task else str(task.id)
        backup_dir = os.path.join(str(settings.BASE_DIR), "backup", b_user_id, backup_id)
        if not os.path.exists(backup_dir) and task.backup_task:
            alt_dir = os.path.join(str(settings.BASE_DIR), "backup", "1", backup_id)
            if os.path.exists(alt_dir):
                backup_dir = alt_dir
        
        print(f"\n[TENSORTRADE-RL] >>> Launching RL Backtest Task #{task.id} | Index: {task.index_name} | Strategy: {task.strategy_name} | Capital: ₹{task.initial_capital} | Period: {task.start_date} → {task.end_date}", flush=True)
        logger.info(f"Launching RL Backtest Task #{task.id} ({task.index_name})")

        broadcast_backtest_progress(task.id, 5, BacktestTask.StatusChoices.RUNNING, step_info="Ingesting market dataset...")

        def on_rl_progress(progress, status, net_pnl, total_trades, step_info):
            broadcast_backtest_progress(
                task_id=task.id,
                progress=progress,
                status=status,
                net_pnl=net_pnl,
                total_trades=total_trades,
                step_info=step_info,
            )

        def check_control():
            if cancel_event.is_set():
                return "CANCEL"
            if not pause_event.is_set():
                return "PAUSE"
            return "CONTINUE"

        macro_dir = None
        if task.macro_backup_task:
            m_user_id = str(task.macro_backup_task.created_by_id or 1)
            macro_dir = os.path.join(str(settings.BASE_DIR), "backup", m_user_id, str(task.macro_backup_task.id))

        task_rules = list(task.rules.all().values("name", "rule_type", "parameters"))
        task_params = dict(task.parameters or {})
        if task_rules:
            task_params["rules"] = task_rules
        elif "rules" not in task_params:
            task_params["rules"] = []

        results = TensorTradeRLEngine.run_rl_backtest(
            backup_dir=backup_dir,
            params={
                "index_name": task.index_name,
                "start_date": task.start_date.isoformat(),
                "end_date": task.end_date.isoformat(),
                "initial_capital": task.initial_capital,
                "use_macro_assist": task.use_macro_assist,
                "macro_timeframe": task.macro_timeframe or "1h",
                "macro_dir": macro_dir,
                "enable_ai_lot_sizing": bool(task.enable_ai_lot_sizing),
                "auto_risk_management": bool(task.auto_risk_management),
                "max_risk_per_trade_pct": float(task.max_risk_per_trade_pct or 2.0),
                "max_capital_utilization_pct": float(task.max_capital_utilization_pct or 60.0),
                "max_lots_cap": int(task.max_lots_cap or 10),
                **task_params
            },
            progress_callback=on_rl_progress,
            control_callback=check_control
        )

        task.refresh_from_db()
        task.results = results
        task.metrics = {k: v for k, v in results.items() if k != 'trades'}

        if task.status not in [BacktestTask.StatusChoices.CANCELLED, BacktestTask.StatusChoices.PAUSED]:
            task.status = BacktestTask.StatusChoices.COMPLETED
            task.progress = 100
            task.error_logs = None
            task.save(update_fields=['results', 'metrics', 'status', 'progress', 'error_logs'])

            net_pnl = float(results.get('net_pnl', 0.0))
            total_trades = int(results.get('total_trades', len(results.get('trades', []))))
            
            print(f"[TENSORTRADE-RL] === Task #{task.id} FINISHED SUCCESSFULLY | Generated {total_trades} trades | Net PnL: ₹{net_pnl:,.2f} | Win Rate: {results.get('win_rate', 0)}% ===\n", flush=True)
            broadcast_backtest_progress(task.id, 100, BacktestTask.StatusChoices.COMPLETED, net_pnl=net_pnl, total_trades=total_trades, step_info="Backtest completed!")
        else:
            task.save(update_fields=['results', 'metrics'])
            print(f"[TENSORTRADE-RL] Task #{task.id} halted in {task.status} state. Preserved {len(results.get('trades', []))} partial trades.", flush=True)
        return task
    except Exception as e:
        print(f"[TENSORTRADE-RL] !!! Task #{task_id} ERROR: {e}\n", flush=True)
        logger.error(f"Error executing Python RL backtest task #{task_id}: {e}", exc_info=True)
        task = BacktestTask.objects.filter(id=task_id).first()
        if task and task.status not in [BacktestTask.StatusChoices.CANCELLED, BacktestTask.StatusChoices.PAUSED]:
            task.status = BacktestTask.StatusChoices.ERROR
            task.error_logs = str(e)
            task.save(update_fields=['status', 'error_logs'])
            broadcast_backtest_progress(task_id, 0, BacktestTask.StatusChoices.ERROR, step_info=f"Error: {str(e)}")
        return None
    finally:
        BacktestControlRegistry.cleanup(task_id)
