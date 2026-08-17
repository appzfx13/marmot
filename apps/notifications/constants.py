class EmailTemplateConstants:
    """Central registry of email template paths across the platform."""
    BASE = "emails/base_email.html"
    OTP = "emails/otp_email.html"
    WELCOME = "emails/welcome_email.html"
    PASSWORD_RESET = "emails/password_reset_email.html"
    TRADE_ALERT = "emails/trade_alert_email.html"
    NOTIFICATION = "emails/notification_email.html"
    KILL_SWITCH = "emails/kill_switch_email.html"
    ACCOUNT_ACTIVATION = "emails/activation_email.html"


class EmailSubjectConstants:
    """Standardized email subjects for automated notifications."""
    OTP_VERIFICATION = "Your Marmot Verification Code: {otp}"
    WELCOME = "Welcome to Marmot Algorithmic Trading Platform"
    PASSWORD_RESET = "Password Reset Request — Marmot Platform"
    TRADE_ALERT = "[Trade Alert] {action} {symbol} — Marmot"
    NOTIFICATION = "[Marmot] {title}"
    KILL_SWITCH_TRIGGERED = "🚨 CRITICAL: Emergency Kill Switch Activated"
    ACCOUNT_ACTIVATION = "Activate Your Marmot Trading Account"
