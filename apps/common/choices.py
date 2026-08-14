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
    INDIAVIX = 'INDIAVIX', 'India VIX'


# Go Strategy Plugin Choices
class StrategyChoices(models.TextChoices):
    ICT_SMC = 'ict_smc', 'ICT / SMC (Order Block & FVG)'
    GAMMA_BLAST = 'gamma_blast', 'Expiry Gamma Blast (0DTE)'
    CANDLE_3PM = 'candle_3pm', '3:00 PM Breakout Candle'


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

