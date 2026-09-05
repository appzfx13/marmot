from django.core.management.base import BaseCommand
from apps.backtest.models import BacktestRule
from apps.backtest.choices import BacktestRuleTypeChoices, RuleMarketTypeChoices


class Command(BaseCommand):
    """Seeds and resets the unified Professional Intraday Trend & Momentum Guardrail rule."""

    help = "Seeds clean, professional Backtest Strategy Rules for the RL trading engine."

    def add_arguments(self, parser):
        parser.add_argument(
            '--clean',
            action='store_true',
            default=True,
            help='Removes legacy outdated micro-rules before creating the unified rule.'
        )

    def handle(self, *args, **options):
        clean_legacy = options.get('clean', True)

        if clean_legacy:
            deleted = BacktestRule.all_objects.all().hard_delete()
            self.stdout.write(self.style.WARNING(f"Removed legacy rules from database: {deleted}"))

        rule, created = BacktestRule.objects.update_or_create(
            name="Professional Intraday Trend & Momentum Guardrails",
            defaults={
                "rule_type": BacktestRuleTypeChoices.MOMENTUM_GUARDRAIL,
                "market_type": RuleMarketTypeChoices.ALL,
                "description": (
                    "Eliminates blind 09:15 entries and 6-hour theta decay. Enforces 15-minute "
                    "Opening Range (09:15-09:30) discovery, EMA 9/21 trend confirmation, dynamic "
                    "1.5x ATR targets, and a 45-minute momentum time-stop."
                ),
                "prompt_directive": (
                    "Wait for 09:30 15-min Opening Range Breakout and EMA 9/21 trend confirmation. "
                    "Enforce 45-minute momentum time-stop and trailing stop loss to protect long options against theta decay."
                ),
                "parameters": {
                    "orb_minutes": 15,
                    "ema_fast": 9,
                    "ema_slow": 21,
                    "time_stop_minutes": 45,
                    "target_atr_mult": 1.5,
                    "trailing_sl": True,
                },
                "is_system_preset": True,
                "is_active": True,
            }
        )

        status_str = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"Successfully {status_str} unified system rule: {rule.name} (ID: {rule.id})"))
