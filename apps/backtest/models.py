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
