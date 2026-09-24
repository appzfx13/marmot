import os
from django.apps import AppConfig


class CommonConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.common'

    def ready(self):
        """Connect signals and log Cloudflare Tunnel URL when development server starts."""
        try:
            import apps.common.signals  # noqa: F401
        except ImportError:
            pass

        if os.environ.get('RUN_MAIN') == 'true':
            from apps.common.utils import fetch_tunnel_url
            tunnel_url = fetch_tunnel_url(timeout=2, retries=8, delay=1)
            if tunnel_url:
                print(f"\n{'=' * 65}")
                print(f"🚀 CLOUDFLARE TUNNEL URL: {tunnel_url}")
                print(f"   Terminal & Dashboard: {tunnel_url}/admins/dashboard/")
                print(f"{'=' * 65}\n")


