# apps/common/constants.py

# Task Control & Redis Configuration
REDIS_CHANNEL = 'market_backup_commands'

# Market Index Instruments Map
INDEX_INSTRUMENT_MAP = {
    'NIFTY':      {"security_id": "13",  "exchange_segment": "IDX_I", "instrument": "INDEX"},
    'BANKNIFTY':  {"security_id": "25",  "exchange_segment": "IDX_I", "instrument": "INDEX"},
    'FINNIFTY':   {"security_id": "27",  "exchange_segment": "IDX_I", "instrument": "INDEX"},
    'MIDCPNIFTY': {"security_id": "26",  "exchange_segment": "IDX_I", "instrument": "INDEX"},
    'INDIAVIX':   {"security_id": "17",  "exchange_segment": "IDX_I", "instrument": "INDEX"},
}

# Options Download Configuration — Instrument & Segment for NSE F&O Options
INDEX_OPTIONS_MAP = {
    'NIFTY':      {"exchange_segment": "NSE_FO", "instrument": "OPTIDX"},
    'BANKNIFTY':  {"exchange_segment": "NSE_FO", "instrument": "OPTIDX"},
    'FINNIFTY':   {"exchange_segment": "NSE_FO", "instrument": "OPTIDX"},
    'MIDCPNIFTY': {"exchange_segment": "NSE_FO", "instrument": "OPTIDX"},
}

# Strike Price Step per Index
INDEX_STRIKE_INTERVAL = {
    'NIFTY':      50,
    'BANKNIFTY':  100,
    'FINNIFTY':   50,
    'MIDCPNIFTY': 25,
}

# Platform Numerical Defaults
DEFAULT_INITIAL_CAPITAL = 100000.0
DEFAULT_RISK_REWARD_RATIO = 2.0
DEFAULT_STOP_LOSS_PCT = 0.5
DEFAULT_STRIKE_COUNT = 5
MAX_LOG_LINES = 200


# Admin System Messages
class Messages:
    """Admin CRUD status messages and generic system fallbacks."""
    TRADER_CREATED = "Trader profile was successfully created."
    TRADER_UPDATED = "Trader profile details have been updated."
    TRADER_DELETED = "Trader profile has been removed."

    LOGIN_SUCCESS = "Login successful!"
    LOGOUT_SUCCESS = "You have been logged out successfully."

    CONFIG_CREATED = "Trade execution configuration created successfully."
    CONFIG_UPDATED = "Trade execution configuration updated successfully."
    CONFIG_DELETED = "Trade execution configuration deleted successfully."

    GENERIC_ERROR = "An error occurred while processing your request. Please try again."


# User Portal Messages
class UserMessages:
    """User notification strings and system messages for users app."""
    PROFILE_UPDATED = "Profile settings updated successfully!"
    PASSWORD_CHANGED = "Password changed successfully!"
    OTP_SENT = "OTP has been sent to your email/phone."
    OTP_VERIFIED = "OTP verified successfully."
    INVALID_OTP = "Invalid or expired OTP code. Please try again."
    LOGIN_SUCCESS = "Welcome back to Marmot Trading Platform."
    LOGOUT_SUCCESS = "Logged out successfully."
    ACCOUNT_CREATED = "Trading account configured successfully."
    ACCOUNT_DELETED = "Trading account deleted successfully."
    ACCOUNT_DEFAULT_SET = "Default trading account updated."
    KILL_SWITCH_ACTIVATED = "Emergency Kill Switch activated! All orders cancelled and positions squared off."


# Email Notification Constants
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
