from django import forms
from users.models import MarmotUser


class MarmotUserForm(forms.ModelForm):
    class Meta:
        model = MarmotUser
        fields = [
            'name',
            'username',
            'email',
            'phone_number',
            'is_email_verified',
            'is_mobile_verified',
            'broker',
            'api_key',
            'app_id',
            'description',
            'trade_eligibility',
            'is_blocked',
            'primary_freeze',
            'final_freeze',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Full Name'}),
            'username': forms.TextInput(attrs={'placeholder': 'Username'}),
            'email': forms.EmailInput(attrs={'placeholder': 'Email Address'}),
            'phone_number': forms.TextInput(attrs={'placeholder': '+1234567890'}),
            'broker': forms.Select(attrs={'class': 'form-select'}),
            'api_key': forms.TextInput(attrs={'placeholder': 'API Key'}),
            'app_id': forms.TextInput(attrs={'placeholder': 'App ID'}),
            'description': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Optional description or notes...'}),
            'is_email_verified': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_mobile_verified': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'trade_eligibility': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_blocked': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'primary_freeze': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'final_freeze': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }