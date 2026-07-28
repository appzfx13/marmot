import logging
import requests

from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger(__name__)


def ping_health():
    try:
        response = requests.get("https://bug-tracker-z4mi.onrender.com/", timeout=5)
        logger.info("Health ping status %s", response.status_code)
        print("PING WORKS", response.status_code)
    except Exception as exc:
        logger.exception("Health ping failed: %s", exc)
        print("PING EXCEPTION", exc)


scheduler = BackgroundScheduler()


def start_scheduler():
    if scheduler.running:
        return
    scheduler.add_job(ping_health, "interval", hours=15, id="health_ping", replace_existing=True)
    scheduler.start()