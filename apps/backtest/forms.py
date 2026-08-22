from django import forms
import json
from .models import BacktestTask, BacktestRule
from apps.market.models import MarketBackupTask
from apps.common.choices import StrikeSelectionChoices


class BacktestRuleForm(forms.ModelForm):
    parameters_json = forms.CharField(
        required=False,
        label="Rule Parameters (JSON)",
        help_text="Optional JSON dictionary of rule parameters (e.g. {'cutoff_time': '15:15'})",
        widget=forms.Textarea(attrs={'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25 font-monospace small', 'rows': 3, 'placeholder': '{"start_time": "09:20", "end_time": "10:30"}'})
    )

    class Meta:
        model = BacktestRule
        fields = ['name', 'rule_type', 'description', 'prompt_directive', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25', 'placeholder': 'e.g. 3:00 PM Institutional Breakout'}),
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


class BacktestTaskForm(forms.ModelForm):
    backup_task = forms.ModelChoiceField(
        queryset=MarketBackupTask.objects.filter(is_deleted=False),
        required=False,
        empty_label="-- Select Existing Backup File (Optional) --",
        widget=forms.Select(attrs={'class': 'form-select bg-transparent theme-text-main border-secondary border-opacity-25', 'id': 'id_backup_task'})
    )
    rules = forms.ModelMultipleChoiceField(
        queryset=BacktestRule.objects.filter(is_active=True),
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input rule-checkbox'}),
        help_text="Select one or more active strategy rules for constraint-conditioned RL."
    )
    prompt_directives = forms.CharField(
        required=False,
        label="AI Strategy Directives Prompt",
        help_text="Natural language strategy instructions to inject directly into TensorTrade RL environment.",
        widget=forms.Textarea(attrs={'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25', 'rows': 2, 'placeholder': 'e.g. Only take CE trades when index crosses yesterday\'s high, maximum 3 trades per day...'})
    )
    strike_selection = forms.ChoiceField(
        choices=StrikeSelectionChoices.choices,
        initial=StrikeSelectionChoices.ATM,
        required=False,
        help_text="Target Option Strike (ATM, ITM +/- 1/2, OTM +/- 1/2)",
        widget=forms.Select(attrs={'class': 'form-select bg-transparent theme-text-main border-secondary border-opacity-25', 'id': 'id_strike_selection'})
    )
    risk_reward_ratio = forms.FloatField(initial=2.0, required=False, help_text="Risk to Reward Ratio (e.g. 2.0)")
    stop_loss_points = forms.FloatField(initial=30.0, required=False, help_text="Stop Loss in Points (e.g. 30 pts)", widget=forms.NumberInput(attrs={'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25', 'id': 'id_stop_loss_points', 'step': '0.5'}))
    lots_count = forms.IntegerField(initial=1, min_value=1, required=False, help_text="Number of Lots to trade (e.g. 1, 2, 5, 10)", widget=forms.NumberInput(attrs={'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25', 'min': '1'}))

    class Meta:
        model = BacktestTask
        fields = ['backup_task', 'strategy_name', 'index_name', 'start_date', 'end_date', 'initial_capital', 'rules']
        widgets = {
            'strategy_name': forms.Select(attrs={'class': 'form-select bg-transparent theme-text-main border-secondary border-opacity-25'}),
            'index_name': forms.Select(attrs={'class': 'form-select bg-transparent theme-text-main border-secondary border-opacity-25', 'id': 'id_index_name'}),
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25', 'id': 'id_start_date'}),
            'end_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25', 'id': 'id_end_date'}),
            'initial_capital': forms.NumberInput(attrs={'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25', 'step': '1000'}),
        }

