from django import forms
from .models import MarketBackupTask

class MarketBackupForm(forms.ModelForm):
    strike_count = forms.IntegerField(
        required=False,
        initial=5,
        min_value=0,
        max_value=50,
        widget=forms.NumberInput(attrs={'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25', 'min': 0, 'max': 50})
    )

    dhan_access_token = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25',
            'placeholder': 'Optional: Paste 24h Dhan Access Token (starts with eyJ...)'
        }),
        help_text="If not already authenticated via 'Auth DhanHQ', paste your 24-hour Access Token directly from web.dhan.co."
    )

    class Meta:
        model = MarketBackupTask
        fields = ['index_name', 'start_date', 'end_date', 'strike_count']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25'}),
            'end_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25'}),
            'index_name': forms.Select(attrs={'class': 'form-select bg-transparent theme-text-main border-secondary border-opacity-25'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        index_name = cleaned_data.get('index_name')
        strike_count = cleaned_data.get('strike_count')
        if index_name == 'INDIAVIX':
            cleaned_data['strike_count'] = 0
        elif strike_count is None or strike_count <= 0:
            self.add_error('strike_count', "Strike count must be at least 1 for index options.")
        return cleaned_data