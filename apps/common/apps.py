import os
from django.apps import AppConfig


class CommonConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.common'

    def ready(self):
        """Connect signals and log NGROK URL when development server starts."""
        try:
            import apps.common.signals  # noqa: F401
        except ImportError:
            pass

        if os.environ.get('RUN_MAIN') == 'true':
            from apps.common.utils import fetch_ngrok_url
            ngrok_url = fetch_ngrok_url(timeout=1, retries=3, delay=1)
            if ngrok_url:
                print(f"NGROK Tunnel URL: {ngrok_url}")


