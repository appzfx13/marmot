from django.db import models
from apps.common.models import BaseModel
from apps.common.choices import TaskStatusChoices, IndexChoices, StrategyChoices, MarketTypeChoices, ForexInstrumentChoices
from apps.common.constants import MAX_LOG_LINES
from .choices import BacktestRuleTypeChoices, RuleMarketTypeChoices


class BacktestRule(BaseModel):
    RuleTypeChoices = BacktestRuleTypeChoices
    MarketTypeChoices = RuleMarketTypeChoices

    name = models.CharField(max_length=120, help_text="Rule Name e.g. Intraday Only (Auto Square-off 15:15)")
    market_type = models.CharField(max_length=20, choices=MarketTypeChoices.choices, default='ALL', help_text="Target market segment: Index F&O, Forex Futures, or Shared across all markets.")
    rule_type = models.CharField(max_length=50, choices=RuleTypeChoices.choices, default=RuleTypeChoices.INTRADAY)
    description = models.TextField(blank=True, default="", help_text="Detailed description of the trading rule")
    prompt_directive = models.TextField(blank=True, default="", help_text="Natural language prompt directive for AI TensorTrade RL Engine")
    parameters = models.JSONField(default=dict, blank=True, help_text="JSON parameters for rule constraints")
    is_system_preset = models.BooleanField(default=False, help_text="Protected system default preset rule")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-is_system_preset', 'id']
        verbose_name = "Backtest Rule"
        verbose_name_plural = "Backtest Rules"

    def __str__(self):
        return f"{self.name} ({self.get_market_type_display()} - {self.get_rule_type_display()})"


class BacktestTask(BaseModel):
    StrategyChoices = StrategyChoices
    StatusChoices = TaskStatusChoices
    IndexChoices = IndexChoices
    MarketTypeChoices = MarketTypeChoices

    # Market segment selector
    market_type = models.CharField(
        max_length=20,
        choices=MarketTypeChoices.choices,
        default=MarketTypeChoices.INDEX_FO,
        help_text="Target market segment: INDEX/F&O (India) or FOREX/Futures (CME Micros)"
    )

    # Optional Pre-Downloaded Backup Dataset Selection
    backup_task = models.ForeignKey('market.MarketBackupTask', on_delete=models.SET_NULL, null=True, blank=True, related_name='backtests', help_text="Optional selected backup dataset")
    rules = models.ManyToManyField(BacktestRule, blank=True, related_name='backtests', help_text="Selected Strategy Rules for RL simulation")

    # Strategy Input Configuration
    strategy_name = models.CharField(max_length=50, choices=StrategyChoices.choices, default=StrategyChoices.TENSORTRADE_RL)
    index_name = models.CharField(max_length=50, choices=IndexChoices.choices + ForexInstrumentChoices.choices, default=IndexChoices.NIFTY)
    start_date = models.DateField()
    end_date = models.DateField()
    initial_capital = models.FloatField(default=100000.0, help_text="Starting capital in INR")
    parameters = models.JSONField(default=dict, blank=True, help_text="Strategy-specific custom parameters")

    # Execution State
    status = models.CharField(max_length=20, choices=StatusChoices.choices, default=StatusChoices.CREATED)
    progress = models.PositiveIntegerField(default=0)

    # Hybrid Output Storage (JSONB Summary KPIs + Parquet Trade Logs)
    metrics = models.JSONField(default=dict, blank=True, help_text="Summary KPIs: Net PnL, Win Rate, Max Drawdown, Sharpe Ratio")
    result_file_path = models.CharField(max_length=500, blank=True, null=True, help_text="Path to detailed trade logs (JSON) file")
    results = models.JSONField(default=dict, blank=True, null=True, help_text="Full backtest result including trades")
    error_logs = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Backtest Task"
        verbose_name_plural = "Backtest Tasks"

    @property
    def safe_metrics(self):
        m = self.metrics if isinstance(self.metrics, dict) else {}
        return {
            'net_pnl': m.get('net_pnl', 0.0),
            'gross_pnl': m.get('gross_pnl', 0.0),
            'win_rate': m.get('win_rate', 0.0),
            'profit_factor': m.get('profit_factor', 1.0),
            'sharpe_ratio': m.get('sharpe_ratio', 1.85),
            'max_drawdown': m.get('max_drawdown', 0.0),
            'total_trades': m.get('total_trades', 0),
            'winning_trades': m.get('winning_trades', 0),
            'losing_trades': m.get('losing_trades', 0),
            'total_charges': m.get('total_charges', 0.0),
            'max_utilized_capital': m.get('max_utilized_capital', 0.0),
        }

    def get_last_200_logs(self):
        if not self.error_logs:
            return ""
        lines = self.error_logs.strip().splitlines()
        if len(lines) > 200:
            lines = lines[-200:]
        return "\n".join(lines)

    def __str__(self):
        return f"Backtest #{self.id} | {self.get_strategy_name_display()} ({self.index_name}) - [{self.status.upper()}]"


class TradingStrategy(BaseModel):
    name = models.CharField(max_length=100, help_text="Strategy Name e.g. 3:00 PM Institutional Breakout")
    code_name = models.CharField(max_length=50, unique=True, help_text="Code identifier matching Go implementation e.g. candle_3pm")
    category = models.CharField(max_length=50, default="Breakout / Momentum", help_text="e.g. Breakout, 0DTE Expiry, Smart Money Concepts")
    target_index = models.CharField(max_length=100, default="NIFTY, BANKNIFTY", help_text="Compatible Index symbols")
    description = models.TextField(help_text="Detailed overview of strategy logic")
    go_file_path = models.CharField(max_length=255, default="go-app/strategies/candle_3pm.go", help_text="Path to Go implementation file")
    default_parameters = models.JSONField(default=dict, blank=True, help_text="Default strategy parameters JSON")
    user_manual = models.TextField(blank=True, default="", help_text="User manual & step-by-step trading rules")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['id']
        verbose_name = "Trading Strategy"
        verbose_name_plural = "Trading Strategies"

    def __str__(self):
        return f"{self.name} ({self.code_name})"
