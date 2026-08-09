import os
import django
import datetime
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'marmot.settings')
django.setup()

from apps.market.models import MarketBackupTask
from apps.market.services import send_control_command

task = MarketBackupTask.objects.last()
if task:
    print(f"Modifying and restarting task {task.id}")
    task.start_date = datetime.date(2024, 1, 1)
    task.end_date = datetime.date(2024, 1, 5)
    task.status = 'paused' # Need it in paused so resume works
    task.save()
    send_control_command(task.id, 'RESUME')
else:
    print("No task found")
