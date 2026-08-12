import json
import redis
from django.conf import settings
from apps.common.constants import REDIS_CHANNEL, INDEX_INSTRUMENT_MAP
from .models import MarketBackupTask

# Initialize Redis Connection (Pulls from your Django settings, falls back to local docker defaults)
REDIS_URL = settings.REDIS_URL
redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)

def create_and_start_backup_task(start_date, end_date, index_name, strike_count, user):
    """Creates the backup record in Postgres with pre-stored path."""
    task = MarketBackupTask.objects.create(
        start_date=start_date,
        end_date=end_date,
        index_name=index_name,
        strike_count=strike_count,
        status=MarketBackupTask.StatusChoices.CREATED,
        created_by=user
    )
    user_id = str(user.id if user else 1)
    task.parquet_file_path = f"/app/backup/{user_id}/{task.id}"
    task.save(update_fields=['parquet_file_path'])
    return task

def send_control_command(task_id, command):
    """
    Sends a PAUSE, RESUME, or CANCEL command to the Go Engine for a specific task.
    """
    # Ensure the task exists and update the local DB status first
    task = MarketBackupTask.objects.get(id=task_id)
    
    valid_commands = ['PAUSE', 'RESUME', 'START', 'CANCEL']
    if command.upper() not in valid_commands:
        raise ValueError(f"Invalid command. Must be one of {valid_commands}")

    # Optionally update DB status immediately so UI reflects it before Go confirms
    if command.upper() == 'PAUSE':
        task.status = MarketBackupTask.StatusChoices.PAUSED
    elif command.upper() == 'CANCEL':
        task.status = MarketBackupTask.StatusChoices.CANCELLED
    elif command.upper() in ['RESUME', 'START']:
        task.status = MarketBackupTask.StatusChoices.RUNNING
    task.save(update_fields=['status'])

    index_params = INDEX_INSTRUMENT_MAP.get(task.index_name, {})
    
    # Broadcast to Go Engine
    payload = {
        "task_id": str(task.id),
        "command": command.upper()
    }
    
    if command.upper() in ['START', 'RESUME']:
        payload["params"] = {
            "start_date": task.start_date.isoformat(),
            "end_date": task.end_date.isoformat(),
            "index_name": task.index_name,
            "strike_count": task.strike_count,
            "security_id": index_params.get("security_id", ""),
            "exchange_segment": index_params.get("exchange_segment", ""),
            "instrument": index_params.get("instrument", ""),
            "user_id": str(task.created_by.id if getattr(task, 'created_by', None) else 1)
        }

    redis_client.publish(REDIS_CHANNEL, json.dumps(payload))
    
    return task