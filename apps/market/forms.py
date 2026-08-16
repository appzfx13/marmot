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
            'forex_instrument',
        ]
        widgets = {
            'market_type':      forms.Select(attrs={'class': _SELECT_CSS, 'id': 'id_market_type'}),
            'start_date':       forms.DateInput(attrs={'type': 'date', 'class': _FIELD_CSS}),
            'end_date':         forms.DateInput(attrs={'type': 'date', 'class': _FIELD_CSS}),
            'index_name':       forms.Select(attrs={'class': _SELECT_CSS}),
            'forex_instrument': forms.Select(attrs={'class': _SELECT_CSS}),
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
            elif strike_count is None or strike_count <= 0:
                self.add_error('strike_count', 'Strike count must be at least 1 for index options.')
            # Clear forex field
            cleaned_data['forex_instrument'] = None

        elif market_type == MarketTypeChoices.FOREX_FUTURES:
            if not forex_instrument:
                self.add_error('forex_instrument', 'Please select a CME Micro Futures instrument.')
            # Clear INDEX fields
            cleaned_data['index_name'] = None
            cleaned_data['strike_count'] = None

        return cleaned_data