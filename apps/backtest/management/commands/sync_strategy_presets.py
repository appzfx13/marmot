from django.core.management.base import BaseCommand
from apps.backtest.models import BacktestRule
from apps.backtest.services import GO_STRATEGY_PRESETS


class Command(BaseCommand):
    """Synchronize BacktestRule database table with Go strategy presets registry."""
    help = "Checks existence and synchronizes BacktestRule entries for Go strategy presets."

    def add_arguments(self, parser):
        parser.add_argument('--force-update', action='store_true', help='Force update parameters for existing presets')

    def handle(self, *args, **options):
        force_update = options.get('force_update', False)
        created_count = 0
        updated_count = 0
        existing_count = 0

        for item in GO_STRATEGY_PRESETS:
            rule_type = item['rule_type']
            name = item['name']
            rule = BacktestRule.objects.filter(rule_type=rule_type).first()

            if not rule:
                BacktestRule.objects.create(
                    rule_type=rule_type,
                    name=name,
                    market_type=item['market_type'],
                    description=item['description'],
                    parameters=item['parameters'],
                    is_system_preset=item['is_system_preset'],
                    is_active=item['is_active'],
                )
                self.stdout.write(self.style.SUCCESS(f"✓ Created preset: {name} ({rule_type})"))
                created_count += 1
            elif force_update:
                rule.name = name
                rule.market_type = item['market_type']
                rule.description = item['description']
                rule.parameters = item['parameters']
                rule.is_system_preset = item['is_system_preset']
                rule.is_active = item['is_active']
                rule.save()
                self.stdout.write(self.style.WARNING(f"↻ Updated preset: {name} ({rule_type})"))
                updated_count += 1
            else:
                self.stdout.write(f"• Preset already exists: {name} ({rule_type})")
                existing_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"\nSync complete: {created_count} created, {updated_count} updated, {existing_count} already existed."
        ))
