from django import forms

from apps.common.choices import AccountTypeChoices, ForexInstrumentChoices, MarketTypeChoices, RiskTypeChoices
from .models import BrokerMaster, TradeExecConfig, UserTradingAccount

_FIELD_CSS  = 'form-control theme-text-main'
_SELECT_CSS = 'form-select theme-text-main'
_CHECK_CSS  = 'form-check-input'


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
            'broker':           forms.Select(attrs={'class': _SELECT_CSS}),
            'account_name':     forms.TextInput(attrs={'class': _FIELD_CSS, 'placeholder': 'Account Nickname (e.g. Dhan Live Primary)'}),
            'account_type':     forms.Select(attrs={'class': _SELECT_CSS}),
            'broker_client_id': forms.TextInput(attrs={'class': _FIELD_CSS, 'placeholder': 'Client ID'}),
            'api_key':          forms.TextInput(attrs={'class': _FIELD_CSS, 'placeholder': 'API Key'}),
            'app_id':           forms.TextInput(attrs={'class': _FIELD_CSS, 'placeholder': 'App ID / Secret'}),
            'is_default':       forms.CheckboxInput(attrs={'class': _CHECK_CSS}),
            'is_active':        forms.CheckboxInput(attrs={'class': _CHECK_CSS}),
        }


class TradeExecConfigForm(forms.ModelForm):
    class Meta:
        model = TradeExecConfig
        fields = [
            # ── General ──────────────────────────────────────────────────────
            'name',
            'admins_user',
            'trading_account',
            'account_type',
            'is_active',
            # ── Market Type selector ─────────────────────────────────────────
            'market_type',
            # ── Risk Controls (shared across both market types) ───────────────
            'max_loss_status',
            'max_loss_type',
            'max_loss_limit',
            'max_loss_percentage',
            'max_loss_reference',
            'max_profit_status',
            'max_profit_limit',
            # ── Forex / CME Futures (shown only for FOREX_FUTURES) ───────────
            'forex_instrument',
            'forex_broker_api_key',
            'forex_account_id',
            'forex_contract_size',
            'forex_tick_value',
            'forex_max_contracts',
        ]
        widgets = {
            # General
            'name':                 forms.TextInput(attrs={'class': _FIELD_CSS, 'placeholder': 'Strategy / Config Name'}),
            'admins_user':          forms.Select(attrs={'class': _SELECT_CSS, 'id': 'id_admins_user'}),
            'trading_account':      forms.HiddenInput(attrs={'id': 'id_trading_account'}),
            'account_type':         forms.HiddenInput(attrs={'id': 'id_account_type'}),
            'is_active':            forms.CheckboxInput(attrs={'class': _CHECK_CSS, 'role': 'switch', 'id': 'id_is_active'}),
            # Market Type
            'market_type':          forms.Select(attrs={'class': _SELECT_CSS, 'id': 'id_market_type'}),
            # Risk
            'max_loss_status':      forms.CheckboxInput(attrs={'class': _CHECK_CSS, 'role': 'switch', 'id': 'id_max_loss_status'}),
            'max_loss_type':        forms.Select(attrs={'class': _SELECT_CSS, 'id': 'id_max_loss_type'}),
            'max_loss_limit':       forms.NumberInput(attrs={'class': _FIELD_CSS, 'step': '500', 'placeholder': 'e.g. 5000.00', 'id': 'id_max_loss_limit'}),
            'max_loss_percentage':  forms.NumberInput(attrs={'class': _FIELD_CSS, 'step': '0.1', 'min': '0.1', 'max': '100', 'placeholder': 'e.g. 2.50', 'id': 'id_max_loss_percentage'}),
            'max_loss_reference':   forms.Select(attrs={'class': _SELECT_CSS, 'id': 'id_max_loss_reference'}),
            'max_profit_status':    forms.CheckboxInput(attrs={'class': _CHECK_CSS, 'role': 'switch', 'id': 'id_max_profit_status'}),
            'max_profit_limit':     forms.NumberInput(attrs={'class': _FIELD_CSS, 'step': '500', 'placeholder': 'e.g. 10000.00', 'id': 'id_max_profit_limit'}),
            # Forex / CME
            'forex_instrument':     forms.Select(attrs={'class': _SELECT_CSS}),
            'forex_broker_api_key': forms.TextInput(attrs={'class': _FIELD_CSS, 'placeholder': 'Rithmic / OANDA API Key'}),
            'forex_account_id':     forms.TextInput(attrs={'class': _FIELD_CSS, 'placeholder': 'Broker Account ID'}),
            'forex_contract_size':  forms.NumberInput(attrs={'class': _FIELD_CSS, 'step': '0.0001', 'placeholder': 'e.g. 10 for MGC'}),
            'forex_tick_value':     forms.NumberInput(attrs={'class': _FIELD_CSS, 'step': '0.0001', 'placeholder': 'e.g. 1.00 for MGC'}),
            'forex_max_contracts':  forms.NumberInput(attrs={'class': _FIELD_CSS, 'min': '1', 'placeholder': 'Max contracts per trade'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['account_type'].required = False
        self.fields['trading_account'].required = False
        self.fields['max_loss_limit'].required = False
        self.fields['max_loss_percentage'].required = False
        self.fields['max_loss_reference'].required = False
        self.fields['max_profit_limit'].required = False
        self.fields['forex_contract_size'].required = False
        self.fields['forex_tick_value'].required = False
        self.fields['forex_max_contracts'].required = False

    def clean(self):
        cleaned_data = super().clean()
        max_loss_status = cleaned_data.get('max_loss_status')
        max_loss_type = cleaned_data.get('max_loss_type')
        max_loss_limit = cleaned_data.get('max_loss_limit')
        max_loss_percentage = cleaned_data.get('max_loss_percentage')
        max_loss_reference = cleaned_data.get('max_loss_reference')

        if max_loss_status:
            if max_loss_type == 'AMOUNT':
                if max_loss_limit is None or max_loss_limit <= 0:
                    self.add_error('max_loss_limit', 'Max Loss Limit amount is required and must be greater than 0.')
            elif max_loss_type == 'PERCENTAGE':
                if max_loss_percentage is None or max_loss_percentage <= 0:
                    self.add_error('max_loss_percentage', 'Max Loss Percentage is required and must be greater than 0%.')
                if not max_loss_reference:
                    self.add_error('max_loss_reference', 'Capital reference method is required for percentage-based loss calculation.')

        max_profit_status = cleaned_data.get('max_profit_status')
        max_profit_limit = cleaned_data.get('max_profit_limit')
        if max_profit_status and (max_profit_limit is None or max_profit_limit <= 0):
            self.add_error('max_profit_limit', 'Max Profit Limit value is required and must be greater than 0.')

        return cleaned_data
