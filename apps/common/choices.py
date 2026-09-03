from django.db import models

# Task Execution Choices
class TaskStatusChoices(models.TextChoices):
    CREATED = 'created', 'Created'
    PENDING = 'pending', 'Pending'
    RUNNING = 'running', 'Running'
    PAUSED = 'paused', 'Paused'
    CANCELLED = 'cancelled', 'Cancelled'
    COMPLETED = 'completed', 'Completed'
    ERROR = 'error', 'Error'


# Market Index Choices
class IndexChoices(models.TextChoices):
    NIFTY = 'NIFTY', 'Nifty 50'
    BANKNIFTY = 'BANKNIFTY', 'Bank Nifty'
    FINNIFTY = 'FINNIFTY', 'Fin Nifty'
    MIDCPNIFTY = 'MIDCPNIFTY', 'Midcp Nifty'
    SENSEX = 'SENSEX', 'BSE Sensex'
    GIFTNIFTY = 'GIFTNIFTY', 'GIFT Nifty'
    INDIAVIX = 'INDIAVIX', 'India VIX'



# Strategy Choices
class StrategyChoices(models.TextChoices):
    TENSORTRADE_RL = 'tensortrade_rl', 'TensorTrade RL (Deep Reinforcement Learning)'


# Strike Selection Choices
class StrikeSelectionChoices(models.TextChoices):
    ATM = 'ATM', 'ATM (At The Money)'
    ITM1 = 'ITM1', 'ITM 1 (In The Money - 1 Strike)'
    ITM2 = 'ITM2', 'ITM 2 (In The Money - 2 Strikes)'
    OTM1 = 'OTM1', 'OTM 1 (Out of The Money + 1 Strike)'
    OTM2 = 'OTM2', 'OTM 2 (Out of The Money + 2 Strikes)'


# Member Role Choices
class MemberRoleChoices(models.TextChoices):
    ADMIN = "admin", "Admin"
    STAFF = "staff", "Staff"
    DEVELOPER = "developer", "Developer"
    CUSTOMER = "customer", "Customer"
    TRADERS = "traders", "Traders"
    MEMBER = "member", "Member"


# Broker Integration Choices
class BrokerChoices(models.TextChoices):
    FYERS = "fyers", "FYERS"
    DHAN = "dhan", "DHAN"


# P&L Performance Choices
class PLStatusChoices(models.TextChoices):
    PROFIT = "profit", "PROFIT"
    LOSS = "loss", "LOSS"
    NO_TRADE = "no_trade", "NO TRADE"
    NEUTRAL = "neutral", "NEUTRAL"
    HEAVY_LOSS = "heavy_loss", "HEAVY LOSS"
    HEAVY_PROFIT = "heavy_profit", "HEAVY PROFIT"


# Risk Management Type Choices
class RiskTypeChoices(models.TextChoices):
    PERCENTAGE = "percentage", "Percentage (%)"
    FIXED_AMOUNT = "fixed_amount", "Fixed Amount (₹/$)"
    POINTS = "points", "Points"


# Gateway Service Choices
class GatewayServiceChoices(models.TextChoices):
    TWILIO_SMS = "TWILIO", "Twilio SMS"
    GO_RIVER = "GO_RIVER", "Go River Worker"
    LOCAL_DB = "LOCAL_DB", "Local Database"


# Test Log Status Choices
class TestLogStatusChoices(models.TextChoices):
    PENDING = "PENDING", "Pending"
    SUCCESS = "SUCCESS", "Success"
    FAILED = "FAILED", "Failed"


# Test Log Event Choices
class TestLogEventChoices(models.TextChoices):
    ADMIN_TEST_OTP_DISPATCH = "ADMIN_TEST_OTP_DISPATCH", "Admin Test OTP Dispatch"
    ADMIN_TEST_OTP_VERIFY = "ADMIN_TEST_OTP_VERIFY", "Admin Test OTP Verify"


# Account Type Choices
class AccountTypeChoices(models.TextChoices):
    LIVE = "LIVE", "Live Account"
    SANDBOX = "SANDBOX", "Sandbox Account"


# ─── New: Market Type Choices ───────────────────────────────────────────────
class MarketTypeChoices(models.TextChoices):
    INDEX_FO = "INDEX_FO", "INDEX / F&O (India — Nifty, BankNifty…)"
    FOREX_FUTURES = "FOREX_FUTURES", "FOREX / Futures (CME Micro Futures)"


# ─── New: Forex / CME Micro Futures Instrument Choices ──────────────────────
class ForexInstrumentChoices(models.TextChoices):
    XAUUSD_MGC  = "MGC",  "XAUUSD / Gold  →  MGC  (Micro Gold)"
    EURUSD_M6E  = "M6E",  "EURUSD          →  M6E  (Micro Euro FX)"
    USDJPY_M6J  = "M6J",  "USDJPY          →  M6J  (Micro Japanese Yen)"
    US30_MYM    = "MYM",  "US30 / Dow      →  MYM  (Micro Dow)"
    NAS100_MNQ  = "MNQ",  "NAS100 / Nasdaq →  MNQ  (Micro Nasdaq)"
    SPX500_MES  = "MES",  "SPX500 / S&P    →  MES  (Micro S&P 500)"
    USOIL_MCL   = "MCL",  "USOIL / Crude   →  MCL  (Micro Crude Oil)"


# Databento Order Flow Data Schema Choices
class DatabentoSchemaChoices(models.TextChoices):
    OHLCV_1M = 'ohlcv-1m', '1-Min Candles (OHLCV)'
    TRADES   = 'trades',   'Tick-by-Tick Executions'
    MBP_10   = 'mbp-10',   'Level-10 Order Book Depth (DOM)'
    MBO      = 'mbo',      'Full Market-By-Order Flow'


# Logger Category Choices (Marmot Trading Platform Apps & Subsystems)
class LoggerCategoryChoices(models.TextChoices):
    TRADING = "TRADING", "Trading Core Engine"
    TRADE_CONFIG = "TRADE_CONFIG", "Strategy & Trade Config"
    MARKET = "MARKET", "Market Data Ingestion"
    NOTIFICATIONS = "NOTIFICATIONS", "Notifications & Alerts"
    POSTBACK = "POSTBACK", "Broker Webhook Postback"
    USERS = "USERS", "Trader Accounts & Auth"
    ADMINS = "ADMINS", "Admin Management"
    BACKTEST = "BACKTEST", "Backtesting Engine"
    MASTERS = "MASTERS", "Master Symbols & Instruments"
    SYSTEM = "SYSTEM", "Core System"


# AI Copilot Chat Role Choices
class AIChatRoleChoices(models.TextChoices):
    USER = "user", "User"
    MODEL = "model", "Model"


class PermanentLogTargets:
    """Defines target tuples (app, log_type) that should never be cleaned up."""
    ALL = [
        ("trade_core", "order_audit"),
        ("trade_core", "execution_audit"),
        ("users", "auth_audit"),
        ("notifications", "email_audit"),
        ("postback", "webhook_audit"),
    ]

