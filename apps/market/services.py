import json
import logging
import redis
from django.conf import settings
from apps.common.constants import REDIS_CHANNEL, INDEX_INSTRUMENT_MAP
from apps.trade_core.services.dhan_token_service import AdminDhanClient
from .models import MarketBackupTask

logger = logging.getLogger(__name__)

REDIS_URL = settings.REDIS_URL
redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)

def create_and_start_backup_task(start_date, end_date, index_name, strike_count, user, dhan_access_token=None):
    """Creates the backup record in Postgres with pre-stored path and caches token if provided."""
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

    # If direct access token was entered in form, cache it in Redis for the master Dhan client
    if dhan_access_token and dhan_access_token.strip():
        client_id = getattr(settings, 'DHAN_CLIENT_ID', '')
        if client_id:
            redis_client.setex(f"dhan_token:{client_id}", 82800, dhan_access_token.strip())
            logger.info("Direct Dhan access token cached in Redis for admin client_id=%s (len=%d)", client_id, len(dhan_access_token.strip()))

    return task

def send_control_command(task_id, command, dhan_access_token=None):
    """
    Sends a PAUSE, RESUME, or CANCEL command to the Go Engine for a specific task.
    For START/RESUME, generates a live Dhan access token and injects it into the payload.
    If a direct dhan_access_token is provided, it is cached and prioritized.
    The Go engine uses: access-token + client-id headers for all DhanHQ API calls.
    """
    task = MarketBackupTask.objects.get(id=task_id)

    valid_commands = ['PAUSE', 'RESUME', 'START', 'CANCEL']
    if command.upper() not in valid_commands:
        raise ValueError(f"Invalid command. Must be one of {valid_commands}")

    if command.upper() == 'PAUSE':
        task.status = MarketBackupTask.StatusChoices.PAUSED
    elif command.upper() == 'CANCEL':
        task.status = MarketBackupTask.StatusChoices.CANCELLED
    elif command.upper() in ['RESUME', 'START']:
        task.status = MarketBackupTask.StatusChoices.RUNNING
    task.save(update_fields=['status'])

    index_params = INDEX_INSTRUMENT_MAP.get(task.index_name, {})

    payload = {
        "task_id": str(task.id),
        "command": command.upper()
    }

    if command.upper() in ['START', 'RESUME']:
        client_id = getattr(settings, 'DHAN_CLIENT_ID', '')

        # Direct token override if provided
        if dhan_access_token and dhan_access_token.strip():
            access_token = dhan_access_token.strip()
            if client_id:
                redis_client.setex(f"dhan_token:{client_id}", 82800, access_token)
        else:
            try:
                access_token = AdminDhanClient.get_access_token()
            except ValueError as e:
                logger.error("Failed to obtain Dhan access token for backup task #%s: %s", task_id, e)
                access_token = ''

        payload["params"] = {
            "start_date": task.start_date.isoformat(),
            "end_date": task.end_date.isoformat(),
            "index_name": task.index_name,
            "strike_count": task.strike_count,
            "security_id": index_params.get("security_id", ""),
            "exchange_segment": index_params.get("exchange_segment", ""),
            "instrument": index_params.get("instrument", ""),
            "user_id": str(task.created_by.id if getattr(task, 'created_by', None) else 1),
            # Dhan auth: client_id + live access_token (direct or cached)
            "dhan_client_id": client_id,
            "dhan_access_token": access_token,
        }

    redis_client.publish(REDIS_CHANNEL, json.dumps(payload))

    return task

