import hmac
import hashlib
from django.conf import settings


def get_user_hash(user_id: int) -> str:
    """Generates a deterministic HMAC-SHA256 hash for a given user ID."""
    if not user_id:
        return ""
    secret_key = getattr(settings, 'HASH_SECRET_KEY', getattr(settings, 'SECRET_KEY', ''))
    secret_bytes = secret_key.encode('utf-8') if isinstance(secret_key, str) else secret_key
    return hmac.new(secret_bytes, str(user_id).encode('utf-8'), hashlib.sha256).hexdigest()


def get_user_event_channel(user_id: int) -> str:
    """Returns Redis group name for a user."""
    user_hash = get_user_hash(user_id)
    return f"user_events_{user_hash}" if user_hash else ""


from apps.notifications.constants import EmailTemplateConstants, EmailSubjectConstants
from apps.notifications.services.email import (
    EmailService,
    send_otp_email,
    send_welcome_email,
    send_password_reset_email,
    send_notification_email,
    send_trade_alert_email,
    send_kill_switch_alert_email,
)