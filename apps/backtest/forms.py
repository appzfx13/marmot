from django import forms
import json
from .models import BacktestTask
from apps.market.models import MarketBackupTask
from apps.common.choices import IndexChoices, ForexInstrumentChoices, MarketTypeChoices, MacroTimeframeChoices, CompoundingProfileChoices


class BackupTaskSelectWidget(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)
        instance = getattr(value, 'instance', None)
        if instance:
            asset_code = getattr(instance, 'asset_code', None) or getattr(instance, 'index_name', None)
            if asset_code:
                option['attrs']['data-index'] = asset_code
            market_type = getattr(instance, 'market_type', 'INDEX_FO')
            option['attrs']['data-market-type'] = market_type
            if getattr(instance, 'start_date', None):
                option['attrs']['data-start-date'] = instance.start_date.strftime('%Y-%m-%d')
            if getattr(instance, 'end_date', None):
                option['attrs']['data-end-date'] = instance.end_date.strftime('%Y-%m-%d')
        return option


class MarketBackupTaskChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        size_info = f" ({obj.file_size_mb:.1f} MB)" if obj.file_size_mb > 0 else ""
        return f"#{obj.id:04d} · {obj.display_symbol} ({obj.start_date} → {obj.end_date}) — [{obj.status.upper()}]{size_info}"


class IndexBacktestTaskForm(forms.ModelForm):
    """Form dedicated to Indian Index & Option (F&O) Backtesting."""
    market_type = forms.CharField(initial=MarketTypeChoices.INDEX_FO, widget=forms.HiddenInput())
    backup_task = MarketBackupTaskChoiceField(
        queryset=MarketBackupTask.objects.filter(is_deleted=False, market_type='INDEX_FO', is_macro_assist=False).order_by('-id'),
        required=False,
        empty_label="-- Select Existing Index Backup Dataset (Optional) --",
        widget=BackupTaskSelectWidget(attrs={'class': 'form-select bg-transparent theme-text-main border-secondary border-opacity-25', 'id': 'id_index_backup_task'})
    )
    index_name = forms.ChoiceField(
        choices=IndexChoices.choices,
        required=True,
        widget=forms.Select(attrs={'class': 'form-select bg-transparent theme-text-main border-secondary border-opacity-25', 'id': 'id_index_index_name'})
    )
    risk_reward_ratio = forms.FloatField(initial=2.0, required=False, help_text="Risk to Reward Ratio (e.g. 2.0)")
    stop_loss_points = forms.FloatField(initial=30.0, required=False, help_text="Stop Loss in Index/Option Points (e.g. 30 pts)", widget=forms.NumberInput(attrs={'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25', 'id': 'id_index_stop_loss_points', 'step': '0.5'}))
    lots_count = forms.IntegerField(initial=1, min_value=1, required=False, help_text="Number of option lots (e.g. 1, 2, 5)", widget=forms.NumberInput(attrs={'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25', 'min': '1'}))
    class Meta:
        model = BacktestTask
        fields = ['market_type', 'backup_task', 'strategy_name', 'index_name', 'start_date', 'end_date', 'initial_capital']
        widgets = {
            'strategy_name': forms.Select(attrs={'class': 'form-select bg-transparent theme-text-main border-secondary border-opacity-25', 'id': 'id_index_strategy_name'}),
            'index_name': forms.Select(attrs={'class': 'form-select bg-transparent theme-text-main border-secondary border-opacity-25', 'id': 'id_index_index_name'}),
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25', 'id': 'id_index_start_date'}),
            'end_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25', 'id': 'id_index_end_date'}),
            'initial_capital': forms.NumberInput(attrs={'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25', 'step': '1000'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import TradingStrategy
        strategies = list(TradingStrategy.objects.filter(is_deleted=False).order_by('id'))
        if strategies:
            self.fields['strategy_name'].choices = [(s.code_name, s.name) for s in strategies]


class ForexBacktestTaskForm(forms.ModelForm):
    """Form dedicated to Forex & CME Micro Futures Backtesting (NO strike_selection)."""
    market_type = forms.CharField(initial=MarketTypeChoices.FOREX_FUTURES, widget=forms.HiddenInput())
    backup_task = MarketBackupTaskChoiceField(
        queryset=MarketBackupTask.objects.filter(is_deleted=False, market_type='FOREX_FUTURES', is_macro_assist=False).order_by('-id'),
        required=False,
        empty_label="-- Select Existing Databento Forex Backup Dataset (Optional) --",
        widget=BackupTaskSelectWidget(attrs={'class': 'form-select bg-transparent theme-text-main border-secondary border-opacity-25', 'id': 'id_forex_backup_task'})
    )
    index_name = forms.ChoiceField(
        choices=ForexInstrumentChoices.choices,
        required=True,
        label="CME Futures Asset",
        widget=forms.Select(attrs={'class': 'form-select bg-transparent theme-text-main border-secondary border-opacity-25', 'id': 'id_forex_index_name'})
    )
    risk_reward_ratio = forms.FloatField(initial=2.0, required=False, help_text="Risk to Reward Ratio (e.g. 2.0)")
    stop_loss_points = forms.FloatField(initial=25.0, required=False, help_text="Stop Loss in Pips or Ticks (e.g. 25 pips)", widget=forms.NumberInput(attrs={'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25', 'id': 'id_forex_stop_loss_points', 'step': '0.1'}))
    lots_count = forms.IntegerField(initial=1, min_value=1, required=False, help_text="Number of CME Micro Contracts / Lots (e.g. 1, 2, 5)", widget=forms.NumberInput(attrs={'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25', 'min': '1'}))
    class Meta:
        model = BacktestTask
        fields = ['market_type', 'backup_task', 'strategy_name', 'index_name', 'start_date', 'end_date', 'initial_capital']
        widgets = {
            'strategy_name': forms.Select(attrs={'class': 'form-select bg-transparent theme-text-main border-secondary border-opacity-25', 'id': 'id_forex_strategy_name'}),
            'index_name': forms.Select(attrs={'class': 'form-select bg-transparent theme-text-main border-secondary border-opacity-25', 'id': 'id_forex_index_name'}),
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25', 'id': 'id_forex_start_date'}),
            'end_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25', 'id': 'id_forex_end_date'}),
            'initial_capital': forms.NumberInput(attrs={'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25', 'step': '100'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import TradingStrategy
        strategies = list(TradingStrategy.objects.filter(is_deleted=False).order_by('id'))
        if strategies:
            self.fields['strategy_name'].choices = [(s.code_name, s.name) for s in strategies]



# Backward compatibility alias
BacktestTaskForm = IndexBacktestTaskForm

