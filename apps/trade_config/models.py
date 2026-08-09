from django.db import models
from apps.users.models import User
from apps.common.models import BaseModel
from apps.common.choices import RiskTypeChoices


# --- Trade Execution Configuration ---
class TradeExecConfig(BaseModel):
    # Identification
    name = models.CharField(max_length=255, help_text="Configuration name or title")
    # Foreign Keys & Relations
    admins_user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='trade_config_exec', verbose_name="Marmot User")
    # General Status
    is_active = models.BooleanField(default=True, help_text="Master toggle to enable or disable auto trade execution features")
    # Risk Controls (Max Limits)
    max_loss_limit = models.DecimalField(max_digits=12, decimal_places=2, help_text="Maximum allowed loss limit before auto-freeze triggers")
    max_profit_limit = models.DecimalField(max_digits=12, decimal_places=2, help_text="Target max profit limit for the session")
    # Lot & Position Sizing
    auto_lot_status = models.BooleanField(default=False, help_text="Enable automatic lot size calculation based on risk parameters")
    default_lot_size = models.PositiveIntegerField(default=1, help_text="Default lot size to use when auto lot status is disabled")
    # Stop Loss Sizing
    auto_sl_status = models.BooleanField(default=False, help_text="Automatically attach default stop loss to outgoing orders")
    default_risk_value = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, help_text="Default risk value (e.g. 1.5% or 50 points depending on risk type)")
    default_risk_type = models.CharField(max_length=20, choices=RiskTypeChoices.choices, default=RiskTypeChoices.PERCENTAGE, help_text="Calculation mode for default stop loss risk")
    # Layering / Pyramiding Logic
    layer_status = models.BooleanField(default=False, help_text="Enable order layering (pyramiding into winning positions)")
    layer_add_in_lot_count = models.PositiveSmallIntegerField(default=0, help_text="Number of additional lots to add per layer entry")
    layer_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, help_text="Percentage step/distance required to trigger each layer entry")
    # Feature Toggles
    forecast_status = models.BooleanField(default=False, help_text="Enable algorithmic predictive forecasting for position entries")
    backtest_status = models.BooleanField(default=False, help_text="Enable backtest execution simulation mode")

    class Meta:
        verbose_name = "Trade Execution Configuration"
        verbose_name_plural = "Trade Execution Configurations"
        ordering = ['-id']

    def __str__(self):
        return f"{self.name} - Exec Config: {self.admins_user.username} (Active: {self.is_active})"