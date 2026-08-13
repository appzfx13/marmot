from django.db import models
from apps.common.models import BaseModel
from apps.common.choices import TaskStatusChoices, IndexChoices, StrategyChoices
from apps.common.constants import MAX_LOG_LINES

class BacktestTask(BaseModel):
    StrategyChoices = StrategyChoices
    StatusChoices = TaskStatusChoices
    IndexChoices = IndexChoices

    # Optional Pre-Downloaded Backup Dataset Selection
    backup_task = models.ForeignKey('market.MarketBackupTask', on_delete=models.SET_NULL, null=True, blank=True, related_name='backtests', help_text="Optional selected backup dataset")

    # Strategy Input Configuration
    strategy_name = models.CharField(max_length=50, choices=StrategyChoices.choices, default=StrategyChoices.ICT_SMC)
    index_name = models.CharField(max_length=50, choices=IndexChoices.choices, default=IndexChoices.NIFTY)
    start_date = models.DateField()
    end_date = models.DateField()
    initial_capital = models.FloatField(default=100000.0, help_text="Starting capital in INR")
    parameters = models.JSONField(default=dict, blank=True, help_text="Strategy-specific custom parameters")

    # Execution State
    status = models.CharField(max_length=20, choices=StatusChoices.choices, default=StatusChoices.CREATED)
    progress = models.PositiveIntegerField(default=0)

    # Hybrid Output Storage (JSONB Summary KPIs + Parquet Trade Logs)
    metrics = models.JSONField(default=dict, blank=True, help_text="Summary KPIs: Net PnL, Win Rate, Max Drawdown, Sharpe Ratio")
    result_file_path = models.CharField(max_length=500, blank=True, null=True, help_text="Path to detailed trade logs parquet file")
    error_logs = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Backtest Task"
        verbose_name_plural = "Backtest Tasks"

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
