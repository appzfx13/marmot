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
            # ── Market Type selector (NEW) ────────────────────────────────────
            'market_type',
            # ── Risk Controls (shared across both market types) ───────────────
            'max_loss_status',
            'max_loss_limit',
            'max_profit_status',
            'max_profit_limit',
            # ── Lot & SL (INDEX/F&O specific, hidden for FOREX) ──────────────
            'auto_lot_status',
            'default_lot_size',
            'auto_sl_status',
            'default_risk_value',
            'default_risk_type',
            # ── Layering & Features (shared) ─────────────────────────────────
            'layer_status',
            'layer_add_in_lot_count',
            'layer_percentage',
            'forecast_status',
            'backtest_status',
            # ── Forex / CME Futures (NEW, shown only for FOREX_FUTURES) ───────
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
            'max_loss_limit':       forms.NumberInput(attrs={'class': _FIELD_CSS, 'step': '500', 'placeholder': 'e.g. 5000.00', 'id': 'id_max_loss_limit'}),
            'max_profit_status':    forms.CheckboxInput(attrs={'class': _CHECK_CSS, 'role': 'switch', 'id': 'id_max_profit_status'}),
            'max_profit_limit':     forms.NumberInput(attrs={'class': _FIELD_CSS, 'step': '500', 'placeholder': 'e.g. 10000.00', 'id': 'id_max_profit_limit'}),
            # Lot / SL (INDEX/F&O)
            'auto_lot_status':      forms.CheckboxInput(attrs={'class': _CHECK_CSS, 'role': 'switch', 'id': 'id_auto_lot_status'}),
            'default_lot_size':     forms.NumberInput(attrs={'class': _FIELD_CSS, 'min': '1'}),
            'auto_sl_status':       forms.CheckboxInput(attrs={'class': _CHECK_CSS, 'role': 'switch', 'id': 'id_auto_sl_status'}),
            'default_risk_value':   forms.NumberInput(attrs={'class': _FIELD_CSS, 'step': '0.1'}),
            'default_risk_type':    forms.Select(attrs={'class': _SELECT_CSS}),
            # Layering
            'layer_status':         forms.CheckboxInput(attrs={'class': _CHECK_CSS, 'role': 'switch', 'id': 'id_layer_status'}),
            'layer_add_in_lot_count': forms.NumberInput(attrs={'class': _FIELD_CSS}),
            'layer_percentage':     forms.NumberInput(attrs={'class': _FIELD_CSS, 'step': '0.1'}),
            # Features
            'forecast_status':      forms.CheckboxInput(attrs={'class': _CHECK_CSS, 'role': 'switch', 'id': 'id_forecast_status'}),
            'backtest_status':      forms.CheckboxInput(attrs={'class': _CHECK_CSS, 'role': 'switch', 'id': 'id_backtest_status'}),
            # Forex / CME (NEW)
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
        self.fields['max_profit_limit'].required = False
        self.fields['default_risk_value'].required = False
        self.fields['default_risk_type'].required = False
        self.fields['default_lot_size'].required = False
        self.fields['layer_add_in_lot_count'].required = False
        self.fields['layer_percentage'].required = False
        self.fields['forex_contract_size'].required = False
        self.fields['forex_tick_value'].required = False
        self.fields['forex_max_contracts'].required = False

    def clean(self):
        cleaned_data = super().clean()
        auto_sl_status = cleaned_data.get('auto_sl_status')
        default_risk_value = cleaned_data.get('default_risk_value')
        layer_status = cleaned_data.get('layer_status')
        layer_percentage = cleaned_data.get('layer_percentage')

        if auto_sl_status and (default_risk_value is None or default_risk_value <= 0):
            self.add_error('default_risk_value', 'Risk value must be greater than 0 when Auto Stop Loss is enabled.')

        if layer_status and (layer_percentage is None or layer_percentage <= 0):
            self.add_error('layer_percentage', 'Layer step distance (%) is required when Order Layering is enabled.')

        # Safe defaults for un-checked numeric values
        if not cleaned_data.get('default_risk_value'):
            cleaned_data['default_risk_value'] = 0.00
        if not cleaned_data.get('default_risk_type'):
            cleaned_data['default_risk_type'] = RiskTypeChoices.PERCENTAGE
        if not cleaned_data.get('default_lot_size'):
            cleaned_data['default_lot_size'] = 1
        if not cleaned_data.get('layer_add_in_lot_count'):
            cleaned_data['layer_add_in_lot_count'] = 0
        if not cleaned_data.get('layer_percentage'):
            cleaned_data['layer_percentage'] = 0.00

        return cleaned_data
