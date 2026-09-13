import os
import pyarrow.parquet as pq
from datetime import datetime
from django.contrib.auth import get_user_model
from django.db import connection
from apps.market.models import MarketBackupTask

User = get_user_model()
admin_user = User.objects.filter(pk=1).first() or User.objects.first()

FOREX_SYMBOLS = {'MGC': 'MGC', 'M6E': 'M6E', 'M6J': 'M6J', 'MYM': 'MYM', 'MNQ': 'MNQ', 'MES': 'MES', 'MCL': 'MCL'}
INDEX_SYMBOLS = {'NIFTY': 'NIFTY', 'BANKNIFTY': 'BANKNIFTY', 'SENSEX': 'SENSEX', 'GIFTNIFTY': 'GIFTNIFTY', 'INDIAVIX': 'INDIAVIX'}

base_dir = 'backup/1'
restored_count = 0
max_id = 0

for folder_name in sorted(os.listdir(base_dir), key=lambda x: int(x) if x.isdigit() else 9999):
    if not folder_name.isdigit():
        continue
    
    task_id = int(folder_name)
    if task_id > max_id:
        max_id = task_id
        
    task_dir = os.path.join(base_dir, folder_name)
    ds_file = os.path.join(task_dir, 'dataset.parquet')
    if not os.path.exists(ds_file):
        print(f"Skipping task {task_id}: dataset.parquet not found")
        continue

    # Inspect schema & metadata
    schema = pq.read_schema(ds_file)
    names = schema.names
    is_macro = ('macro_sentiment_score' in names)

    tab = pq.read_table(ds_file, columns=['datetime', 'index_name'] if 'index_name' in names else ['datetime'])
    df = tab.to_pandas()
    start_str = str(df['datetime'].min())[:10]
    end_str = str(df['datetime'].max())[:10]

    symbol = None
    if 'index_name' in df.columns:
        symbol = df['index_name'].iloc[0]
    else:
        for f in os.listdir(task_dir):
            if f.startswith('macro_1h_') and f.endswith('.parquet'):
                symbol = f.replace('macro_1h_', '').replace('.parquet', '')
                break

    market_type = 'INDEX_FO'
    forex_inst = None
    idx_name = None
    if symbol in FOREX_SYMBOLS:
        market_type = 'FOREX_FUTURES'
        forex_inst = symbol
    else:
        idx_name = symbol if symbol in INDEX_SYMBOLS else 'NIFTY'

    sz_mb = round(os.path.getsize(ds_file) / (1024 * 1024), 2)
    parquet_path = f"/app/backup/1/{task_id}/dataset.parquet"

    obj, created = MarketBackupTask.objects.update_or_create(
        id=task_id,
        defaults={
            'created_by': admin_user,
            'start_date': datetime.strptime(start_str, '%Y-%m-%d').date(),
            'end_date': datetime.strptime(end_str, '%Y-%m-%d').date(),
            'market_type': market_type,
            'index_name': idx_name,
            'forex_instrument': forex_inst,
            'is_macro_assist': is_macro,
            'macro_timeframe': '1h' if is_macro else None,
            'status': 'completed',
            'progress': 100,
            'parquet_file_path': parquet_path,
            'file_size_mb': sz_mb,
            'is_deleted': False,
        }
    )
    restored_count += 1
    print(f"Restored Task #{task_id}: {idx_name or forex_inst} ({market_type}, macro={is_macro}, {start_str} to {end_str}, {sz_mb} MB)")

# Reset postgres sequence so future auto-generated IDs do not collide
with connection.cursor() as cursor:
    cursor.execute("SELECT setval(pg_get_serial_sequence('market_marketbackuptask', 'id'), %s);", [max(max_id, 100)])

print(f"\nSuccessfully restored {restored_count} tasks! Next sequence value set to {max(max_id, 100) + 1}.")
