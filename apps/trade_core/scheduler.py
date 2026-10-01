import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
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


def fetch_macro_ai_data_job():
    """Periodic job running every 1 hour to synthesize live macro intelligence via Gemini AI."""
    from django.core.cache import cache
    from apps.common.services.gemini_service import GeminiAIService

    logger.info("🤖 [APScheduler] Starting 1-hour Gemini Macro AI Ingestion Job...")
    try:
        intel = GeminiAIService.fetch_current_macro_ai_intel(selected_index="NIFTY")
        if intel:
            cache.set("marmot:macro_ai:latest_intel", intel, timeout=7200)
            logger.info("✅ [APScheduler] Gemini Macro AI Ingestion Succeeded (Model: %s, Stance: %s)",
                        intel.get("model"), intel.get("regime_stance"))
            return intel
    except Exception as e:
        logger.error("❌ [APScheduler] Gemini Macro AI Ingestion Failed: %s", e)
    return None


def get_cached_macro_ai_intel(selected_index="NIFTY"):
    """Returns cached Gemini Macro AI intel or triggers on-demand computation if cold."""
    from django.core.cache import cache
    cached = cache.get("marmot:macro_ai:latest_intel")
    if not cached:
        cached = fetch_macro_ai_data_job()
    return cached


def daily_morning_unfreeze_and_unblock_job():
    """Runs daily at 6, 7, 8, and 9 AM IST to unfreeze and unblock all active traders."""
    from apps.trade_core.services.risk_reset_service import unfreeze_and_unblock_active_traders

    logger.info("⏰ [APScheduler] Triggered Daily Morning Unfreeze & Kill Switch Reset Job...")
    try:
        summary = unfreeze_and_unblock_active_traders(deactivate_broker_killswitch=True)
        logger.info("✅ [APScheduler] Daily Morning Unfreeze Job Succeeded. Summary: %s", summary)
        return summary
    except Exception as e:
        logger.error("❌ [APScheduler] Daily Morning Unfreeze Job Failed: %s", e)
        return None


def start_daily_spot_1s_recorder_job():
    """Triggered by APScheduler at 09:14:55 AM IST Mon-Fri to activate Go 1S spot Parquet recorder."""
    import json
    import redis
    logger.info("🔔 [APScheduler] Triggering Market Open 1S Index Spot Parquet Recording...")
    try:
        r = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
        r.set("marmot:live_record:active", "1")
        payload = json.dumps({"action": "start_spot_1s_record"})
        r.publish("marmot:tasks:control", payload)
        logger.info("✅ [APScheduler] Published start_spot_1s_record to marmot:tasks:control")
    except Exception as e:
        logger.error("❌ [APScheduler] Failed to start live 1S spot recorder: %s", e)


def stop_daily_spot_1s_recorder_job():
    """Triggered by APScheduler at 15:30:05 PM IST Mon-Fri to finalize and flush Go 1S spot recorder."""
    import json
    import redis
    logger.info("🔕 [APScheduler] Triggering Market Close 1S Index Spot Parquet Finalization...")
    try:
        r = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
        r.set("marmot:live_record:active", "0")
        payload = json.dumps({"action": "stop_spot_1s_record"})
        r.publish("marmot:tasks:control", payload)
        logger.info("✅ [APScheduler] Published stop_spot_1s_record to marmot:tasks:control")
    except Exception as e:
        logger.error("❌ [APScheduler] Failed to stop live 1S spot recorder: %s", e)


def run_postmarket_option_merge_job():
    """Triggered by APScheduler at 16:00:00 PM IST Mon-Fri to fetch 1S options and merge into unified dataset."""
    import json
    import redis
    from django.utils import timezone
    logger.info("📦 [APScheduler] Triggering 4:00 PM Post-Market 1S Option Fetch & Consolidation Job...")
    try:
        r = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
        today_str = timezone.localdate().strftime('%Y-%m-%d')
        payload = json.dumps({
            "action": "run_daily_postmarket_merge",
            "date": today_str,
            "indices": ["NIFTY", "BANKNIFTY"],
            "strike_count": 15,
        })
        r.publish("marmot:tasks:control", payload)
        logger.info("✅ [APScheduler] Published run_daily_postmarket_merge for %s to marmot:tasks:control", today_str)
    except Exception as e:
        logger.error("❌ [APScheduler] Failed to trigger post-market option merge job: %s", e)


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

    # Register 1-hour Gemini Macro AI Ingestion job
    _scheduler.add_job(
        fetch_macro_ai_data_job,
        trigger=IntervalTrigger(hours=1),
        id='gemini_macro_ai_sync_1h',
        name='Gemini AI Hourly Macro Intelligence Sync',
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    # Register Daily Morning Unfreeze & Kill Switch Reset Job (6, 7, 8, 9 AM IST)
    _scheduler.add_job(
        daily_morning_unfreeze_and_unblock_job,
        trigger=CronTrigger(hour='6,7,8,9', minute=0, timezone=tz_str),
        id='morning_unfreeze_reset_cron',
        name='Daily Morning Unfreeze & Kill Switch Reset (6, 7, 8, 9 AM IST)',
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    # Register Market Open (09:14:55 AM Mon-Fri) 1S Live Spot Recorder Job
    _scheduler.add_job(
        start_daily_spot_1s_recorder_job,
        trigger=CronTrigger(day_of_week='mon-fri', hour=9, minute=14, second=55, timezone=tz_str),
        id='market_open_spot_1s_recorder_start',
        name='Start Live 1S Index Spot Recorder at Market Open (09:14:55 AM IST)',
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    # Register Market Close (15:30:05 PM Mon-Fri) 1S Live Spot Recorder Job
    _scheduler.add_job(
        stop_daily_spot_1s_recorder_job,
        trigger=CronTrigger(day_of_week='mon-fri', hour=15, minute=30, second=5, timezone=tz_str),
        id='market_close_spot_1s_recorder_stop',
        name='Stop Live 1S Index Spot Recorder at Market Close (15:30:05 PM IST)',
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    # Register 4:00 PM Post-Market (16:00:00 PM Mon-Fri) 1S Option Merge Job
    _scheduler.add_job(
        run_postmarket_option_merge_job,
        trigger=CronTrigger(day_of_week='mon-fri', hour=16, minute=0, second=0, timezone=tz_str),
        id='postmarket_option_merge_4pm',
        name='Post-Market 1S Option Fetch & Parquet Consolidation (16:00:00 PM IST)',
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    try:
        _scheduler.start()
        logger.info("🚀 [APScheduler] BackgroundScheduler started with Token Renewal, Gemini Macro, 1S Spot & 4PM Merge Jobs.")
    except Exception as e:
        logger.error("Failed to start BackgroundScheduler: %s", e)


