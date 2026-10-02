import json
import logging
import os
import pyarrow.parquet as pq
import redis
from django.conf import settings
from apps.common.constants import REDIS_CHANNEL, INDEX_INSTRUMENT_MAP
from apps.common.choices import MarketTypeChoices
from .models import MarketBackupTask

logger = logging.getLogger(__name__)

REDIS_URL = settings.REDIS_URL
redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)


def dispatch_task_command(payload: dict) -> None:
    """Dispatches command to Go engine via both Redis Streams (persistent) and Pub/Sub (instant trigger)."""
    payload_str = json.dumps(payload)
    try:
        redis_client.xadd(REDIS_CHANNEL, {'data': payload_str}, maxlen=1000)
    except Exception as stream_err:
        logger.debug("Redis stream XADD warning: %s", stream_err)
    redis_client.publish(REDIS_CHANNEL, payload_str)


def create_and_start_backup_task(start_date, end_date, index_name=None, strike_count=None, user=None, market_type='INDEX_FO', forex_instrument=None, databento_schema=None, use_30_days_5s=False, use_30_days_1s=False):
    """Creates the backup record in Postgres with pre-stored path and dispatches to Go engine."""
    task = MarketBackupTask.objects.create(
        market_type=market_type or MarketTypeChoices.INDEX_FO,
        start_date=start_date,
        end_date=end_date,
        index_name=index_name,
        strike_count=strike_count,
        use_30_days_5s=use_30_days_5s,
        use_30_days_1s=use_30_days_1s,
        forex_instrument=forex_instrument,
        databento_schema=databento_schema or MarketBackupTask.DatabentoSchemaChoices.OHLCV_1M,
        status=MarketBackupTask.StatusChoices.CREATED,
        created_by=user
    )
    user_id = str(user.id if user else 1)
    task.parquet_file_path = f"/app/backup/{user_id}/{task.id}"
    task.save(update_fields=['parquet_file_path'])

    # Send the START command to the Go Engine
    send_control_command(str(task.id), 'START')

    return task


def run_macro_sync_worker(task_id):
    """Executes single-hit Gemini macro dataset generation and saves Apache Parquet dataset."""
    import pandas as pd
    from apps.common.services.gemini_service import GeminiAIService

    try:
        task = MarketBackupTask.objects.get(id=task_id)
        task.status = MarketBackupTask.StatusChoices.RUNNING
        task.progress = 20
        task.save(update_fields=['status', 'progress'])

        symbol = task.forex_instrument if task.market_type == MarketTypeChoices.FOREX_FUTURES else task.index_name
        symbol = symbol or "NIFTY"

        # Broadcast progress via Redis
        redis_client.publish(REDIS_CHANNEL, json.dumps({
            "type": "progress",
            "task_id": str(task.id),
            "progress": 35,
            "status": "running"
        }))

        records = GeminiAIService.fetch_macro_month_dataset(
            symbol=symbol,
            start_date=task.start_date.isoformat(),
            end_date=task.end_date.isoformat(),
            timeframe=task.macro_timeframe or "1h",
            market_type=task.market_type
        )

        df = pd.DataFrame(records)
        user_id = str(task.created_by.id if task.created_by else 1)
        
        # Save to macro task directory, and co-locate in linked market backup folder if specified
        out_dirs = [
            f"/app/backup/{user_id}/{task.id}",
            os.path.join(settings.BASE_DIR, 'backup', user_id, str(task.id))
        ]
        if task.linked_backup_task:
            linked_id = str(task.linked_backup_task.id)
            out_dirs.extend([
                f"/app/backup/{user_id}/{linked_id}",
                os.path.join(settings.BASE_DIR, 'backup', user_id, linked_id)
            ])
        
        saved_path = None
        for out_dir in out_dirs:
            try:
                os.makedirs(out_dir, exist_ok=True)
                macro_named_file = os.path.join(out_dir, f"macro_{task.macro_timeframe or '1h'}_{symbol}.parquet")
                df.to_parquet(macro_named_file, index=False)
                # Only write dataset.parquet into task's own directory (avoid overwriting market dataset.parquet)
                if str(task.id) in out_dir:
                    parquet_file = os.path.join(out_dir, "dataset.parquet")
                    df.to_parquet(parquet_file, index=False)
                if not saved_path:
                    saved_path = macro_named_file
            except Exception as e:
                logger.warning(f"Could not write to {out_dir}: {e}")

        file_size_mb = 0.0
        if saved_path and os.path.exists(saved_path):
            file_size_mb = round(os.path.getsize(saved_path) / (1024 * 1024), 3)

        task.status = MarketBackupTask.StatusChoices.COMPLETED
        task.progress = 100
        task.file_size_mb = max(0.01, file_size_mb)
        task.error_logs = None
        if saved_path:
            task.parquet_file_path = saved_path
        task.save(update_fields=['status', 'progress', 'file_size_mb', 'parquet_file_path', 'error_logs'])

        redis_client.publish(REDIS_CHANNEL, json.dumps({
            "type": "progress",
            "task_id": str(task.id),
            "progress": 100,
            "status": "completed"
        }))
        logger.info(f"AI Macro Parquet backup task #{task.id} completed successfully ({len(df)} rows).")

    except Exception as e:
        logger.error(f"Error in macro backup worker for task #{task_id}: {e}", exc_info=True)
        try:
            task = MarketBackupTask.objects.get(id=task_id)
            task.status = MarketBackupTask.StatusChoices.ERROR
            task.error_logs = str(e)
            task.save(update_fields=['status', 'error_logs'])
        except Exception:
            pass


def create_and_start_macro_backup_task(start_date, end_date, market_type='INDEX_FO', index_name=None, forex_instrument=None, macro_timeframe='1h', linked_backup_task=None, user=None):
    """Initializes AI Macro Assist backup task and triggers async sync worker with co-location."""
    import threading

    task = MarketBackupTask.objects.create(
        market_type=market_type or MarketTypeChoices.INDEX_FO,
        start_date=start_date,
        end_date=end_date,
        index_name=index_name,
        forex_instrument=forex_instrument,
        is_macro_assist=True,
        macro_timeframe=macro_timeframe or '1h',
        linked_backup_task=linked_backup_task,
        status=MarketBackupTask.StatusChoices.RUNNING,
        created_by=user
    )
    user_id = str(user.id if user else 1)
    if linked_backup_task:
        task.parquet_file_path = f"/app/backup/{user_id}/{linked_backup_task.id}/macro_{task.macro_timeframe or '1h'}_{task.asset_code}.parquet"
    else:
        task.parquet_file_path = f"/app/backup/{user_id}/{task.id}"
    task.save(update_fields=['parquet_file_path'])

    worker_thread = threading.Thread(target=run_macro_sync_worker, args=(task.id,), daemon=True)
    worker_thread.start()

    return task

def send_control_command(task_id, command):
    """
    Sends a PAUSE, RESUME, or CANCEL command to the Go Engine for a specific task.
    Injects active FYERS API v3 credentials from SiteSettings into the Redis control payload.
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
        from apps.common.models import SiteSettings
        site_settings = SiteSettings.load()
        fyers_app_id = (site_settings.fyers_app_id or '').strip()
        fyers_access_token = (site_settings.fyers_access_token or '').strip()

        payload["params"] = {
            "start_date": task.start_date.isoformat(),
            "end_date": task.end_date.isoformat(),
            "market_type": task.market_type,
            "index_name": task.index_name or '',
            "forex_instrument": task.forex_instrument or '',
            "provider_name": task.provider_name,
            "strike_count": 0 if (task.strike_count == 0 or task.index_name == 'INDIAVIX') else (task.strike_count if task.strike_count is not None else 15),
            "use_30_days_5s": task.use_30_days_5s,
            "use_30_days_1s": task.use_30_days_1s,
            "security_id": index_params.get("security_id", ""),
            "exchange_segment": index_params.get("exchange_segment", ""),
            "instrument": index_params.get("instrument", ""),
            "user_id": str(task.created_by.id if getattr(task, 'created_by', None) else 1),
            # FYERS API v3 Auth
            "fyers_app_id": fyers_app_id,
            "fyers_access_token": fyers_access_token,
            "databento_schema": task.databento_schema or 'ohlcv-1m',
            # Databento auth: API key from settings/env
            "databento_api_key": getattr(settings, 'DATABENTO_API_KEY', ''),
        }

    dispatch_task_command(payload)

    return task


def inspect_parquet_dataset(task, query=None, limit=50):
    """
    Reads and inspects the Apache Parquet file for a backup task using PyArrow.
    Returns metadata, column schema, total rows, and sample candle records.
    """
    user_id = str(task.created_by.id if getattr(task, 'created_by', None) else 1)
    task_id = str(task.id)

    if task.is_macro_assist:
        symbol = task.forex_instrument if task.market_type == MarketTypeChoices.FOREX_FUTURES else task.index_name
        symbol = symbol or "NIFTY"
        tf = task.macro_timeframe or "1h"
        macro_name = f"macro_{tf}_{symbol}.parquet"
        candidate_paths = [
            task.parquet_file_path,
            os.path.join('/app', 'backup', user_id, task_id, macro_name),
            os.path.join(settings.BASE_DIR, 'backup', user_id, task_id, macro_name),
        ]
        if task.linked_backup_task:
            linked_id = str(task.linked_backup_task.id)
            candidate_paths.extend([
                os.path.join('/app', 'backup', user_id, linked_id, macro_name),
                os.path.join(settings.BASE_DIR, 'backup', user_id, linked_id, macro_name),
            ])
        candidate_paths.extend([
            os.path.join('/app', 'backup', user_id, task_id, 'dataset.parquet'),
            os.path.join(settings.BASE_DIR, 'backup', user_id, task_id, 'dataset.parquet'),
        ])
    else:
        candidate_paths = [
            task.parquet_file_path,
            os.path.join(settings.BASE_DIR, 'backup', user_id, task_id, 'dataset.parquet'),
            os.path.join('/app', 'backup', user_id, task_id, 'dataset.parquet'),
        ]

    target_path = None
    is_in_progress = False
    for p in candidate_paths:
        if p and os.path.exists(p) and not os.path.isdir(p):
            if os.path.getsize(p) > 0:
                target_path = p
                break
            else:
                is_in_progress = True

    if not target_path:
        err_msg = 'Parquet dataset consolidation in progress...' if is_in_progress else 'Parquet dataset file not generated yet or missing on disk.'
        return {'exists': False, 'error': err_msg}

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


def get_daily_ticks_metadata():
    """Scans /app/backup/ticks/ directory and returns daily tick summaries and status."""
    import glob
    from datetime import datetime

    base_dir = os.path.join(getattr(settings, 'BACKUP_DIR', '/app/backup'), 'ticks')
    if not os.path.exists(base_dir):
        base_dir = '/app/backup/ticks'

    days = []
    total_spot_days = 0
    total_merged_days = 0
    total_bytes = 0

    if os.path.exists(base_dir):
        dir_entries = [d for d in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, d))]
        dir_entries.sort(reverse=True)

        for d_str in dir_entries:
            try:
                dt = datetime.strptime(d_str, '%Y-%m-%d')
                day_name = dt.strftime('%A')
                formatted_date = dt.strftime('%b %d, %Y')
            except ValueError:
                continue

            day_path = os.path.join(base_dir, d_str)
            spot_file = os.path.join(day_path, 'spot_1s.parquet')
            dataset_file = os.path.join(day_path, 'dataset_1s.parquet')

            has_spot = os.path.exists(spot_file)
            spot_size_mb = 0.0
            if has_spot:
                try:
                    s_size = os.path.getsize(spot_file)
                    spot_size_mb = round(s_size / (1024 * 1024), 2)
                    total_bytes += s_size
                    total_spot_days += 1
                except OSError:
                    pass

            has_merged = os.path.exists(dataset_file)
            merged_size_mb = 0.0
            if has_merged:
                try:
                    m_size = os.path.getsize(dataset_file)
                    merged_size_mb = round(m_size / (1024 * 1024), 2)
                    total_bytes += m_size
                    total_merged_days += 1
                except OSError:
                    pass

            raw_ticks = glob.glob(os.path.join(day_path, 'ticks_*.parquet'))
            spot_parts = glob.glob(os.path.join(day_path, 'spot_parts', 'spot_*.parquet'))
            if not spot_parts:
                spot_parts = glob.glob(os.path.join(day_path, 'spot_*.parquet'))

            redis_status = None
            try:
                redis_status = redis_client.get(f"marmot:merge:{d_str}:status")
            except Exception:
                pass

            if redis_status == 'running':
                status_label = 'Merging...'
                status_badge = 'warning'
            elif has_merged:
                status_label = 'Merged'
                status_badge = 'success'
            elif has_spot:
                status_label = 'Spot Ready'
                status_badge = 'info'
            elif raw_ticks:
                status_label = 'Raw Ticks'
                status_badge = 'secondary'
            else:
                status_label = 'Empty'
                status_badge = 'dark'

            days.append({
                'date_str': d_str,
                'formatted_date': formatted_date,
                'day_name': day_name,
                'has_spot': has_spot,
                'spot_size_mb': spot_size_mb,
                'has_merged': has_merged,
                'merged_size_mb': merged_size_mb,
                'raw_ticks_count': len(raw_ticks),
                'spot_parts_count': len(spot_parts),
                'status_label': status_label,
                'status_badge': status_badge,
                'redis_status': redis_status,
                'target_indices': ['NIFTY', 'BANKNIFTY'],
            })

    total_storage_mb = round(total_bytes / (1024 * 1024), 2)
    return {
        'days': days,
        'total_days': len(days),
        'total_spot_days': total_spot_days,
        'total_merged_days': total_merged_days,
        'total_storage_mb': total_storage_mb,
    }


def dispatch_daily_strike_merge(date_str, indices=None, strike_count=15):
    """Dispatches asynchronous 1S option download and merge request to Go microservice via Redis IPC."""
    if not indices:
        indices = ['NIFTY', 'BANKNIFTY']

    payload = {
        'action': 'run_daily_postmarket_merge',
        'date': date_str,
        'indices': indices,
        'strike_count': strike_count,
    }

    try:
        redis_client.set(f"marmot:merge:{date_str}:status", "running", ex=86400)
    except Exception as e:
        logger.warning(f"Could not set merge status in Redis: {e}")

    dispatch_task_command(payload)
    logger.info(f"Dispatched daily strike merge for {date_str} to Go microservice: {payload}")
    return True


