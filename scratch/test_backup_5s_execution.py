import os
import time
import django
from django.contrib.auth import get_user_model
from apps.market.models import MarketBackupTask
from apps.common.choices import IndexChoices, MarketTypeChoices, TaskStatusChoices as StatusChoices
import redis
import json
import pyarrow.parquet as pq

def test_backup():
    User = get_user_model()
    admin = User.objects.filter(is_superuser=True).first()
    if not admin:
        print("No admin user found")
        return

    # Create task with default 5S resolution for a 2-day historical window
    # 2024-07-25 to 2024-07-26 (2 trading days)
    task = MarketBackupTask.objects.create(
        created_by=admin,
        market_type=MarketTypeChoices.INDEX_FO,
        index_name=IndexChoices.NIFTY,
        start_date="2024-07-25",
        end_date="2024-07-26",
        strike_count=2,  # 2 strikes above/below ATM (5 strikes total, 10 option contracts + spot)
        use_30_days_5s=True, # Explicitly True
        status=StatusChoices.CREATED,
    )
    print(f"Created Task #{task.id}: index={task.index_name}, 5S={task.use_30_days_5s}, strikes={task.strike_count}")

    from apps.market.services import send_control_command
    send_control_command(task.id, 'START')
    print(f"Dispatched task #{task.id} to Go worker via send_control_command!")

    # Wait for completion (up to 30s)
    for _ in range(30):
        time.sleep(1)
        task.refresh_from_db()
        print(f"Task status: {task.status}, progress: {task.progress}%")
        if task.status in (StatusChoices.COMPLETED, StatusChoices.ERROR):
            break

    if task.status == StatusChoices.COMPLETED:
        print("Task Completed Successfully!")
        p_path = task.parquet_file_path or f"/app/backup/{admin.id}/{task.id}/dataset.parquet"
        print("Parquet path:", p_path)
        if os.path.exists(p_path):
            tbl = pq.read_table(p_path)
            df = tbl.to_pandas()
            print("Total rows:", len(df))
            print("Columns:", list(df.columns))
            # Check time delta between consecutive timestamps for same symbol
            sample_sym = df[df['option_type'] != 'INDEX']['trading_symbol'].iloc[0]
            sym_df = df[df['trading_symbol'] == sample_sym].sort_values('timestamp')
            diffs = sym_df['timestamp'].diff().dropna().unique()
            print(f"Timestamp steps for {sample_sym}:", diffs[:5])
            print("Sample 5S rows with OI:")
            print(sym_df[['datetime', 'trading_symbol', 'strike', 'option_type', 'close', 'oi']].head(6))
            unique_oi = sym_df['oi'].unique()
            print("Unique OI count:", len(unique_oi), "Max OI:", max(unique_oi))
        else:
            print("File does not exist:", p_path)
    else:
        print("Task error logs:", task.error_logs)

if __name__ == '__main__':
    test_backup()
