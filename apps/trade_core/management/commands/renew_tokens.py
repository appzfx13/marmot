import logging
from django.core.management.base import BaseCommand
from apps.trade_core.scheduler import renew_keep_alive_tokens_job

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Management command to manually or periodically trigger Dhan Keep-Alive token renewal."""
    help = "Renew active Dhan access tokens for accounts with keep_alive enabled."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Starting Dhan Keep-Alive Token Renewal..."))
        renew_keep_alive_tokens_job()
        self.stdout.write(self.style.SUCCESS("Dhan Token Renewal task completed successfully."))
