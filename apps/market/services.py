import json
import logging
import os
import pyarrow.parquet as pq
import redis
from django.conf import settings
from apps.common.constants import REDIS_CHANNEL, INDEX_INSTRUMENT_MAP
from apps.trade_core.services.dhan_token_service import AdminDhanClient
from .models import MarketBackupTask

logger = logging.getLogger(__name__)

REDIS_URL = settings.REDIS_URL
redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)

def create_and_start_backup_task(start_date, end_date, index_name=None, strike_count=None, user=None, dhan_access_token=None, market_type='INDEX_FO', forex_instrument=None, databento_schema=None):
    """Creates the backup record in Postgres with pre-stored path and caches token if provided."""
    task = MarketBackupTask.objects.create(
        market_type=market_type or MarketBackupTask.MarketTypeChoices.INDEX_FO,
        start_date=start_date,
        end_date=end_date,
        index_name=index_name,
        strike_count=strike_count,
        forex_instrument=forex_instrument,
        databento_schema=databento_schema or MarketBackupTask.DatabentoSchemaChoices.OHLCV_1M,
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
            "market_type": task.market_type,
            "index_name": task.index_name or '',
            "forex_instrument": task.forex_instrument or '',
            "provider_name": task.provider_name,
            "strike_count": task.strike_count or 5,
            "security_id": index_params.get("security_id", ""),
            "exchange_segment": index_params.get("exchange_segment", ""),
            "instrument": index_params.get("instrument", ""),
            "user_id": str(task.created_by.id if getattr(task, 'created_by', None) else 1),
            # Dhan auth: client_id + live access_token
            "dhan_client_id": client_id,
            "dhan_access_token": access_token,
            "databento_schema": task.databento_schema or 'ohlcv-1m',
            # Databento auth: API key from settings/env
            "databento_api_key": getattr(settings, 'DATABENTO_API_KEY', ''),
        }

    redis_client.publish(REDIS_CHANNEL, json.dumps(payload))

    return task


def inspect_parquet_dataset(task, query=None, limit=50):
    """
    Reads and inspects the Apache Parquet file for a backup task using PyArrow.
    Returns metadata, column schema, total rows, and sample candle records.
    """
    user_id = str(task.created_by.id if getattr(task, 'created_by', None) else 1)
    task_id = str(task.id)

    candidate_paths = [
        task.parquet_file_path,
        os.path.join(settings.BASE_DIR, 'backup', user_id, task_id, 'dataset.parquet'),
        os.path.join('/app', 'backup', user_id, task_id, 'dataset.parquet'),
    ]

    target_path = None
    for p in candidate_paths:
        if p and os.path.exists(p) and not os.path.isdir(p):
            target_path = p
            break

    if not target_path:
        return {'exists': False, 'error': 'Parquet dataset file not generated yet or missing on disk.'}

    try:
        pf = pq.ParquetFile(target_path)
        num_rows = pf.metadata.num_rows
        num_row_groups = pf.metadata.num_row_groups
        schema = [{'name': f.name, 'type': str(f.type)} for f in pf.schema_arrow]

        head_records = []
        tail_records = []
        records = []
        is_split_view = False

        q_lower = query.strip().lower() if query else None

        if q_lower:
            # Filter search: Scan row groups until up to 50 matching records are collected
            for rg_idx in range(num_row_groups):
                rg_table = pf.read_row_group(rg_idx)
                rg_pydict = rg_table.to_pydict()
                keys = list(rg_pydict.keys())
                rg_len = len(rg_pydict[keys[0]]) if keys else 0
                for i in range(rg_len):
                    row = {k: rg_pydict[k][i] for k in keys}
                    row_str = ' '.join(str(v).lower() for v in row.values())
                    if q_lower in row_str:
                        records.append(row)
                        if len(records) >= 50:
                            break
                if len(records) >= 50:
                    break
        else:
            # Ultra-fast zero-copy slice: 10 starting K-lines (Head) and 10 ending K-lines (Tail)
            slice_count = min(limit, 10) if limit else 10
            if num_row_groups > 0:
                first_rg_table = pf.read_row_group(0)
                head_len = min(slice_count, first_rg_table.num_rows)
                head_table = first_rg_table.slice(0, head_len)
                head_dict = head_table.to_pydict()
                keys = list(head_dict.keys())
                for i in range(head_len):
                    head_records.append({k: head_dict[k][i] for k in keys})

                if num_rows > head_len:
                    last_rg_idx = num_row_groups - 1
                    last_rg_table = pf.read_row_group(last_rg_idx)
                    tail_len = min(slice_count, last_rg_table.num_rows)
                    tail_offset = max(0, last_rg_table.num_rows - tail_len)
                    tail_table = last_rg_table.slice(tail_offset, tail_len)
                    tail_dict = tail_table.to_pydict()
                    for i in range(tail_len):
                        tail_records.append({k: tail_dict[k][i] for k in keys})

                if tail_records:
                    is_split_view = True
                    records = head_records + tail_records
                else:
                    records = head_records

        file_size_bytes = os.path.getsize(target_path)
        file_size_mb = round(file_size_bytes / (1024 * 1024), 2)

        return {
            'exists': True,
            'is_valid': True,
            'file_path': target_path,
            'file_size_mb': file_size_mb,
            'num_rows': num_rows,
            'num_row_groups': num_row_groups,
            'columns': pf.schema.names,
            'schema': schema,
            'head_records': head_records,
            'tail_records': tail_records,
            'records': records,
            'is_split_view': is_split_view,
            'sample_count': len(records),
        }
    except Exception as e:
        return {
            'exists': True,
            'is_valid': False,
            'error': f'Invalid Parquet binary format: {str(e)}'
        }

