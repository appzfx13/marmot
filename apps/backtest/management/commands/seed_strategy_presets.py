from django.core.management.base import BaseCommand
from apps.backtest.models import BacktestRule
from apps.backtest.choices import BacktestRuleTypeChoices, RuleMarketTypeChoices


class Command(BaseCommand):
    """Seed clean, system-level BacktestRule presets that activate Go quantitative strategies."""
    help = "Seeds database with BacktestRule records mapped to hardcoded Go strategy presets."

    def handle(self, *args, **options):
        presets = [
            {
                'rule_type': BacktestRuleTypeChoices.GAMMA_BLAST,
                'name': 'Expiry Gamma Blast 1:3.5 (Hero or Zero)',
                'market_type': RuleMarketTypeChoices.INDEX_FO,
                'description': 'Afternoon 14:15-15:15 IST gamma explosion micro-scalper for expiry days. Tight 8pt SL, 1:3.5 RR.',
                'parameters': {
                    'entry_window_from': 14 * 60 + 15,
                    'entry_window_to': 15 * 60 + 15,
                    'sl_pts': 8.0,
                    'rr_ratio': 3.5,
                    'require_expiry_day': True,
                    'min_displacement': 0.70,
                },
                'is_system_preset': True,
                'is_active': True,
            },
            {
                'rule_type': BacktestRuleTypeChoices.MOMENTUM_SCALP,
                'name': 'Momentum Scalp 1:2.5 (EMA 9/21 + ORB)',
                'market_type': RuleMarketTypeChoices.ALL,
                'description': 'EMA 9/21 momentum crossover with ORB midpoint filter. 1:2.5 RR, trailing breakeven at 1.2R.',
                'parameters': {
                    'entry_window_from': 9 * 60 + 20,
                    'entry_window_to': 15 * 60,
                    'sl_pts': 12.0,
                    'rr_ratio': 2.5,
                    'use_orb_filter': True,
                    'min_displacement': 0.50,
                },
                'is_system_preset': True,
                'is_active': True,
            },
            {
                'rule_type': BacktestRuleTypeChoices.ALGO_MICRO_SCALP,
                'name': 'Institutional Micro-Scalp 1:3 (EMA 5/13)',
                'market_type': RuleMarketTypeChoices.ALL,
                'description': 'EMA 5/13 fast scalp with tight 8pt SL and 1:3 RR. Trailing BE at 1R.',
                'parameters': {
                    'entry_window_from': 9 * 60 + 20,
                    'entry_window_to': 14 * 60 + 30,
                    'sl_pts': 8.0,
                    'rr_ratio': 3.0,
                    'use_orb_filter': False,
                    'min_displacement': 0.55,
                },
                'is_system_preset': True,
                'is_active': True,
            },
            {
                'rule_type': BacktestRuleTypeChoices.ICT_SMC,
                'name': 'ICT Smart Money 1:2 (Limit Retest)',
                'market_type': RuleMarketTypeChoices.ALL,
                'description': 'ICT displacement 65%+ with limit retest entry. 1:2 RR, trail at 1.5R.',
                'parameters': {
                    'entry_window_from': 9 * 60 + 20,
                    'entry_window_to': 15 * 60,
                    'sl_pts': 15.0,
                    'rr_ratio': 2.0,
                    'order_type': 'LIMIT',
                    'min_displacement': 0.65,
                },
                'is_system_preset': True,
                'is_active': True,
            },
            {
                'rule_type': 'orb_breakout',
                'name': 'ORB Breakout 1:2 (Morning Session)',
                'market_type': RuleMarketTypeChoices.INDEX_FO,
                'description': 'ORB breakout only before noon. Wider SL with confirmed displacement above 60%.',
                'parameters': {
                    'entry_window_from': 9 * 60 + 30,
                    'entry_window_to': 12 * 60,
                    'sl_pts': 20.0,
                    'rr_ratio': 2.0,
                    'use_orb_filter': True,
                    'min_displacement': 0.60,
                },
                'is_system_preset': True,
                'is_active': True,
            },
            {
                'rule_type': BacktestRuleTypeChoices.INTRADAY,
                'name': 'Intraday Momentum 1:2.5 (Auto Square-off)',
                'market_type': RuleMarketTypeChoices.ALL,
                'description': 'Standard intraday momentum scalp. Square-off before 14:45.',
                'parameters': {
                    'entry_window_from': 9 * 60 + 20,
                    'entry_window_to': 14 * 60 + 45,
                    'sl_pts': 12.0,
                    'rr_ratio': 2.5,
                },
                'is_system_preset': True,
                'is_active': True,
            },
            {
                'rule_type': BacktestRuleTypeChoices.MORNING_TREND,
                'name': 'Morning Trend 1:2 (First Hour)',
                'market_type': RuleMarketTypeChoices.ALL,
                'description': 'First-hour momentum capture only. Tight SL 10pts, 1:2 RR.',
                'parameters': {
                    'entry_window_from': 9 * 60 + 20,
                    'entry_window_to': 11 * 60,
                    'sl_pts': 10.0,
                    'rr_ratio': 2.0,
                },
                'is_system_preset': True,
                'is_active': True,
            },
            {
                'rule_type': BacktestRuleTypeChoices.MOMENTUM_GUARDRAIL,
                'name': 'Professional Momentum Guardrail 1:2.5',
                'market_type': RuleMarketTypeChoices.ALL,
                'description': 'Guardrail version: wider displacement threshold, later window close, trail at 1.5R.',
                'parameters': {
                    'entry_window_from': 9 * 60 + 30,
                    'entry_window_to': 14 * 60 + 30,
                    'sl_pts': 15.0,
                    'rr_ratio': 2.5,
                    'min_displacement': 0.60,
                },
                'is_system_preset': True,
                'is_active': True,
            },
        ]

        count = 0
        for item in presets:
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
