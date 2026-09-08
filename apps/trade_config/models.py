from django.core.exceptions import ValidationError
from django.db import models

from apps.common.choices import (
    AccountTypeChoices,
    ForexInstrumentChoices,
    LiveStrategyStatusChoices,
    MarketTypeChoices,
    RiskTypeChoices,
    StrategyChoices,
    TaskStatusChoices,
)
from apps.common.models import BaseModel
from apps.users.models import User


# --- Master Broker Table (Managed Dynamically by Admin) ---
class BrokerMaster(BaseModel):
    name = models.CharField(max_length=100, help_text="Broker Display Name (e.g. DHAN, FYERS, ZERODHA)")
    code = models.CharField(max_length=50, unique=True, help_text="Broker system code (e.g. dhan, fyers, sandbox)")
    api_base_url = models.URLField(blank=True, null=True, help_text="Base API Gateway URL for execution")
    is_active = models.BooleanField(default=True, help_text="Broker availability toggle")
    description = models.TextField(blank=True, help_text="Broker notes and integration details")

    class Meta:
        verbose_name = "Master Broker"
        verbose_name_plural = "Master Brokers"
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.code.upper()})"


# --- Dedicated User Trading Account Configuration Table ---
class UserTradingAccount(BaseModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='trading_accounts', verbose_name="Trader")
    broker = models.ForeignKey(BrokerMaster, on_delete=models.CASCADE, related_name='user_accounts', verbose_name="Broker Platform")
    account_name = models.CharField(max_length=150, help_text="Account Nickname (e.g. Primary Dhan Live, Fyers Alpha, Sandbox Demo)")
    account_type = models.CharField(max_length=20, choices=AccountTypeChoices.choices, default=AccountTypeChoices.SANDBOX, help_text="Account environment mode (LIVE / SANDBOX)")

    # Broker Credentials & API Keys
    broker_client_id = models.CharField(max_length=255, blank=True, null=True, help_text="Broker Client ID / User ID")
    api_key = models.TextField(blank=True, null=True, help_text="API Key / Access Token")
    app_id = models.TextField(blank=True, null=True, help_text="App ID / Secret Key")

    # Account Controls & Telemetry
    is_default = models.BooleanField(default=False, help_text="Is this the default primary trading account for the user?")
    is_active = models.BooleanField(default=True, help_text="Account active toggle")
    is_configured = models.BooleanField(default=False, help_text="API key credentials validated")
    is_trader_active = models.BooleanField(default=False, help_text="Real-time trading execution loop active for this account")
    keep_alive = models.BooleanField(default=False, help_text="Auto-refresh access token every 8 hours")
    last_token_refreshed_at = models.DateTimeField(null=True, blank=True, help_text="Timestamp of last successful token renewal")
    realtime_pnl = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, help_text="Realtime account PnL")

    # Live API Telemetry & Summary
    account_summary = models.JSONField(default=dict, blank=True, help_text="Live API Telemetry (balance, margin, positions, orders)")

    class Meta:
        verbose_name = "User Trading Account"
        verbose_name_plural = "User Trading Accounts"
        ordering = ['-is_default', 'account_type', 'account_name']

    def __str__(self):
        return f"{self.account_name} [{self.broker.name}] - @{self.user.username} ({self.account_type})"


# --- Trade Execution Configuration ---
class TradeExecConfig(BaseModel):
    # Identification
    name = models.CharField(max_length=255, help_text="Configuration name or title")
    # Foreign Keys & Relations
    admins_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='trade_configs_exec', verbose_name="Marmot User")
    trading_account = models.ForeignKey(UserTradingAccount, on_delete=models.CASCADE, related_name='strategy_configs', null=True, blank=True, verbose_name="Target Trading Account")
    # Account Mode
    account_type = models.CharField(max_length=20, choices=AccountTypeChoices.choices, default=AccountTypeChoices.SANDBOX, help_text="Target execution account mode (LIVE / SANDBOX)")

    # ─── Market Type ────────────────────────────────────────────────────────
    market_type = models.CharField(max_length=20, choices=MarketTypeChoices.choices, default=MarketTypeChoices.INDEX_FO, help_text="Market segment")

    # ─── Forex / CME Futures Fields (nullable, used when FOREX_FUTURES) ─────
    forex_instrument = models.CharField(max_length=10, choices=ForexInstrumentChoices.choices, null=True, blank=True, help_text="CME Micro Futures instrument")
    forex_broker_api_key = models.TextField(null=True, blank=True, help_text="Rithmic / OANDA / CME API Key for Forex/Futures execution")
    forex_account_id = models.CharField(max_length=255, null=True, blank=True, help_text="Forex broker account / sub-account ID")
    forex_contract_size = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True, help_text="Contract/lot size for selected CME instrument")
    forex_tick_value = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True, help_text="Value per tick in USD (e.g. $1 MGC, $1.25 MES)")
    forex_max_contracts = models.PositiveSmallIntegerField(null=True, blank=True, default=1, help_text="Max contracts allowed per trade entry")
    # General Status
    is_active = models.BooleanField(default=True, help_text="Master toggle to enable or disable auto trade execution features")
    # Risk Controls (Max Limits)
    max_loss_status = models.BooleanField(default=False, help_text="Enable maximum loss limit rule for auto-freeze")
    max_loss_limit = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, help_text="Maximum allowed loss limit before auto-freeze triggers")
    max_profit_status = models.BooleanField(default=False, help_text="Enable maximum profit limit rule")
    max_profit_limit = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, help_text="Target max profit limit for the session")

    # Lot & Position Sizing
    auto_lot_status = models.BooleanField(default=False, help_text="Enable automatic lot size calculation based on risk parameters")
    default_lot_size = models.PositiveIntegerField(default=1, blank=True, help_text="Default lot size to use when auto lot status is disabled")
    # Stop Loss Sizing
    auto_sl_status = models.BooleanField(default=False, help_text="Automatically attach default stop loss to outgoing orders")
    default_risk_value = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, blank=True, help_text="Default risk value")
    default_risk_type = models.CharField(max_length=20, choices=RiskTypeChoices.choices, default=RiskTypeChoices.PERCENTAGE, blank=True, help_text="Risk calculation mode")
    # Layering / Pyramiding Logic
    layer_status = models.BooleanField(default=False, help_text="Enable order layering (pyramiding into winning positions)")
    layer_add_in_lot_count = models.PositiveSmallIntegerField(default=0, blank=True, help_text="Number of additional lots to add per layer entry")
    layer_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, blank=True, help_text="Percentage step/distance required per layer")
    # Feature Toggles
    forecast_status = models.BooleanField(default=False, help_text="Enable algorithmic predictive forecasting for position entries")
    backtest_status = models.BooleanField(default=False, help_text="Enable backtest execution simulation mode")

    # Realtime Execution Telemetry & Feedback Logs
    execution_status = models.CharField(max_length=20, choices=TaskStatusChoices.choices, default=TaskStatusChoices.CREATED, help_text="Realtime execution status")
    realtime_pnl = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, help_text="Realtime strategy execution PnL")
    estimated_brokerage = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, help_text="Estimated brokerage & taxes incurred")
    execution_remarks = models.TextField(blank=True, null=True, help_text="Execution notes and strategy remarks")
    api_response_log = models.JSONField(default=dict, blank=True, help_text="Live API response telemetry log for Sandbox & Live trades")

    class Meta:
        verbose_name = "Trade Execution Configuration"
        verbose_name_plural = "Trade Execution Configurations"
        ordering = ['-id']

    def clean(self):
        super().clean()
        if self.max_loss_status and (self.max_loss_limit is None or self.max_loss_limit < 0):
            raise ValidationError({'max_loss_limit': 'Max Loss Limit value is required when Max Loss rule is enabled.'})
        if self.max_profit_status and (self.max_profit_limit is None or self.max_profit_limit < 0):
            raise ValidationError({'max_profit_limit': 'Max Profit Limit value is required when Max Profit rule is enabled.'})

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_active and not self.is_deleted:
            TradeExecConfig.objects.filter(
                admins_user=self.admins_user,
                is_active=True,
                is_deleted=False
            ).exclude(pk=self.pk).update(is_active=False)

    def __str__(self):
        return f"{self.name} - Exec Config: {self.admins_user.username} (Active: {self.is_active})"


# --- Deployed Live Strategy Table (Immutable Snapshot of Backtested Configuration) ---
class LiveStrategy(BaseModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='live_strategies', verbose_name="Trader")
    trading_account = models.ForeignKey(UserTradingAccount, on_delete=models.SET_NULL, null=True, blank=True, related_name='live_strategies', verbose_name="Target Trading Account")
    backtest_task = models.ForeignKey('backtest.BacktestTask', on_delete=models.SET_NULL, null=True, blank=True, related_name='live_deployments', verbose_name="Source Backtest")
    name = models.CharField(max_length=255, help_text="Live Strategy Deployment Name")
    strategy_name = models.CharField(max_length=50, choices=StrategyChoices.choices, default=StrategyChoices.TENSORTRADE_RL)
    index_name = models.CharField(max_length=50, default='NIFTY', help_text="Target trading asset (e.g. NIFTY, BANKNIFTY)")
    market_type = models.CharField(max_length=20, choices=MarketTypeChoices.choices, default=MarketTypeChoices.INDEX_FO, help_text="Market segment")
    allocated_capital = models.DecimalField(max_digits=12, decimal_places=2, default=100000.00, help_text="Allocated capital in INR")
    # FROZEN RULE & PARAMETER SNAPSHOTS (strictly isolated JSONB to prevent mutations from rulebook edits)
    frozen_rules_snapshot = models.JSONField(default=list, blank=True, help_text="Immutable snapshot of rules at deployment")
    frozen_parameters = models.JSONField(default=dict, blank=True, help_text="Immutable snapshot of parameters at deployment")
    is_active = models.BooleanField(default=False, help_text="Live execution enabled toggle (initially False)")
    execution_mode = models.CharField(max_length=20, choices=AccountTypeChoices.choices, default=AccountTypeChoices.LIVE)
    status = models.CharField(max_length=20, choices=LiveStrategyStatusChoices.choices, default=LiveStrategyStatusChoices.STANDBY)
    realtime_pnl = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, help_text="Realtime session PnL")
    total_trades = models.PositiveIntegerField(default=0, help_text="Total live trades executed")
    last_signal_at = models.DateTimeField(null=True, blank=True, help_text="Timestamp of last signal")

    class Meta:
        verbose_name = "Live Strategy"
        verbose_name_plural = "Live Strategies"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} [{self.index_name}] - @{self.user.username} (Active: {self.is_active})"


# --- Daily Portfolio Snapshot (Database Ledger for Analytics & Journals) ---
class DailyPortfolioSnapshot(BaseModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='daily_portfolio_snapshots', verbose_name="Trader")
    trading_account = models.ForeignKey(UserTradingAccount, on_delete=models.CASCADE, related_name='portfolio_snapshots', verbose_name="Trading Account")
    account_type = models.CharField(max_length=20, choices=AccountTypeChoices.choices, default=AccountTypeChoices.SANDBOX, help_text="Execution Mode")
    date = models.DateField(db_index=True, help_text="Calendar trading date")
    opening_balance = models.DecimalField(max_digits=12, decimal_places=2, default=100000.00, help_text="Starting day balance")
    closing_balance = models.DecimalField(max_digits=12, decimal_places=2, default=100000.00, help_text="Ending day balance")
    gross_pnl = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, help_text="Gross trading PnL")
    net_pnl = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, help_text="Net PnL after charges")
    realized_pnl = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, help_text="Realized PnL")
    unrealized_pnl = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, help_text="Open positions PnL")
    total_charges = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, help_text="Brokerage and regulatory charges")
    margin_utilized = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, help_text="Peak margin utilized during day")
    total_trades = models.PositiveIntegerField(default=0, help_text="Total trades executed")
    winning_trades = models.PositiveIntegerField(default=0, help_text="Winning trade count")
    losing_trades = models.PositiveIntegerField(default=0, help_text="Losing trade count")
    telemetry_snapshot = models.JSONField(default=dict, blank=True, help_text="Full day-end telemetry JSON snapshot")

    class Meta:
        verbose_name = "Daily Portfolio Snapshot"
        verbose_name_plural = "Daily Portfolio Snapshots"
        ordering = ['-date', '-id']
        constraints = [
            models.UniqueConstraint(fields=['user', 'trading_account', 'date'], name='unique_user_account_daily_snapshot')
        ]

    def __str__(self):
        return f"{self.user.username} - {self.trading_account.account_name} ({self.date}): PnL ₹{self.net_pnl}"