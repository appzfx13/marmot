from django import forms
from .models import TradeExecConfig, UserTradingAccount, BrokerMaster
from apps.common.choices import RiskTypeChoices, AccountTypeChoices

class UserTradingAccountForm(forms.ModelForm):
    class Meta:
        model = UserTradingAccount
        fields = [
            'broker',
            'account_name',
            'account_type',
            'broker_client_id',
            'api_key',
            'app_id',
            'is_default',
            'is_active',
        ]
        widgets = {
            'broker': forms.Select(attrs={'class': 'form-select bg-transparent theme-text-main border-secondary border-opacity-25'}),
            'account_name': forms.TextInput(attrs={'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25', 'placeholder': 'Account Nickname (e.g. Dhan Live Primary)'}),
            'account_type': forms.Select(attrs={'class': 'form-select bg-transparent theme-text-main border-secondary border-opacity-25'}),
            'broker_client_id': forms.TextInput(attrs={'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25', 'placeholder': 'Client ID'}),
            'api_key': forms.TextInput(attrs={'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25', 'placeholder': 'API Key'}),
            'app_id': forms.TextInput(attrs={'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25', 'placeholder': 'App ID / Secret'}),
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class TradeExecConfigForm(forms.ModelForm):
    class Meta:
        model = TradeExecConfig
        fields = [
            'name',
            'account_type',
            'is_active',
            'max_loss_limit',
            'max_profit_limit',
            'auto_lot_status',
            'default_lot_size',
            'auto_sl_status',
            'default_risk_value',
            'default_risk_type',
            'layer_status',
            'layer_add_in_lot_count',
            'layer_percentage',
            'forecast_status',
            'backtest_status',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25', 'placeholder': 'Strategy / Config Name'}),
            'account_type': forms.Select(attrs={'class': 'form-select bg-transparent theme-text-main border-secondary border-opacity-25'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'max_loss_limit': forms.NumberInput(attrs={'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25', 'step': '500'}),
            'max_profit_limit': forms.NumberInput(attrs={'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25', 'step': '500'}),
            'auto_lot_status': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'default_lot_size': forms.NumberInput(attrs={'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25', 'min': '1'}),
            'auto_sl_status': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'default_risk_value': forms.NumberInput(attrs={'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25', 'step': '0.1'}),
            'default_risk_type': forms.Select(attrs={'class': 'form-select bg-transparent theme-text-main border-secondary border-opacity-25'}),
            'layer_status': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'layer_add_in_lot_count': forms.NumberInput(attrs={'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25'}),
            'layer_percentage': forms.NumberInput(attrs={'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25', 'step': '0.1'}),
            'forecast_status': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'backtest_status': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
