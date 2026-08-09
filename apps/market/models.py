from django.db import models
from django.utils import timezone
from apps.common.models import BaseModel, SoftDeleteUserModelManager

class MarketBackupTask(BaseModel):
    class StatusChoices(models.TextChoices):
        CREATED = 'created', 'Created'
        PENDING = 'pending', 'Pending'
        RUNNING = 'running', 'Running'
        PAUSED = 'paused', 'Paused'
        CANCELLED = 'cancelled', 'Cancelled'
        COMPLETED = 'completed', 'Completed'
        ERROR = 'error', 'Error'

    class IndexChoices(models.TextChoices):
        NIFTY = 'NIFTY', 'Nifty 50'
        BANKNIFTY = 'BANKNIFTY', 'Bank Nifty'
        FINNIFTY = 'FINNIFTY', 'Fin Nifty'
        MIDCPNIFTY = 'MIDCPNIFTY', 'Midcp Nifty'

    # 1. User Input Parameters
    start_date = models.DateField(help_text="Start date for options data range")
    end_date = models.DateField(help_text="End date for options data range")
    index_name = models.CharField(max_length=50, choices=IndexChoices.choices, default=IndexChoices.NIFTY, help_text="Target trading index")
    strike_count = models.PositiveIntegerField(default=5, help_text="Number of strikes above/below ATM")

    # 2. Control & Progress State (Tracked by Go Engine & Django UI)
    status = models.CharField(max_length=20, choices=StatusChoices.choices, default=StatusChoices.CREATED)
    progress = models.PositiveIntegerField(default=0, help_text="Execution progress percentage from 0 to 100")
    
    # 3. Output & Error Storage Details
    parquet_file_path = models.CharField(max_length=500, blank=True, null=True, help_text="Local path to the saved Parquet files") 
    file_size_mb = models.FloatField(default=0.0, help_text="Generated Parquet storage size in MB")
    error_logs = models.TextField(blank=True, null=True, help_text="Timestamped trace and error messages if the job fails")

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Market Backup Task"
        verbose_name_plural = "Market Backup Tasks"

    def get_last_200_logs(self):
        """Returns the last 200 lines of error and trace logs for UI rendering."""
        if not self.error_logs:
            return ""
        lines = self.error_logs.strip().splitlines()
        if len(lines) > 200:
            lines = lines[-200:]
        return "\n".join(lines)

    def __str__(self):
        return f"Backup #{self.id} | {self.index_name} ({self.start_date} to {self.end_date}) - [{self.status.upper()}]"