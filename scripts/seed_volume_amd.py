"""
Seed Volume + AMD Strategy entries into LiveStrategy table.
Can be executed via: python manage.py shell < scripts/seed_volume_amd.py
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
from apps.trade_config.models import LiveStrategy, UserTradingAccount
from apps.common.choices import StrategyChoices, MarketTypeChoices, LiveStrategyStatusChoices, AccountTypeChoices


def seed_volume_amd():
    amd_params = {
        'ema_fast': 9,
        'ema_slow': 21,
        'entry_window_from': 9 * 60 + 25,
        'entry_window_to': 15 * 60,
        'sl_pts': 12.0,
        'rr_ratio': 2.5,
        'use_orb_filter': False,
        'min_displacement': 0.50,
        'trail_breakeven': True,
        'breakeven_at_r': 1.5,
        'cooldown_seconds': 300,
        'order_type': 'LIMIT',
    }

    # 2. Seed LiveStrategy entry for active users/admin
    users = User.objects.filter(is_active=True)
    for u in users:
        trading_acc = UserTradingAccount.objects.filter(user=u, is_active=True).first()
        strat, s_created = LiveStrategy.objects.update_or_create(
            user=u,
            strategy_name=StrategyChoices.VOLUME_AMD,
            index_name='NIFTY',
            defaults={
                'name': f"Volume AMD NIFTY ({u.username})",
                'trading_account': trading_acc,
                'market_type': MarketTypeChoices.INDEX_FO,
                'allocated_capital': 100000.00,
                'frozen_rules_snapshot': [{
                    'rule_type': 'volume_amd',
                    'name': 'Volume + AMD Pattern (1:2.5 Limit Midpoint)',
                }],
                'frozen_parameters': amd_params,
                'is_active': False,
                'execution_mode': AccountTypeChoices.MOCK if trading_acc and trading_acc.account_type == AccountTypeChoices.MOCK else AccountTypeChoices.LIVE,
                'status': LiveStrategyStatusChoices.STANDBY,
            }
        )
        print(f"[{'CREATED' if s_created else 'UPDATED'}] LiveStrategy: {strat.name} (id={strat.id}) for user @{u.username}")

    print("✓ Successfully completed seeding Volume + AMD strategy entries.")


if __name__ == '__main__':
    seed_volume_amd()
