from django.db import models

# Role Choice
class MemberRoleChoices(models.TextChoices):
    ADMIN = "admin", "Admin"
    STAFF = "staff", "Staff"
    DEVELOPER = "developer", "Developer"
    CUSTOMER = "customer", "Customer"
    TRADERS = "traders", "Traders"

# Broker Choices
class BrokerChoices(models.TextChoices):
    FYERS = "fyers", "FYERS"
    DHAN = "dhan", "DHAN"


# P&L Status Choices
class PLStatusChoices(models.TextChoices):
    PROFIT = "profit", "PROFIT"
    LOSS = "loss", "LOSS"
    NO_TRADE = "no_trade", "NO TRADE"
    NEUTRAL = "neutral", "NEUTRAL"
    HEAVY_LOSS = "heavy_loss", "HEAVY LOSS"
    HEAVY_PROFIT = "heavy_profit", "HEAVY PROFIT"

