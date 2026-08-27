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

# Historical Lot Size Timelines for Indian Indices (NSE & BSE Circulars 2020 to Present)
HISTORICAL_INDEX_LOT_SIZES = {
    'NIFTY': [
        ('2024-04-26', 25),      # May 2024 expiry onwards (NSE/FAOP/61328): 25
        ('2021-07-01', 50),      # July 2021 expiry to April 2024 (NSE/FAOP/47786): 50
        ('2020-01-01', 75),      # 2020 to June 2021: 75
        ('1990-01-01', 75),      # Prior to 2020: 75
    ],
    'BANKNIFTY': [
        ('2024-11-20', 30),      # Nov 20, 2024 SEBI revision (NSE/FAOP/64515): 30
        ('2023-07-14', 15),      # July 2023 to Nov 2024 (NSE/FAOP/56177): 15
        ('2020-07-31', 25),      # July 2020 to July 2023 (NSE/FAOP/44358): 25
        ('2020-01-01', 20),      # Early 2020: 20
        ('1990-01-01', 20),      # Historical default: 20
    ],
    'FINNIFTY': [
        ('2024-11-20', 65),      # Nov 20, 2024 SEBI revision: 65
        ('2023-01-01', 25),      # Jan 2023 to Nov 2024: 25
        ('2021-01-11', 40),      # Launch Jan 2021 to Dec 2022: 40
        ('1990-01-01', 40),      # Fallback: 40
    ],
    'MIDCPNIFTY': [
        ('2024-11-20', 50),      # Nov 20, 2024 SEBI revision: 50
        ('2022-01-24', 75),      # Launch Jan 2022 to Nov 2024: 75
        ('1990-01-01', 75),      # Fallback: 75
    ],
    'SENSEX': [
        ('2024-11-20', 20),      # Nov 20, 2024 revision: 20
        ('2023-05-15', 10),      # Relaunch May 2023 to Nov 2024: 10
        ('1990-01-01', 10),      # Fallback: 10
    ],
    'BANKEX': [
        ('2024-11-20', 30),      # Nov 20, 2024 revision: 30
        ('2023-05-15', 15),      # Relaunch May 2023 to Nov 2024: 15
        ('1990-01-01', 15),      # Fallback: 15
    ],
}

# Historical Index Expiry Timelines & Day-of-Week (2020 to Present)
HISTORICAL_INDEX_EXPIRY_DAYS = {
    'NIFTY': [
        ('2020-01-01', 'Thursday', 3), # 2020 to Present: Thursday
        ('1990-01-01', 'Thursday', 3),
    ],
    'BANKNIFTY': [
        ('2024-11-20', 'Thursday', 3), # Monthly Thursday only (Weekly discontinued Nov 2024)
        ('2023-09-04', 'Wednesday', 2), # Wednesday weekly (Sept 2023 - Nov 2024)
        ('2020-01-01', 'Thursday', 3), # 2020 to Sept 2023: Thursday
        ('1990-01-01', 'Thursday', 3),
    ],
    'FINNIFTY': [
        ('2021-01-11', 'Tuesday', 1),  # Launch Jan 2021 to Present: Tuesday
        ('1990-01-01', 'Tuesday', 1),
    ],
    'MIDCPNIFTY': [
        ('2023-08-21', 'Monday', 0),   # Shifted to Monday in Aug 2023
        ('2022-01-24', 'Wednesday', 2),# Launch Jan 2022: Wednesday
        ('1990-01-01', 'Monday', 0),
    ],
    'SENSEX': [
        ('2023-05-15', 'Friday', 4),   # Relaunch May 2023 to Present: Friday
        ('1990-01-01', 'Friday', 4),
    ],
    'BANKEX': [
        ('2023-05-15', 'Monday', 0),   # Relaunch May 2023 to Nov 2024: Monday
        ('1990-01-01', 'Monday', 0),
    ],
}


import datetime
import calendar


def get_historical_lot_size(index_name: str, trade_date=None) -> int:
    """Returns the regulatory exchange lot size for the given index symbol on a specific date."""
    sym = (index_name or 'NIFTY').upper().strip()
    timeline = HISTORICAL_INDEX_LOT_SIZES.get(sym)
    if not timeline:
        return 25 if 'BANK' in sym or 'NIFTY' in sym else 50

    if trade_date is None:
        return timeline[0][1]

    if isinstance(trade_date, str):
        date_str = trade_date[:10]
    elif hasattr(trade_date, 'strftime'):
        date_str = trade_date.strftime('%Y-%m-%d')
    else:
        date_str = str(trade_date)[:10]

    for effective_date, lot_size in timeline:
        if date_str >= effective_date:
            return lot_size
    return timeline[-1][1]


def get_index_expiry_info(index_name: str, trade_date=None) -> dict:
    """Returns the active weekly/monthly expiry weekday and schedule for the index on a given date."""
    sym = (index_name or 'NIFTY').upper().strip()
    timeline = HISTORICAL_INDEX_EXPIRY_DAYS.get(sym)
    if not timeline:
        return {"day_name": "Thursday", "weekday": 3}

    if trade_date is None:
        eff, day_name, weekday = timeline[0]
        return {"day_name": day_name, "weekday": weekday}

    if isinstance(trade_date, str):
        date_str = trade_date[:10]
    elif hasattr(trade_date, 'strftime'):
        date_str = trade_date.strftime('%Y-%m-%d')
    else:
        date_str = str(trade_date)[:10]

    for item in timeline:
        effective_date = item[0]
        if date_str >= effective_date:
            return {"day_name": item[1], "weekday": item[2]}
    return {"day_name": timeline[-1][1], "weekday": timeline[-1][2]}


def get_next_expiry_date(index_name: str, trade_date=None) -> datetime.date:
    """Calculates the exact upcoming weekly or monthly exchange expiry date for the index."""
    if trade_date is None:
        trade_dt = datetime.date.today()
    elif isinstance(trade_date, str):
        trade_dt = datetime.datetime.strptime(trade_date[:10], '%Y-%m-%d').date()
    elif isinstance(trade_date, datetime.datetime):
        trade_dt = trade_date.date()
    else:
        trade_dt = trade_date

    sym = (index_name or 'NIFTY').upper().strip()
    expiry_info = get_index_expiry_info(sym, trade_dt)
    target_weekday = expiry_info["weekday"]

    is_monthly_only = False
    if sym == 'BANKNIFTY' and trade_dt >= datetime.date(2024, 11, 20):
        is_monthly_only = True
    elif sym == 'BANKEX' and trade_dt >= datetime.date(2024, 11, 20):
        is_monthly_only = True

    if is_monthly_only:
        year = trade_dt.year
        month = trade_dt.month
        last_day = calendar.monthrange(year, month)[1]
        last_date = datetime.date(year, month, last_day)
        offset = (last_date.weekday() - target_weekday) % 7
        monthly_expiry = last_date - datetime.timedelta(days=offset)
        if trade_dt <= monthly_expiry:
            return monthly_expiry
        else:
            next_month = month + 1 if month < 12 else 1
            next_year = year if month < 12 else year + 1
            next_last_day = calendar.monthrange(next_year, next_month)[1]
            next_last_date = datetime.date(next_year, next_month, next_last_day)
            next_offset = (next_last_date.weekday() - target_weekday) % 7
            return next_last_date - datetime.timedelta(days=next_offset)

    current_weekday = trade_dt.weekday()
    days_ahead = (target_weekday - current_weekday) % 7
    return trade_dt + datetime.timedelta(days=days_ahead)


def calculate_dte(index_name: str, trade_date=None) -> int:
    """Returns the exact Days to Expiry (DTE): 0 for Expiry Day, 1 for 1-day prior, etc."""
    if trade_date is None:
        trade_dt = datetime.date.today()
    elif isinstance(trade_date, str):
        trade_dt = datetime.datetime.strptime(trade_date[:10], '%Y-%m-%d').date()
    elif isinstance(trade_date, datetime.datetime):
        trade_dt = trade_date.date()
    else:
        trade_dt = trade_date

    next_exp = get_next_expiry_date(index_name, trade_dt)
    return max(0, (next_exp - trade_dt).days)


def is_monthly_expiry_date(index_name: str, expiry_date) -> bool:
    """Returns True if the given expiry date is the final monthly expiry of that calendar month."""
    if isinstance(expiry_date, str):
        exp_dt = datetime.datetime.strptime(expiry_date[:10], '%Y-%m-%d').date()
    elif isinstance(expiry_date, datetime.datetime):
        exp_dt = expiry_date.date()
    else:
        exp_dt = expiry_date

    next_week = exp_dt + datetime.timedelta(days=7)
    return next_week.month != exp_dt.month


def get_option_expiry_analysis(index_name: str, trade_date=None, strike_price: float = 0.0, spot_price: float = 0.0, option_type: str = "CE") -> dict:
    """Computes comprehensive expiry analytics: DTE, 0DTE flag, contract type, and settlement moneyness."""
    if trade_date is None:
        trade_dt = datetime.date.today()
    elif isinstance(trade_date, str):
        trade_dt = datetime.datetime.strptime(trade_date[:10], '%Y-%m-%d').date()
    elif isinstance(trade_date, datetime.datetime):
        trade_dt = trade_date.date()
    else:
        trade_dt = trade_date

    next_exp = get_next_expiry_date(index_name, trade_dt)
    dte = max(0, (next_exp - trade_dt).days)
    is_0dte = (dte == 0)
    is_monthly = is_monthly_expiry_date(index_name, next_exp)
    contract_type = "Monthly Expiry" if is_monthly else "Weekly Expiry"

    opt_type = option_type.upper().strip()
    strike = float(strike_price or 0.0)
    spot = float(spot_price or 0.0)

    if opt_type == "CE":
        intrinsic_value = max(0.0, spot - strike) if strike > 0 and spot > 0 else 0.0
        moneyness = "ITM" if spot > strike + 25 else ("OTM" if spot < strike - 25 else "ATM")
    else:
        intrinsic_value = max(0.0, strike - spot) if strike > 0 and spot > 0 else 0.0
        moneyness = "ITM" if spot < strike - 25 else ("OTM" if spot > strike + 25 else "ATM")

    return {
        "expiry_date": next_exp.strftime("%Y-%m-%d"),
        "expiry_day": next_exp.strftime("%A"),
        "dte": dte,
        "is_0dte": is_0dte,
        "is_monthly": is_monthly,
        "contract_type": contract_type,
        "moneyness": moneyness,
        "intrinsic_value": round(intrinsic_value, 2),
        "expiry_tag": f"{'0DTE ' if is_0dte else f'{dte}DTE '}{contract_type} ({next_exp.strftime('%d %b')})",
    }


FOREX_INSTRUMENT_SPECS = {
    'MGC': {"name": "Micro Gold", "tick_size": 0.1, "point_value": 10.0, "tick_value": 1.0, "currency": "USD"},
    'M6E': {"name": "Micro Euro", "tick_size": 0.0001, "point_value": 125000.0, "tick_value": 1.25, "currency": "USD"},
    'MNQ': {"name": "Micro E-mini Nasdaq-100", "tick_size": 0.25, "point_value": 2.0, "tick_value": 0.50, "currency": "USD"},
    'MES': {"name": "Micro E-mini S&P 500", "tick_size": 0.25, "point_value": 5.0, "tick_value": 1.25, "currency": "USD"},
    'MCL': {"name": "Micro WTI Crude Oil", "tick_size": 0.01, "point_value": 100.0, "tick_value": 1.0, "currency": "USD"},
    'MYM': {"name": "Micro E-mini Dow", "tick_size": 1.0, "point_value": 0.5, "tick_value": 0.50, "currency": "USD"},
    'M6J': {"name": "Micro Japanese Yen", "tick_size": 0.000001, "point_value": 1250000.0, "tick_value": 1.25, "currency": "USD"},
}


def calculate_trade_charges(entry_price: float, exit_price: float, quantity: int, is_option: bool = True, is_forex: bool = False) -> dict:
    """Calculates regulatory & broker charges for Indian Options or CME Forex Micro Futures."""
    buy_turnover = float(entry_price) * int(quantity)
    sell_turnover = float(exit_price) * int(quantity)

    if is_forex:
        # CME Micro Futures Commission: ~$0.75 per side ($1.50 round-turn per micro contract)
        total_brokerage = round(float(quantity) * 1.50, 2)
        return {
            "brokerage": total_brokerage,
            "stt": 0.0,
            "exchange_charges": 0.0,
            "sebi_charges": 0.0,
            "stamp_duty": 0.0,
            "gst": 0.0,
            "total_charges": total_brokerage,
            "utilized_capital": round(buy_turnover, 2),
        }

    total_turnover = buy_turnover + sell_turnover

    brokerage_entry = min(20.0, buy_turnover * 0.0005) if buy_turnover > 0 else 0.0
    brokerage_exit = min(20.0, sell_turnover * 0.0005) if sell_turnover > 0 else 0.0
    total_brokerage = round(brokerage_entry + brokerage_exit, 2)

    stt = round(sell_turnover * 0.001, 2) if is_option else round(total_turnover * 0.00025, 2)
    exchange_charges = round(total_turnover * 0.0005, 2)
    sebi_charges = round(total_turnover * 0.000001, 2)
    stamp_duty = round(buy_turnover * 0.00003, 2)
    gst = round((total_brokerage + exchange_charges + sebi_charges) * 0.18, 2)

    total_charges = round(total_brokerage + stt + exchange_charges + sebi_charges + stamp_duty + gst, 2)
    return {
        "brokerage": total_brokerage,
        "stt": stt,
        "exchange_charges": exchange_charges,
        "sebi_charges": sebi_charges,
        "stamp_duty": stamp_duty,
        "gst": gst,
        "total_charges": total_charges,
        "utilized_capital": round(buy_turnover, 2),
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
