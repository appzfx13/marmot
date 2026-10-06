from django import forms

from apps.common.choices import AccountTypeChoices, MarketTypeChoices
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
            # ── Two-Level Account Guardian Risk Controls ─────────────────────
            'max_loss_status',
            'primary_loss_status',
            'primary_loss_limit',
            'final_loss_status',
            'final_loss_limit',
            'max_profit_status',
            'max_profit_limit',
        ]
        widgets = {
            # General
            'name':                 forms.TextInput(attrs={'class': _FIELD_CSS, 'placeholder': 'Strategy / Risk Guardian Name'}),
            'admins_user':          forms.Select(attrs={'class': _SELECT_CSS, 'id': 'id_admins_user'}),
            'trading_account':      forms.HiddenInput(attrs={'id': 'id_trading_account'}),
            'account_type':         forms.HiddenInput(attrs={'id': 'id_account_type'}),
            'is_active':            forms.CheckboxInput(attrs={'class': _CHECK_CSS, 'role': 'switch', 'id': 'id_is_active'}),
            # Market Type
            'market_type':          forms.Select(attrs={'class': _SELECT_CSS, 'id': 'id_market_type'}),
            # Two-Level Account Guardian Risk Controls
            'max_loss_status':      forms.CheckboxInput(attrs={'class': _CHECK_CSS, 'role': 'switch', 'id': 'id_max_loss_status'}),
            'primary_loss_status':  forms.CheckboxInput(attrs={'class': _CHECK_CSS, 'role': 'switch', 'id': 'id_primary_loss_status'}),
            'primary_loss_limit':   forms.NumberInput(attrs={'class': _FIELD_CSS, 'step': '100', 'placeholder': 'e.g. 1000.00', 'id': 'id_primary_loss_limit'}),
            'final_loss_status':    forms.CheckboxInput(attrs={'class': _CHECK_CSS, 'role': 'switch', 'id': 'id_final_loss_status'}),
            'final_loss_limit':     forms.NumberInput(attrs={'class': _FIELD_CSS, 'step': '100', 'placeholder': 'e.g. 2000.00', 'id': 'id_final_loss_limit'}),
            'max_profit_status':    forms.CheckboxInput(attrs={'class': _CHECK_CSS, 'role': 'switch', 'id': 'id_max_profit_status'}),
            'max_profit_limit':     forms.NumberInput(attrs={'class': _FIELD_CSS, 'step': '500', 'placeholder': 'e.g. 10000.00', 'id': 'id_max_profit_limit'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['account_type'].required = False
        self.fields['trading_account'].required = False
        self.fields['primary_loss_limit'].required = False
        self.fields['final_loss_limit'].required = False
        self.fields['max_profit_limit'].required = False

    def clean(self):
        cleaned_data = super().clean()
        max_loss_status = cleaned_data.get('max_loss_status')
        primary_status = cleaned_data.get('primary_loss_status')
        primary_limit = cleaned_data.get('primary_loss_limit')
        final_status = cleaned_data.get('final_loss_status')
        final_limit = cleaned_data.get('final_loss_limit')
        max_profit_status = cleaned_data.get('max_profit_status')
        max_profit_limit = cleaned_data.get('max_profit_limit')

        if max_loss_status:
            if primary_status and (primary_limit is None or primary_limit <= 0):
                self.add_error('primary_loss_limit', 'Level 1 Warning Loss Limit must be greater than 0.')
            if final_status and (final_limit is None or final_limit <= 0):
                self.add_error('final_loss_limit', 'Level 2 Hard Day Loss Limit must be greater than 0.')
            if primary_status and final_status and primary_limit and final_limit:
                if primary_limit >= final_limit:
                    self.add_error('final_loss_limit', 'Level 2 Hard Loss Limit must be strictly greater than Level 1 Warning Limit.')
        if max_profit_status and (max_profit_limit is None or max_profit_limit <= 0):
            self.add_error('max_profit_limit', 'Max Profit Limit value is required when Max Profit rule is enabled.')

        return cleaned_data

        return cleaned_data
