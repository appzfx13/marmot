from django import forms
import json
from .models import BacktestTask, BacktestRule
from apps.market.models import MarketBackupTask
from apps.common.choices import StrikeSelectionChoices, IndexChoices, ForexInstrumentChoices, MarketTypeChoices, MacroTimeframeChoices


class BacktestRuleForm(forms.ModelForm):
    parameters_json = forms.CharField(
        required=False,
        label="Rule Parameters (JSON)",
        help_text="Optional JSON dictionary of rule parameters (e.g. {'cutoff_time': '15:15'})",
        widget=forms.Textarea(attrs={'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25 font-monospace small', 'rows': 3, 'placeholder': '{"start_time": "09:20", "end_time": "10:30"}'})
    )

    class Meta:
        model = BacktestRule
        fields = ['name', 'market_type', 'rule_type', 'description', 'prompt_directive', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25', 'placeholder': 'e.g. 3:00 PM Institutional Breakout'}),
            'market_type': forms.Select(attrs={'class': 'form-select bg-transparent theme-text-main border-secondary border-opacity-25'}),
            'rule_type': forms.Select(attrs={'class': 'form-select bg-transparent theme-text-main border-secondary border-opacity-25'}),
            'description': forms.Textarea(attrs={'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25', 'rows': 2, 'placeholder': 'Describe rule logic & market conditions...'}),
            'prompt_directive': forms.Textarea(attrs={'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25', 'rows': 2, 'placeholder': 'Natural language prompt instruction for TensorTrade RL...'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.parameters:
            self.fields['parameters_json'].initial = json.dumps(self.instance.parameters, indent=2)

    def clean_parameters_json(self):
        raw = self.cleaned_data.get('parameters_json', '').strip()
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            raise forms.ValidationError(f"Invalid JSON format: {e}")

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.parameters = self.cleaned_data.get('parameters_json', {})
        if commit:
            instance.save()
        return instance


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


class RuleCheckboxSelectMultiple(forms.CheckboxSelectMultiple):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)
        instance = getattr(value, 'instance', None)
        if instance:
            option['attrs']['data-market-type'] = getattr(instance, 'market_type', 'ALL')
        return option


class MarketBackupTaskChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        size_info = f" ({obj.file_size_mb:.1f} MB)" if obj.file_size_mb > 0 else ""
        return f"#{obj.id:04d} · {obj.display_symbol} ({obj.start_date} → {obj.end_date}) — [{obj.status.upper()}]{size_info}"


class IndexBacktestTaskForm(forms.ModelForm):
    """Form dedicated to Indian Index & Option (F&O) Backtesting."""
    market_type = forms.CharField(initial=MarketTypeChoices.INDEX_FO, widget=forms.HiddenInput())
    backup_task = MarketBackupTaskChoiceField(
        queryset=MarketBackupTask.objects.filter(is_deleted=False, market_type='INDEX_FO').order_by('-id'),
        required=False,
        empty_label="-- Select Existing Index Backup Dataset (Optional) --",
        widget=BackupTaskSelectWidget(attrs={'class': 'form-select bg-transparent theme-text-main border-secondary border-opacity-25', 'id': 'id_index_backup_task'})
    )
    index_name = forms.ChoiceField(
        choices=IndexChoices.choices,
        required=True,
        widget=forms.Select(attrs={'class': 'form-select bg-transparent theme-text-main border-secondary border-opacity-25', 'id': 'id_index_index_name'})
    )
    rules = forms.ModelMultipleChoiceField(
        queryset=BacktestRule.objects.filter(is_active=True, is_deleted=False, market_type__in=['INDEX_FO', 'ALL']),
        required=False,
        widget=RuleCheckboxSelectMultiple(attrs={'class': 'form-check-input rule-checkbox'}),
        help_text="Select active Index F&O & Shared strategy rules."
    )
    prompt_directives = forms.CharField(
        required=False,
        label="AI Strategy Directives Prompt",
        widget=forms.Textarea(attrs={'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25', 'rows': 2, 'placeholder': 'e.g. Only take CE trades when index crosses yesterday\'s high...'})
    )
    strike_selection = forms.ChoiceField(
        choices=StrikeSelectionChoices.choices,
        initial=StrikeSelectionChoices.ATM,
        required=False,
        help_text="Target Option Strike (ATM, ITM +/- 1/2, OTM +/- 1/2)",
        widget=forms.Select(attrs={'class': 'form-select bg-transparent theme-text-main border-secondary border-opacity-25', 'id': 'id_index_strike_selection'})
    )
    risk_reward_ratio = forms.FloatField(initial=2.0, required=False, help_text="Risk to Reward Ratio (e.g. 2.0)")
    stop_loss_points = forms.FloatField(initial=30.0, required=False, help_text="Stop Loss in Index/Option Points (e.g. 30 pts)", widget=forms.NumberInput(attrs={'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25', 'id': 'id_index_stop_loss_points', 'step': '0.5'}))
    lots_count = forms.IntegerField(initial=1, min_value=1, required=False, help_text="Number of option lots (e.g. 1, 2, 5)", widget=forms.NumberInput(attrs={'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25', 'min': '1'}))
    use_macro_assist = forms.BooleanField(required=False, initial=False, label="USE AI MACRO ASSIST", widget=forms.CheckboxInput(attrs={'class': 'form-check-input', 'id': 'id_index_use_macro_assist'}))
    macro_timeframe = forms.ChoiceField(choices=MacroTimeframeChoices.choices, initial=MacroTimeframeChoices.H1, required=False, widget=forms.Select(attrs={'class': 'form-select bg-transparent theme-text-main border-secondary border-opacity-25', 'id': 'id_index_macro_timeframe'}))
    macro_backup_task = MarketBackupTaskChoiceField(queryset=MarketBackupTask.objects.filter(is_deleted=False, is_macro_assist=True).order_by('-id'), required=False, empty_label="-- Auto-Detect / Select Macro Parquet Dataset (Optional) --", widget=BackupTaskSelectWidget(attrs={'class': 'form-select bg-transparent theme-text-main border-secondary border-opacity-25', 'id': 'id_index_macro_backup_task'}))

    class Meta:
        model = BacktestTask
        fields = ['market_type', 'backup_task', 'macro_backup_task', 'use_macro_assist', 'macro_timeframe', 'strategy_name', 'index_name', 'start_date', 'end_date', 'initial_capital', 'rules']
        widgets = {
            'strategy_name': forms.Select(attrs={'class': 'form-select bg-transparent theme-text-main border-secondary border-opacity-25'}),
            'index_name': forms.Select(attrs={'class': 'form-select bg-transparent theme-text-main border-secondary border-opacity-25', 'id': 'id_index_index_name'}),
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25', 'id': 'id_index_start_date'}),
            'end_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25', 'id': 'id_index_end_date'}),
            'initial_capital': forms.NumberInput(attrs={'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25', 'step': '1000'}),
        }


class ForexBacktestTaskForm(forms.ModelForm):
    """Form dedicated to Forex & CME Micro Futures Backtesting (NO strike_selection)."""
    market_type = forms.CharField(initial=MarketTypeChoices.FOREX_FUTURES, widget=forms.HiddenInput())
    backup_task = MarketBackupTaskChoiceField(
        queryset=MarketBackupTask.objects.filter(is_deleted=False, market_type='FOREX_FUTURES').order_by('-id'),
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
    rules = forms.ModelMultipleChoiceField(
        queryset=BacktestRule.objects.filter(is_active=True, is_deleted=False, market_type__in=['FOREX_FUTURES', 'ALL']),
        required=False,
        widget=RuleCheckboxSelectMultiple(attrs={'class': 'form-check-input rule-checkbox'}),
        help_text="Select active Forex Order Flow & Shared strategy rules."
    )
    prompt_directives = forms.CharField(
        required=False,
        label="AI Order Flow Directives Prompt",
        widget=forms.Textarea(attrs={'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25', 'rows': 2, 'placeholder': 'e.g. Only enter long when CVD sweeps support with net positive delta...'})
    )
    risk_reward_ratio = forms.FloatField(initial=2.0, required=False, help_text="Risk to Reward Ratio (e.g. 2.0)")
    stop_loss_points = forms.FloatField(initial=25.0, required=False, help_text="Stop Loss in Pips or Ticks (e.g. 25 pips)", widget=forms.NumberInput(attrs={'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25', 'id': 'id_forex_stop_loss_points', 'step': '0.1'}))
    lots_count = forms.IntegerField(initial=1, min_value=1, required=False, help_text="Number of CME Micro Contracts / Lots (e.g. 1, 2, 5)", widget=forms.NumberInput(attrs={'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25', 'min': '1'}))
    use_macro_assist = forms.BooleanField(required=False, initial=False, label="USE AI MACRO ASSIST", widget=forms.CheckboxInput(attrs={'class': 'form-check-input', 'id': 'id_forex_use_macro_assist'}))
    macro_timeframe = forms.ChoiceField(choices=MacroTimeframeChoices.choices, initial=MacroTimeframeChoices.H1, required=False, widget=forms.Select(attrs={'class': 'form-select bg-transparent theme-text-main border-secondary border-opacity-25', 'id': 'id_forex_macro_timeframe'}))
    macro_backup_task = MarketBackupTaskChoiceField(queryset=MarketBackupTask.objects.filter(is_deleted=False, is_macro_assist=True).order_by('-id'), required=False, empty_label="-- Auto-Detect / Select Macro Parquet Dataset (Optional) --", widget=BackupTaskSelectWidget(attrs={'class': 'form-select bg-transparent theme-text-main border-secondary border-opacity-25', 'id': 'id_forex_macro_backup_task'}))

    class Meta:
        model = BacktestTask
        fields = ['market_type', 'backup_task', 'macro_backup_task', 'use_macro_assist', 'macro_timeframe', 'strategy_name', 'index_name', 'start_date', 'end_date', 'initial_capital', 'rules']
        widgets = {
            'strategy_name': forms.Select(attrs={'class': 'form-select bg-transparent theme-text-main border-secondary border-opacity-25'}),
            'index_name': forms.Select(attrs={'class': 'form-select bg-transparent theme-text-main border-secondary border-opacity-25', 'id': 'id_forex_index_name'}),
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25', 'id': 'id_forex_start_date'}),
            'end_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25', 'id': 'id_forex_end_date'}),
            'initial_capital': forms.NumberInput(attrs={'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25', 'step': '100'}),
        }


# Backward compatibility alias
BacktestTaskForm = IndexBacktestTaskForm

