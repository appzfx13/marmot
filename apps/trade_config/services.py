import logging
from datetime import date
from decimal import Decimal
from django.utils import timezone
from .models import DailyPortfolioSnapshot, UserTradingAccount

logger = logging.getLogger(__name__)


def record_daily_portfolio_snapshot(user, trading_account=None, telemetry=None, execution_date=None):
    """Upsert daily portfolio snapshot for the given user and trading account."""
    if not user:
        return None

    if not trading_account:
        trading_account = user.get_active_trading_account()

    if not trading_account:
        return None

    if not execution_date:
        execution_date = timezone.localdate()

    telemetry = telemetry or {}
    account_type = trading_account.account_type

    # Extract capital and balance
    summary = trading_account.account_summary or {}
    initial_cap = Decimal(str(summary.get('initial_capital') or summary.get('balance') or 100000.00))

    realized = Decimal(str(telemetry.get('realized_pnl', 0.00)))
    unrealized = Decimal(str(telemetry.get('unrealized_pnl', 0.00)))
    gross_pnl = realized + unrealized
    charges = Decimal(str(telemetry.get('charges', 0.00)))
    net_pnl = Decimal(str(telemetry.get('live_net_pnl', gross_pnl - charges)))

    margin_utilized = Decimal(str(telemetry.get('margin_utilized', 0.00)))
    closing_bal = initial_cap + net_pnl

    orders = telemetry.get('orders', [])
    total_trades = len(orders) if orders else int(telemetry.get('todays_orders_count', 0))

    snapshot, _ = DailyPortfolioSnapshot.objects.update_or_create(
        user=user,
        trading_account=trading_account,
        date=execution_date,
        defaults={
            'account_type': account_type,
            'opening_balance': initial_cap,
            'closing_balance': closing_bal,
            'gross_pnl': gross_pnl,
            'net_pnl': net_pnl,
            'realized_pnl': realized,
            'unrealized_pnl': unrealized,
            'total_charges': charges,
            'margin_utilized': margin_utilized,
            'total_trades': total_trades,
            'telemetry_snapshot': telemetry,
        }
    )
    return snapshot
