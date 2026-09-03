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
        BacktestTask.objects.filter(id=task_id).update(progress=progress, status=status)
        pub_count = redis_client.publish(REDIS_CHANNEL, json.dumps(payload))
        print(f"📡 [BROADCAST-PROGRESS] Task #{task_id} -> {progress}% ({status}) | Step: {step_info} | PnL: ₹{net_pnl:,.2f} | Trades: {total_trades} | Redis Pub Subscribed Clients: {pub_count}", flush=True)
    except Exception as e:
        print(f"❌ [BROADCAST-PROGRESS ERROR] Task #{task_id}: {e}", flush=True)
        logger.error("Failed to broadcast backtest progress", exc=e, extra={"task_id": task_id})


def create_and_start_backtest_task(strategy_name, index_name, start_date, end_date, initial_capital, parameters, user, backup_task=None, use_macro_assist=False, macro_timeframe='1h', macro_backup_task=None):
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
        status=BacktestTask.StatusChoices.CREATED,
        created_by=user
    )
    return task


def send_backtest_control_command(task_id, command):
    """Sends START_BACKTEST, PAUSE, or CANCEL command to Go Engine or Python RL worker."""
    task = BacktestTask.objects.get(id=task_id)
    cmd = command.upper()

    if cmd in ['START', 'START_BACKTEST', 'RESUME', 'RERUN', 'RESTART']:
        task.status = BacktestTask.StatusChoices.RUNNING
        task.progress = 5
        task.error_logs = ""
        task.results = {}
        task.metrics = {}
        task.save(update_fields=['status', 'progress', 'error_logs', 'results', 'metrics'])
    elif cmd == 'PAUSE':
        task.status = BacktestTask.StatusChoices.PAUSED
        task.save(update_fields=['status'])
    elif cmd in ['CANCEL', 'STOP']:
        task.status = BacktestTask.StatusChoices.CANCELLED
        task.save(update_fields=['status'])

    is_rl_strategy = (task.strategy_name == 'tensortrade_rl')

    # If strategy is TensorTrade RL, execute Python RL Engine exclusively in background thread
    if is_rl_strategy and cmd in ['START', 'START_BACKTEST', 'RESUME', 'RERUN', 'RESTART']:
        broadcast_backtest_progress(task.id, 5, BacktestTask.StatusChoices.RUNNING, step_info="Starting RL backtest execution...")
        threading.Thread(target=execute_python_rl_backtest, args=(task.id,), daemon=True).start()
    else:
        # Otherwise publish command to Go TaskManager on Redis Pub/Sub (for Go-native strategies or pause/cancel)
        payload = {
            "task_id": str(task.id),
            "command": "START_BACKTEST" if cmd in ['START', 'START_BACKTEST', 'RESUME', 'RERUN', 'RESTART'] else cmd,
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
    try:
        task = BacktestTask.objects.get(id=task_id)
        user_id = str(task.created_by_id or 1)
        backup_id = str(task.backup_task.id) if task.backup_task else str(task.id)
        backup_dir = os.path.join(str(settings.BASE_DIR), "backup", user_id, backup_id)
        
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

        macro_dir = None
        if task.macro_backup_task:
            m_user_id = str(task.macro_backup_task.created_by_id or 1)
            macro_dir = os.path.join(str(settings.BASE_DIR), "backup", m_user_id, str(task.macro_backup_task.id))

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
                **(task.parameters or {})
            },
            progress_callback=on_rl_progress
        )

        task.results = results
        task.metrics = {k: v for k, v in results.items() if k != 'trades'}
        task.status = BacktestTask.StatusChoices.COMPLETED
        task.progress = 100
        task.save(update_fields=['results', 'metrics', 'status', 'progress'])

        net_pnl = float(results.get('net_pnl', 0.0))
        total_trades = int(results.get('total_trades', len(results.get('trades', []))))
        
        print(f"[TENSORTRADE-RL] === Task #{task.id} FINISHED SUCCESSFULLY | Generated {total_trades} trades | Net PnL: ₹{net_pnl:,.2f} | Win Rate: {results.get('win_rate', 0)}% ===\n", flush=True)
        broadcast_backtest_progress(task.id, 100, BacktestTask.StatusChoices.COMPLETED, net_pnl=net_pnl, total_trades=total_trades, step_info="Backtest completed!")
        return task
    except Exception as e:
        print(f"[TENSORTRADE-RL] !!! Task #{task_id} ERROR: {e}\n", flush=True)
        logger.error(f"Error executing Python RL backtest task #{task_id}: {e}", exc_info=True)
        task = BacktestTask.objects.filter(id=task_id).first()
        if task:
            task.status = BacktestTask.StatusChoices.ERROR
            task.error_logs = str(e)
            task.save(update_fields=['status', 'error_logs'])
        broadcast_backtest_progress(task_id, 0, BacktestTask.StatusChoices.ERROR, step_info=f"Error: {str(e)}")
        return None
