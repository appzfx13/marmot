from django import forms
from .models import MarketBackupTask
from apps.common.choices import MarketTypeChoices, ForexInstrumentChoices

_FIELD_CSS  = 'form-control bg-transparent theme-text-main border-secondary border-opacity-25'
_SELECT_CSS = 'form-select bg-transparent theme-text-main border-secondary border-opacity-25'


class MarketBackupForm(forms.ModelForm):
    # ── INDEX / F&O fields ──────────────────────────────────────────────────
    strike_count = forms.IntegerField(
        required=False,
        initial=5,
        min_value=0,
        max_value=50,
        widget=forms.NumberInput(attrs={'class': _FIELD_CSS, 'min': 0, 'max': 50})
    )

    dhan_access_token = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': _FIELD_CSS,
            'placeholder': 'Optional: Paste 24h Dhan Access Token (starts with eyJ...)'
        }),
        help_text="If not already authenticated via 'Auth DhanHQ', paste your 24-hour Access Token directly from web.dhan.co."
    )

    class Meta:
        model = MarketBackupTask
        fields = [
            'market_type',
            'start_date', 'end_date',
            # INDEX / F&O
            'index_name', 'strike_count',
            # FOREX / CME
            'forex_instrument', 'databento_schema',
        ]
        widgets = {
            'market_type':      forms.Select(attrs={'class': _SELECT_CSS, 'id': 'id_market_type'}),
            'start_date':       forms.DateInput(attrs={'type': 'date', 'class': _FIELD_CSS}),
            'end_date':         forms.DateInput(attrs={'type': 'date', 'class': _FIELD_CSS}),
            'index_name':       forms.Select(attrs={'class': _SELECT_CSS}),
            'forex_instrument': forms.Select(attrs={'class': _SELECT_CSS}),
            'databento_schema': forms.Select(attrs={'class': _SELECT_CSS}),
        }

    def clean(self):
        cleaned_data = super().clean()
        market_type = cleaned_data.get('market_type')
        index_name  = cleaned_data.get('index_name')
        strike_count = cleaned_data.get('strike_count')
        forex_instrument = cleaned_data.get('forex_instrument')

        if market_type == MarketTypeChoices.INDEX_FO:
            # Existing validation — untouched
            if not index_name:
                self.add_error('index_name', 'Please select a target index.')
            if index_name == 'INDIAVIX':
                cleaned_data['strike_count'] = 0
            elif strike_count is None or strike_count < 0:
                self.add_error('strike_count', 'Strike count cannot be negative.')
            # Clear forex field
            cleaned_data['forex_instrument'] = None

        elif market_type == MarketTypeChoices.FOREX_FUTURES:
            if not forex_instrument:
                self.add_error('forex_instrument', 'Please select a CME Micro Futures instrument.')
            # Clear INDEX fields
            cleaned_data['index_name'] = None
            cleaned_data['strike_count'] = None

        return cleaned_data


class MacroBackupForm(forms.ModelForm):
    """Form for creating AI Macro Assist background sync tasks with optional market dataset co-location."""

    class Meta:
        model = MarketBackupTask
        fields = ['linked_backup_task', 'market_type', 'start_date', 'end_date', 'index_name', 'forex_instrument', 'macro_timeframe']
        widgets = {
            'linked_backup_task': forms.Select(attrs={'class': _SELECT_CSS, 'id': 'id_macro_linked_backup_task'}),
            'market_type': forms.Select(attrs={'class': _SELECT_CSS, 'id': 'id_macro_market_type'}),
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': _FIELD_CSS, 'id': 'id_macro_start_date'}),
            'end_date': forms.DateInput(attrs={'type': 'date', 'class': _FIELD_CSS, 'id': 'id_macro_end_date'}),
            'index_name': forms.Select(attrs={'class': _SELECT_CSS, 'id': 'id_macro_index_name'}),
            'forex_instrument': forms.Select(attrs={'class': _SELECT_CSS, 'id': 'id_macro_forex_instrument'}),
            'macro_timeframe': forms.Select(attrs={'class': _SELECT_CSS, 'id': 'id_macro_timeframe'}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        qs = MarketBackupTask.objects.filter(is_deleted=False, is_macro_assist=False)
        if user and not getattr(user, 'is_superuser', False):
            qs = qs.filter(created_by=user)
        self.fields['linked_backup_task'].queryset = qs.order_by('-id')
        self.fields['linked_backup_task'].empty_label = "-- Select Market Backup Dataset to Co-locate (Optional) --"
        self.fields['linked_backup_task'].required = False
        self.fields['start_date'].required = False
        self.fields['end_date'].required = False
        self.fields['market_type'].required = False
        self.fields['linked_backup_task'].label_from_instance = (
            lambda obj: f"Backup #{obj.id} — {obj.display_symbol} ({obj.start_date} to {obj.end_date}) [{obj.provider_name}]"
        )

    def clean(self):
        cleaned_data = super().clean()
        linked = cleaned_data.get('linked_backup_task')
        if linked:
            if not cleaned_data.get('start_date'):
                cleaned_data['start_date'] = linked.start_date
            if not cleaned_data.get('end_date'):
                cleaned_data['end_date'] = linked.end_date
            if not cleaned_data.get('market_type'):
                cleaned_data['market_type'] = linked.market_type
            if linked.market_type == MarketTypeChoices.INDEX_FO and not cleaned_data.get('index_name'):
                cleaned_data['index_name'] = linked.index_name
            elif linked.market_type == MarketTypeChoices.FOREX_FUTURES and not cleaned_data.get('forex_instrument'):
                cleaned_data['forex_instrument'] = linked.forex_instrument

        if not cleaned_data.get('start_date'):
            self.add_error('start_date', 'Please provide a start date.')
        if not cleaned_data.get('end_date'):
            self.add_error('end_date', 'Please provide an end date.')
        if not cleaned_data.get('market_type'):
            cleaned_data['market_type'] = MarketTypeChoices.INDEX_FO

        market_type = cleaned_data.get('market_type')
        index_name = cleaned_data.get('index_name')
        forex_instrument = cleaned_data.get('forex_instrument')

        if market_type == MarketTypeChoices.INDEX_FO:
            if not index_name:
                self.add_error('index_name', 'Please select a target index.')
            cleaned_data['forex_instrument'] = None
        elif market_type == MarketTypeChoices.FOREX_FUTURES:
            if not forex_instrument:
                self.add_error('forex_instrument', 'Please select a CME Micro Futures instrument.')
            cleaned_data['index_name'] = None

        return cleaned_data