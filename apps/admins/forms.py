from django import forms
from apps.users.models import User
from apps.trade_config.models import TradeExecConfig


class UserForm(forms.ModelForm):
    class Meta:
        model = User
        fields = [
            'first_name',
            'last_name',
            'username',
            'email',
            'phone_number',
            'is_email_verified',
            'is_mobile_verified',
            'broker',
            'broker_client_id',
            'api_key',
            'app_id',
            'description',
            'trade_eligibility',
            'is_blocked',
            'primary_freeze',
            'final_freeze',
        ]
        widgets = {
            'first_name': forms.TextInput(attrs={'placeholder': 'First Name'}),
            'last_name': forms.TextInput(attrs={'placeholder': 'Last Name'}),
            'username': forms.TextInput(attrs={'placeholder': 'Username'}),
            'email': forms.EmailInput(attrs={'placeholder': 'Email Address'}),
            'phone_number': forms.TextInput(attrs={'placeholder': '+1234567890'}),
            'broker': forms.Select(attrs={'class': 'form-select'}),
            'broker_client_id': forms.TextInput(attrs={'placeholder': 'Broker Client ID (e.g. 1000000001)'}),
            'api_key': forms.TextInput(attrs={'placeholder': 'API Key / App Key'}),
            'app_id': forms.TextInput(attrs={'placeholder': 'App ID / Client Secret'}),
            'description': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Optional description or notes...'}),
            'is_email_verified': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_mobile_verified': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'trade_eligibility': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_blocked': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'primary_freeze': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'final_freeze': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }



class TradeExecConfigForm(forms.ModelForm):
    class Meta:
        model = TradeExecConfig
        fields = [
            'name',
            'admins_user',
            'is_active',
            'max_loss_limit',
            'max_profit_limit',
            'auto_lot_status',
            'default_lot_size',
            'auto_sl_status',
            'default_risk_value',
            'default_risk_type',
            'layer_status',
            'layer_add_in_lot_count',
            'layer_percentage',
            'forecast_status',
            'backtest_status',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Enter configuration name', 'class': 'form-control'}),
            'admins_user': forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'max_loss_limit': forms.NumberInput(attrs={'placeholder': '0.00', 'step': '0.01'}),
            'max_profit_limit': forms.NumberInput(attrs={'placeholder': '0.00', 'step': '0.01'}),
            'auto_lot_status': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'default_lot_size': forms.NumberInput(attrs={'placeholder': '1', 'min': '1'}),
            'auto_sl_status': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'default_risk_value': forms.NumberInput(attrs={'placeholder': '0.00', 'step': '0.01'}),
            'default_risk_type': forms.Select(attrs={'class': 'form-select'}),
            'layer_status': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'layer_add_in_lot_count': forms.NumberInput(attrs={'placeholder': '0'}),
            'layer_percentage': forms.NumberInput(attrs={'placeholder': '0.00', 'step': '0.01'}),
            'forecast_status': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'backtest_status': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class AdminTraderPasswordResetForm(forms.Form):
    """Form for admins to reset a trader's password directly."""
    new_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter new password',
            'autocomplete': 'new-password'
        }),
        label="New Password",
        min_length=6
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirm new password',
            'autocomplete': 'new-password'
        }),
        label="Confirm Password",
        min_length=6
    )

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('new_password')
        p2 = cleaned_data.get('confirm_password')
        if p1 and p2 and p1 != p2:
            self.add_error('confirm_password', "Passwords do not match.")
        return cleaned_data