from django import forms
from .models import TradeExecConfig, UserTradingAccount, BrokerMaster
from apps.common.choices import RiskTypeChoices, AccountTypeChoices, MarketTypeChoices, ForexInstrumentChoices

_FIELD_CSS  = 'form-control bg-transparent theme-text-main border-secondary border-opacity-25'
_SELECT_CSS = 'form-select bg-transparent theme-text-main border-secondary border-opacity-25'
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
            'account_type',
            'is_active',
            # ── Market Type selector (NEW) ────────────────────────────────────
            'market_type',
            # ── Risk Controls (shared across both market types) ───────────────
            'max_loss_limit',
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
            'account_type':         forms.Select(attrs={'class': _SELECT_CSS}),
            'is_active':            forms.CheckboxInput(attrs={'class': _CHECK_CSS}),
            # Market Type
            'market_type':          forms.Select(attrs={'class': _SELECT_CSS, 'id': 'id_market_type'}),
            # Risk
            'max_loss_limit':       forms.NumberInput(attrs={'class': _FIELD_CSS, 'step': '500'}),
            'max_profit_limit':     forms.NumberInput(attrs={'class': _FIELD_CSS, 'step': '500'}),
            # Lot / SL (INDEX/F&O)
            'auto_lot_status':      forms.CheckboxInput(attrs={'class': _CHECK_CSS}),
            'default_lot_size':     forms.NumberInput(attrs={'class': _FIELD_CSS, 'min': '1'}),
            'auto_sl_status':       forms.CheckboxInput(attrs={'class': _CHECK_CSS}),
            'default_risk_value':   forms.NumberInput(attrs={'class': _FIELD_CSS, 'step': '0.1'}),
            'default_risk_type':    forms.Select(attrs={'class': _SELECT_CSS}),
            # Layering
            'layer_status':         forms.CheckboxInput(attrs={'class': _CHECK_CSS}),
            'layer_add_in_lot_count': forms.NumberInput(attrs={'class': _FIELD_CSS}),
            'layer_percentage':     forms.NumberInput(attrs={'class': _FIELD_CSS, 'step': '0.1'}),
            # Features
            'forecast_status':      forms.CheckboxInput(attrs={'class': _CHECK_CSS}),
            'backtest_status':      forms.CheckboxInput(attrs={'class': _CHECK_CSS}),
            # Forex / CME (NEW)
            'forex_instrument':     forms.Select(attrs={'class': _SELECT_CSS}),
            'forex_broker_api_key': forms.TextInput(attrs={'class': _FIELD_CSS, 'placeholder': 'Rithmic / OANDA API Key'}),
            'forex_account_id':     forms.TextInput(attrs={'class': _FIELD_CSS, 'placeholder': 'Broker Account ID'}),
            'forex_contract_size':  forms.NumberInput(attrs={'class': _FIELD_CSS, 'step': '0.0001', 'placeholder': 'e.g. 10 for MGC'}),
            'forex_tick_value':     forms.NumberInput(attrs={'class': _FIELD_CSS, 'step': '0.0001', 'placeholder': 'e.g. 1.00 for MGC'}),
            'forex_max_contracts':  forms.NumberInput(attrs={'class': _FIELD_CSS, 'min': '1', 'placeholder': 'Max contracts per trade'}),
        }
