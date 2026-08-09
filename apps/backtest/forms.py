from django import forms
from .models import BacktestTask
from apps.market.models import MarketBackupTask

class BacktestTaskForm(forms.ModelForm):
    backup_task = forms.ModelChoiceField(
        queryset=MarketBackupTask.objects.filter(is_deleted=False),
        required=False,
        empty_label="-- Select Existing Backup File (Optional) --",
        widget=forms.Select(attrs={'class': 'form-select bg-transparent theme-text-main border-secondary border-opacity-25', 'id': 'id_backup_task'})
    )
    risk_reward_ratio = forms.FloatField(initial=2.0, required=False, help_text="Risk to Reward Ratio (e.g. 2.0)")
    stop_loss_pct = forms.FloatField(initial=0.5, required=False, help_text="Stop Loss Percentage (e.g. 0.5%)")

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
