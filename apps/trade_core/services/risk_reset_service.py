import logging
from typing import Dict, Any, List
from django.db import transaction
from django.db.models import Q
from apps.users.models import User
from apps.trade_config.models import UserTradingAccount
from apps.trade_core.brokers.factory import BrokerFactory

logger = logging.getLogger(__name__)


def unfreeze_and_unblock_active_traders(deactivate_broker_killswitch: bool = True) -> Dict[str, Any]:
    """Resets freeze flags, trade blocks, and broker kill switches for all active users."""
    logger.info("🌅 [Risk Reset] Commencing morning unfreeze & trade block reset for active users...")

    blocked_users_qs = User.objects.filter(
        is_active=True,
        is_deleted=False
    ).filter(
        Q(primary_freeze=True) |
        Q(final_freeze=True) |
        Q(is_blocked=True) |
        Q(trade_eligibility=False)
    )

    candidate_count = blocked_users_qs.count()
    reset_user_ids: List[int] = list(blocked_users_qs.values_list('id', flat=True))

    with transaction.atomic():
        updated_count = blocked_users_qs.update(
            primary_freeze=False,
            final_freeze=False,
            is_blocked=False,
            trade_eligibility=True,
            primary_freeze_time=None,
            primary_freeze_pl=None,
            final_freeze_time=None,
            final_freeze_pl=None
        )

    logger.info("✅ [Risk Reset] Database flags cleared. Total active users reset: %d (candidates: %d)", updated_count, candidate_count)

    broker_deactivated_count = 0
    broker_errors: List[str] = []

    if deactivate_broker_killswitch:
        trading_accounts_qs = UserTradingAccount.objects.filter(
            is_active=True,
            is_deleted=False,
            account_type='LIVE'
        ).select_related('broker', 'user')

        if reset_user_ids:
            target_accounts = trading_accounts_qs.filter(user_id__in=reset_user_ids)
        else:
            target_accounts = trading_accounts_qs

        for account in target_accounts:
            broker_code = getattr(account.broker, 'code', '').lower()
            if broker_code not in ['dhan', 'dhanhq']:
                continue

            try:
                adapter = BrokerFactory.get_adapter(account)
                if hasattr(adapter, 'deactivate_kill_switch'):
                    res = adapter.deactivate_kill_switch()
                    if res.get('success'):
                        broker_deactivated_count += 1
                        logger.info("🔓 [Risk Reset] Dhan Kill Switch deactivated for account #%s (@%s)", account.id, account.user.username)
                    else:
                        err_msg = f"Account #{account.id} (@{account.user.username}): {res.get('message')}"
                        broker_errors.append(err_msg)
            except Exception as e:
                err_msg = f"Account #{account.id} (@{account.user.username}) exception: {str(e)}"
                broker_errors.append(err_msg)
                logger.error("❌ [Risk Reset] Failed to deactivate broker kill switch: %s", err_msg)

    summary = {
        'users_reset_count': updated_count,
        'broker_accounts_deactivated': broker_deactivated_count,
        'errors': broker_errors
    }
    logger.info("🏁 [Risk Reset] Completed morning reset. Summary: %s", summary)
    return summary
