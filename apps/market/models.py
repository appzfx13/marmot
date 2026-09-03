import os
import shutil
from django.conf import settings
from django.db import models
from apps.common.models import BaseModel
from apps.common.choices import TaskStatusChoices, IndexChoices, MarketTypeChoices, ForexInstrumentChoices, DatabentoSchemaChoices, MacroTimeframeChoices

class MarketBackupTask(BaseModel):
    StatusChoices = TaskStatusChoices
    IndexChoices = IndexChoices
    MarketTypeChoices = MarketTypeChoices
    ForexInstrumentChoices = ForexInstrumentChoices
    DatabentoSchemaChoices = DatabentoSchemaChoices
    MacroTimeframeChoices = MacroTimeframeChoices

    # 1. User Input Parameters
    start_date = models.DateField(help_text="Start date for options data range")
    end_date = models.DateField(help_text="End date for options data range")

    # Market segment selector (NEW) — defaults to INDEX_FO so all existing records are safe
    market_type = models.CharField(
        max_length=20,
        choices=MarketTypeChoices.choices,
        default=MarketTypeChoices.INDEX_FO,
        help_text="Market segment: INDEX/F&O (India) or FOREX/Futures (CME Micros)"
    )

    # INDEX / F&O fields (existing)
    index_name = models.CharField(max_length=50, choices=IndexChoices.choices, default=IndexChoices.NIFTY, null=True, blank=True, help_text="Target trading index (INDEX/F&O only)")
    strike_count = models.PositiveIntegerField(default=5, null=True, blank=True, help_text="Number of strikes above/below ATM (INDEX/F&O only)")

    # FOREX / CME Micro Futures fields (NEW — nullable)
    forex_instrument = models.CharField(max_length=10, choices=ForexInstrumentChoices.choices, null=True, blank=True, help_text="CME Micro Futures instrument to back up (FOREX/FUTURES only)")
    databento_schema = models.CharField(max_length=20, choices=DatabentoSchemaChoices.choices, default=DatabentoSchemaChoices.OHLCV_1M, null=True, blank=True, help_text="Databento Order Flow schema (FOREX/FUTURES only)")

    # AI Macro Assist Fields
    is_macro_assist = models.BooleanField(default=False, help_text="Designates this dataset as an AI Macro & Fundamental sentiment backup")
    macro_timeframe = models.CharField(max_length=10, choices=MacroTimeframeChoices.choices, default=MacroTimeframeChoices.H1, null=True, blank=True, help_text="Macro interval (default 1h)")
    linked_backup_task = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='macro_backups', help_text="Co-located market backup task")

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

    @property
    def display_symbol(self):
        """Returns readable asset symbol (e.g. Nifty 50 or XAUUSD / Gold -> MGC)."""
        if self.market_type == MarketTypeChoices.FOREX_FUTURES and self.forex_instrument:
            return self.get_forex_instrument_display()
        return self.get_index_name_display() if self.index_name else "INDEX/F&O"

    @property
    def asset_code(self):
        """Returns short asset code (e.g. NIFTY or MGC)."""
        if self.market_type == MarketTypeChoices.FOREX_FUTURES and self.forex_instrument:
            return self.forex_instrument
        return self.index_name or "INDEX"

    @property
    def provider_name(self):
        """Returns the market data provider (DhanHQ vs Databento)."""
        if self.market_type == MarketTypeChoices.FOREX_FUTURES:
            return "Databento"
        return "DhanHQ"

    def delete_dataset_files(self):
        """Removes task backup dataset folder from disk."""
        user_id = str(self.created_by.id if self.created_by else 1)
        backup_id = str(self.id)
        candidate_paths = [
            self.parquet_file_path,
            os.path.join(settings.BASE_DIR, 'backup', user_id, backup_id),
            os.path.join('/app', 'backup', user_id, backup_id),
        ]
        for p in candidate_paths:
            if p and os.path.exists(p):
                if os.path.isdir(p):
                    shutil.rmtree(p, ignore_errors=True)
                else:
                    try:
                        os.remove(p)
                    except OSError:
                        pass

    def delete(self, using=None, keep_parents=False):
        """Soft deletes task and purges dataset files on disk."""
        self.delete_dataset_files()
        super().delete(using=using, keep_parents=keep_parents)

    def hard_delete(self):
        """Permanently deletes task record and purges dataset files on disk."""
        self.delete_dataset_files()
        super().hard_delete()

    def get_last_200_logs(self):
        """Returns the last 200 lines of error and trace logs for UI rendering."""
        if not self.error_logs:
            return ""
        lines = self.error_logs.strip().splitlines()
        if len(lines) > 200:
            lines = lines[-200:]
        return "\n".join(lines)

    def __str__(self):
        asset = self.display_symbol if hasattr(self, 'display_symbol') else (self.index_name or self.forex_instrument or "DATASET")
        return f"Backup #{self.id:04d} · {asset} ({self.start_date} → {self.end_date}) — [{self.status.upper()}]"