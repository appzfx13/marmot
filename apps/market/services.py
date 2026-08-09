import json
import redis
from django.conf import settings
from .models import MarketBackupTask

# Initialize Redis Connection (Pulls from your Django settings, falls back to local docker defaults)
REDIS_URL = settings.REDIS_URL
redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)

REDIS_CHANNEL = 'market_backup_commands'

INDEX_INSTRUMENT_MAP = {
    'NIFTY': {"security_id": "13", "exchange_segment": "IDX_I", "instrument": "INDEX"},
    'BANKNIFTY': {"security_id": "25", "exchange_segment": "IDX_I", "instrument": "INDEX"},
    'FINNIFTY': {"security_id": "27", "exchange_segment": "IDX_I", "instrument": "INDEX"},
    'MIDCPNIFTY': {"security_id": "26", "exchange_segment": "IDX_I", "instrument": "INDEX"}
}

def create_and_start_backup_task(start_date, end_date, index_name, strike_count, user):
    """
    Creates the backup record in Postgres and signals the Go Engine via Redis to start.
    """
    # 1. Create the Shared DB State
    task = MarketBackupTask.objects.create(
        start_date=start_date,
        end_date=end_date,
        index_name=index_name,
        strike_count=strike_count,
        status=MarketBackupTask.StatusChoices.PENDING,
        created_by=user  # Assuming your BaseModel handles 'created_by'
    )
    
    # 2. Build the Payload for the Go Engine
    index_params = INDEX_INSTRUMENT_MAP.get(task.index_name, {})
    payload = {
        "task_id": str(task.id),
        "command": "START",
        "params": {
            "start_date": task.start_date.isoformat(),
            "end_date": task.end_date.isoformat(),
            "index_name": task.index_name,
            "strike_count": task.strike_count,
            "security_id": index_params.get("security_id", ""),
            "exchange_segment": index_params.get("exchange_segment", ""),
            "instrument": index_params.get("instrument", "")
        }
    }
    
    # 3. Publish to Redis IPC
    redis_client.publish(REDIS_CHANNEL, json.dumps(payload))
    
    return task

def send_control_command(task_id, command):
    """
    Sends a PAUSE, RESUME, or CANCEL command to the Go Engine for a specific task.
    """
    # Ensure the task exists and update the local DB status first
    task = MarketBackupTask.objects.get(id=task_id)
    
    valid_commands = ['PAUSE', 'RESUME', 'CANCEL']
    if command.upper() not in valid_commands:
        raise ValueError(f"Invalid command. Must be one of {valid_commands}")

    # Optionally update DB status immediately so UI reflects it before Go confirms
    if command.upper() == 'PAUSE':
        task.status = MarketBackupTask.StatusChoices.PAUSED
    elif command.upper() == 'CANCEL':
        task.status = MarketBackupTask.StatusChoices.CANCELLED
    elif command.upper() == 'RESUME':
        task.status = MarketBackupTask.StatusChoices.RUNNING
    task.save(update_fields=['status'])

    print("ccccccccccccccccccccccccccc", command.upper())

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
            "instrument": index_params.get("instrument", "")
        }

    redis_client.publish(REDIS_CHANNEL, json.dumps(payload))
    
    return task