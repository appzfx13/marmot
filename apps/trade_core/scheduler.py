import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

_scheduler = None


def renew_keep_alive_tokens_job():
    """Periodic job running every 8 hours to refresh active Dhan access tokens."""
    from apps.trade_config.models import UserTradingAccount
    from apps.trade_core.services.dhan_token_service import renew_access_token

    logger.info("🔄 [APScheduler] Starting 8-hour Dhan Keep-Alive Token Renewal Job...")
    active_accounts = UserTradingAccount.objects.filter(
        is_active=True,
        is_deleted=False,
        keep_alive=True,
        account_type='LIVE'
    ).select_related('broker', 'user')

    total_renewed = 0
    total_failed = 0

    for account in active_accounts:
        broker_code = getattr(account.broker, 'code', '').lower()
        if broker_code not in ['dhan', 'dhanhq']:
            continue

        client_id = (account.broker_client_id or '').strip()
        current_token = (account.api_key or '').strip()

        if not client_id or not current_token:
            logger.warning("Skipping account #%s (@%s): Missing client ID or token.", account.id, account.user.username)
            continue

        try:
            logger.info("Renewing Dhan token for account #%s (@%s, Client ID: %s)", account.id, account.user.username, client_id)
            new_token = renew_access_token(client_id=client_id, access_token=current_token)

            if new_token:
                account.api_key = new_token
                account.last_token_refreshed_at = timezone.now()
                account.save(update_fields=['api_key', 'last_token_refreshed_at'])
                total_renewed += 1
                logger.info("✅ Token renewed and updated in database for account #%s (@%s)", account.id, account.user.username)
        except Exception as e:
            total_failed += 1
            logger.error("❌ Token renewal failed for account #%s (@%s): %s", account.id, account.user.username, e)

    logger.info("🏁 [APScheduler] Token Renewal Finished. Renewed: %d, Failed: %d", total_renewed, total_failed)


def start_scheduler():
    """Initialize and start the background APScheduler instance safely."""
    global _scheduler

    if _scheduler is not None and _scheduler.running:
        logger.info("[APScheduler] Background scheduler is already running.")
        return

    tz_str = getattr(settings, 'APSCHEDULER_TIMEZONE', 'Asia/Kolkata')
    _scheduler = BackgroundScheduler(timezone=tz_str)

    # Register 8-hour token renewal job
    _scheduler.add_job(
        renew_keep_alive_tokens_job,
        trigger=IntervalTrigger(hours=8),
        id='dhan_token_renewal_8h',
        name='Renew Dhan Keep-Alive Tokens (8-hour Interval)',
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    try:
        _scheduler.start()
        logger.info("🚀 [APScheduler] BackgroundScheduler started successfully with 8h Dhan Token Renewal Job.")
    except Exception as e:
        logger.error("Failed to start BackgroundScheduler: %s", e)
