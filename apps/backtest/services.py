import json
import redis
from django.conf import settings
from apps.common.constants import REDIS_CHANNEL
from .models import BacktestTask

REDIS_URL = settings.REDIS_URL
redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)

def create_and_start_backtest_task(strategy_name, index_name, start_date, end_date, initial_capital, parameters, user, backup_task=None):
    """Creates a BacktestTask DB entry in CREATED status without auto-starting."""
    task = BacktestTask.objects.create(
        strategy_name=strategy_name,
        index_name=index_name,
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
        parameters=parameters or {},
        backup_task=backup_task,
        status=BacktestTask.StatusChoices.CREATED,
        created_by=user
    )
    return task

def send_backtest_control_command(task_id, command):
    """Sends START_BACKTEST, PAUSE, or CANCEL command to Go Engine via Redis."""
    task = BacktestTask.objects.get(id=task_id)
    cmd = command.upper()

    if cmd in ['START', 'START_BACKTEST', 'RESUME']:
        task.status = BacktestTask.StatusChoices.RUNNING
    elif cmd == 'PAUSE':
        task.status = BacktestTask.StatusChoices.PAUSED
    elif cmd in ['CANCEL', 'STOP']:
        task.status = BacktestTask.StatusChoices.CANCELLED
    task.save(update_fields=['status'])

    payload = {
        "task_id": str(task.id),
        "command": "START_BACKTEST" if cmd in ['START', 'START_BACKTEST', 'RESUME'] else cmd,
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

    redis_client.publish(REDIS_CHANNEL, json.dumps(payload))
    return task
