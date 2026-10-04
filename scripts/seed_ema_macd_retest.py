"""
Seed EMA 9/21 Retest + MACD Momentum Strategy entries into Django BacktestRule and LiveStrategy tables.
Can be executed via: python manage.py shell < scripts/seed_ema_macd_retest.py
or directly inside the django_app container.
"""
import os
import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'marmot.settings')
django.setup()

from apps.users.models import User
from apps.backtest.models import BacktestRule
from apps.trade_config.models import LiveStrategy, UserTradingAccount
from apps.common.choices import StrategyChoices, MarketTypeChoices, LiveStrategyStatusChoices, AccountTypeChoices


def seed_ema_macd_retest():
    # 1. Ensure BacktestRule exists
    rule, r_created = BacktestRule.objects.update_or_create(
        rule_type='ema_macd_retest',
        defaults={
            'name': 'EMA 9/21 Retest + MACD Momentum (1:2.0 RR)',
            'market_type': 'ALL',
            'description': 'EMA 9/21 trend alignment with price pullback retest to EMA 9 and MACD zero-line momentum gatekeeper. Features Strike Sweep ATM±3 mid-price entry and 1:2.0 RR with trailing breakeven.',
            'parameters': {
                'ema_fast': 9,
                'ema_slow': 21,
                'macd_fast': 12,
                'macd_slow': 26,
                'macd_signal': 9,
                'entry_window_from': 9 * 60 + 20,
                'entry_window_to': 14 * 60 + 45,
                'sl_pts': 15.0,
                'rr_ratio': 2.0,
                'use_orb_filter': False,
                'min_displacement': 0.40,
                'trail_breakeven': True,
                'breakeven_at_r': 1.2,
                'cooldown_seconds': 300,
                'order_type': 'LIMIT',
            },
            'is_system_preset': True,
            'is_active': True,
        }
    )
    print(f"[{'CREATED' if r_created else 'UPDATED'}] BacktestRule: {rule.name} (id={rule.id})")

    # 2. Seed LiveStrategy entry for active users/admin
    users = User.objects.filter(is_active=True)
    for u in users:
        trading_acc = UserTradingAccount.objects.filter(user=u, is_active=True).first()
        strat, s_created = LiveStrategy.objects.update_or_create(
            user=u,
            strategy_name=StrategyChoices.EMA_MACD_RETEST,
            index_name='NIFTY',
            defaults={
                'name': f"EMA MACD Retest NIFTY ({u.username})",
                'trading_account': trading_acc,
                'market_type': MarketTypeChoices.INDEX_FO,
                'allocated_capital': 100000.00,
                'frozen_rules_snapshot': [{
                    'rule_type': 'ema_macd_retest',
                    'name': 'EMA 9/21 Retest + MACD Momentum (1:2.0 RR)',
                }],
                'frozen_parameters': rule.parameters,
                'is_active': False,
                'execution_mode': AccountTypeChoices.MOCK if trading_acc and trading_acc.account_type == AccountTypeChoices.MOCK else AccountTypeChoices.LIVE,
                'status': LiveStrategyStatusChoices.STANDBY,
            }
        )
        print(f"[{'CREATED' if s_created else 'UPDATED'}] LiveStrategy: {strat.name} (id={strat.id}) for user @{u.username}")

    print("✓ Successfully completed seeding EMA 9/21 Retest + MACD Momentum strategy entries.")


if __name__ == '__main__':
    seed_ema_macd_retest()
