import os
import sys
from django.apps import AppConfig


class MarmotConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.trade_core'

    def ready(self):
        # Only start scheduler in web processes, avoid running during management commands (migrations, tests)
        ignored_commands = {'makemigrations', 'migrate', 'collectstatic', 'check', 'shell', 'test'}
        current_command = sys.argv[1] if len(sys.argv) > 1 else ''
        if current_command in ignored_commands:
            return

        # Avoid double execution under Django development auto-reloader
        if os.environ.get('RUN_MAIN') == 'true' or 'gunicorn' in sys.argv[0] or 'runserver' in sys.argv:
            try:
                from .scheduler import start_scheduler
                start_scheduler()
            except Exception:
                pass
