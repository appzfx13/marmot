from django import forms
from .models import MarketBackupTask

class MarketBackupForm(forms.ModelForm):
    class Meta:
        model = MarketBackupTask
        fields = ['index_name', 'start_date', 'end_date', 'strike_count']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25'}),
            'end_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25'}),
            'index_name': forms.Select(attrs={'class': 'form-select bg-transparent theme-text-main border-secondary border-opacity-25'}),
            'strike_count': forms.NumberInput(attrs={'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25', 'min': 1, 'max': 50}),
        }