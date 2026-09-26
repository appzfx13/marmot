import logging
from django.core.management.base import BaseCommand
from apps.trade_core.services.risk_reset_service import unfreeze_and_unblock_active_traders

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Management command to reset freeze flags, trade blocks, and broker kill switches for all active users."""
    help = "Unfreeze, unblock, and deactivate broker kill switches for active users."

    def add_arguments(self, parser):
        parser.add_argument(
            '--skip-broker',
            action='store_true',
            dest='skip_broker',
            default=False,
            help='Skip sending kill switch deactivation requests to broker APIs.',
        )

    def handle(self, *args, **options):
        skip_broker = options.get('skip_broker', False)
        self.stdout.write(self.style.NOTICE(f"Starting active users unfreeze and risk reset (skip_broker={skip_broker})..."))

        summary = unfreeze_and_unblock_active_traders(deactivate_broker_killswitch=not skip_broker)

        users_count = summary.get('users_reset_count', 0)
        broker_count = summary.get('broker_accounts_deactivated', 0)
        errors = summary.get('errors', [])

        self.stdout.write(self.style.SUCCESS(
            f"Successfully completed: {users_count} users unblocked/unfrozen, {broker_count} broker kill switches deactivated."
        ))
        if errors:
            self.stdout.write(self.style.WARNING(f"Warnings/Errors encountered ({len(errors)}):"))
            for err in errors:
                self.stdout.write(self.style.WARNING(f"  - {err}"))
