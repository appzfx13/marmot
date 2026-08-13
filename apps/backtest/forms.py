from django import forms
from .models import BacktestTask
from apps.market.models import MarketBackupTask

from apps.common.choices import StrikeSelectionChoices

class BacktestTaskForm(forms.ModelForm):
    backup_task = forms.ModelChoiceField(
        queryset=MarketBackupTask.objects.filter(is_deleted=False),
        required=False,
        empty_label="-- Select Existing Backup File (Optional) --",
        widget=forms.Select(attrs={'class': 'form-select bg-transparent theme-text-main border-secondary border-opacity-25', 'id': 'id_backup_task'})
    )
    strike_selection = forms.ChoiceField(
        choices=StrikeSelectionChoices.choices,
        initial=StrikeSelectionChoices.ATM,
        required=False,
        help_text="Target Option Strike (ATM, ITM +/- 1/2, OTM +/- 1/2)",
        widget=forms.Select(attrs={'class': 'form-select bg-transparent theme-text-main border-secondary border-opacity-25', 'id': 'id_strike_selection'})
    )
    risk_reward_ratio = forms.FloatField(initial=2.0, required=False, help_text="Risk to Reward Ratio (e.g. 2.0)")
    stop_loss_pct = forms.FloatField(initial=0.5, required=False, help_text="Stop Loss Percentage (e.g. 0.5%)")
    lots_count = forms.IntegerField(initial=1, min_value=1, required=False, help_text="Number of Lots to trade (e.g. 1, 2, 5, 10)", widget=forms.NumberInput(attrs={'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25', 'min': '1'}))

    class Meta:
        model = BacktestTask
        fields = ['backup_task', 'strategy_name', 'index_name', 'start_date', 'end_date', 'initial_capital']
        widgets = {
            'strategy_name': forms.Select(attrs={'class': 'form-select bg-transparent theme-text-main border-secondary border-opacity-25'}),
            'index_name': forms.Select(attrs={'class': 'form-select bg-transparent theme-text-main border-secondary border-opacity-25', 'id': 'id_index_name'}),
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25', 'id': 'id_start_date'}),
            'end_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25', 'id': 'id_end_date'}),
            'initial_capital': forms.NumberInput(attrs={'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25', 'step': '1000'}),
        }
