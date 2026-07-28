# bugtracker/celery.py
import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bugtracker.settings')

celery = Celery('bugtracker')  # <--- Make sure this variable name is `celery` or `app`
celery.config_from_object('django.conf:settings', namespace='CELERY')
celery.autodiscover_tasks()