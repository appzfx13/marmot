from django import forms
from .models import MarketBackupTask

class MarketBackupForm(forms.ModelForm):
    class Meta:
        model = MarketBackupTask
        fields = ['start_date', 'end_date', 'index_name', 'strike_count']
        widgets = {
            'start_date': forms.DateInput(attrs={
                'type': 'date', 
                'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25 shadow-none'
            }),
            'end_date': forms.DateInput(attrs={
                'type': 'date', 
                'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25 shadow-none'
            }),
            'index_name': forms.Select(attrs={
                'class': 'form-select bg-transparent theme-text-main border-secondary border-opacity-25 shadow-none'
            }),
            'strike_count': forms.NumberInput(attrs={
                'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25 shadow-none', 
                'min': 1, 
                'max': 50
            }),
        }