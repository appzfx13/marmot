from django.core.management.base import BaseCommand
from apps.backtest.models import BacktestRule
from apps.backtest.services import GO_STRATEGY_PRESETS
from apps.backtest.views import ensure_default_strategies


class Command(BaseCommand):
    """Seed clean, system-level BacktestRule presets and TradingStrategy catalog."""
    help = "Seeds database with BacktestRule records and Strategy Hub catalog."

    def handle(self, *args, **options):
        # 1. Seed TradingStrategy catalog for Strategy Library & Execution Hub
        ensure_default_strategies()
        self.stdout.write(self.style.SUCCESS("✓ Seeded TradingStrategy catalog for Strategy Library & Execution Hub."))

        count = 0
        for item in GO_STRATEGY_PRESETS:
            rule_type = item['rule_type']
            name = item['name']
            rule, created = BacktestRule.objects.update_or_create(
                rule_type=rule_type,
                defaults={
                    'name': name,
                    'market_type': item['market_type'],
                    'description': item['description'],
                    'parameters': item['parameters'],
                    'is_system_preset': item['is_system_preset'],
                    'is_active': item['is_active'],
                }
            )
            verb = "Created" if created else "Updated"
            self.stdout.write(self.style.SUCCESS(f"✓ {verb} preset rule: {name} (rule_type={rule_type})"))
            count += 1

        self.stdout.write(self.style.SUCCESS(f"\nSuccessfully seeded {count} Go strategy activation rules."))
