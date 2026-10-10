from django.core.management.base import BaseCommand
from apps.backtest.views import ensure_default_strategies


class Command(BaseCommand):
    """Seed TradingStrategy catalog for Strategy Library & Execution Hub."""
    help = "Seeds database with TradingStrategy catalog."

    def handle(self, *args, **options):
        ensure_default_strategies()
        self.stdout.write(self.style.SUCCESS("✓ Seeded TradingStrategy catalog for Strategy Library & Execution Hub."))
