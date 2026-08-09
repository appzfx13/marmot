import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'marmot.settings')
django.setup()

from apps.market.models import MarketBackupTask
from apps.market.services import send_control_command
from django.contrib.auth import get_user_model

# Get any existing task
task = MarketBackupTask.objects.last()
if task:
    print(f"Testing resume for task {task.id}")
    send_control_command(task.id, 'RESUME')
else:
    print("No task found to test.")
