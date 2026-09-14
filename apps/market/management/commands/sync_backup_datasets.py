import os
import datetime
from django.core.management.base import BaseCommand
from django.conf import settings
from apps.market.models import MarketBackupTask
from apps.common.choices import TaskStatusChoices, MarketTypeChoices, IndexChoices, MacroTimeframeChoices
from apps.users.models import User

try:
    import pyarrow.parquet as pq
except ImportError:
    pq = None


class Command(BaseCommand):
    help = 'Scans the backup directory (/app/backup or ./backup) and registers or updates MarketBackupTask entries.'

    def handle(self, *args, **options):
        if pq is None:
            self.stderr.write(self.style.ERROR('pyarrow is required to inspect parquet datasets.'))
            return

        base_candidates = [
            os.path.join(settings.BASE_DIR, 'backup'),
            '/app/backup',
        ]
        backup_dir = next((p for p in base_candidates if os.path.isdir(p)), None)
        if not backup_dir:
            self.stderr.write(self.style.WARNING('No backup directory found.'))
            return

        admin_user = User.objects.filter(is_superuser=True).order_by('id').first() or User.objects.first()
        self.stdout.write(f"Using default user: {admin_user} (ID: {admin_user.id if admin_user else None})")

        synced_count = 0
        for user_dir_name in os.listdir(backup_dir):
            user_path = os.path.join(backup_dir, user_dir_name)
            if not os.path.isdir(user_path):
                continue

            for task_dir_name in os.listdir(user_path):
                task_path = os.path.join(user_path, task_dir_name)
                if not os.path.isdir(task_path):
                    continue

                dataset_file = os.path.join(task_path, 'dataset.parquet')
                if not os.path.isfile(dataset_file):
                    continue

                try:
                    task_id = int(task_dir_name)
                except ValueError:
                    continue

                file_size_mb = round(os.path.getsize(dataset_file) / (1024 * 1024), 2)
                try:
                    table = pq.read_table(dataset_file)
                    df = table.to_pandas()
                except Exception as e:
                    self.stderr.write(f"Error reading {dataset_file}: {e}")
                    continue

                is_macro = False
                macro_tf = None
                if 'macro_sentiment_score' in df.columns:
                    is_macro = True
                    macro_tf = MacroTimeframeChoices.H1

                d_start = datetime.date.today()
                d_end = datetime.date.today()
                if 'datetime' in df.columns and len(df) > 0:
                    try:
                        d_start = datetime.date.fromisoformat(str(df['datetime'].min())[:10])
                        d_end = datetime.date.fromisoformat(str(df['datetime'].max())[:10])
                    except Exception:
                        pass

                strike_count = 5
                if 'strike' in df.columns and not is_macro:
                    strike_count = len(df['strike'].unique())

                container_parquet_path = f"/app/backup/{user_dir_name}/{task_dir_name}/dataset.parquet"

                task_obj, created = MarketBackupTask.objects.update_or_create(
                    id=task_id,
                    defaults={
                        'created_by': admin_user,
                        'index_name': IndexChoices.NIFTY,
                        'market_type': MarketTypeChoices.INDEX_FO,
                        'strike_count': strike_count,
                        'start_date': d_start,
                        'end_date': d_end,
                        'status': TaskStatusChoices.COMPLETED,
                        'progress': 100,
                        'parquet_file_path': container_parquet_path,
                        'file_size_mb': file_size_mb,
                        'is_macro_assist': is_macro,
                        'macro_timeframe': macro_tf,
                    }
                )
                synced_count += 1
                status_str = "Created" if created else "Updated"
                self.stdout.write(self.style.SUCCESS(f"{status_str} Task #{task_obj.id}: {task_obj.display_symbol} ({d_start} -> {d_end}) [{file_size_mb} MB, Macro={is_macro}]"))

        self.stdout.write(self.style.SUCCESS(f"Successfully synced {synced_count} backup datasets."))
