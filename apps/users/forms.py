from django import forms
from django.contrib.auth.forms import PasswordChangeForm
from .models import User


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = [
            'avatar',
            'first_name',
            'last_name',
            'username',
            'email',
            'phone_number',
            'description',
            'is_email_verified',
            'is_mobile_verified',
            'broker',
            'broker_client_id',
            'api_key',
            'app_id',
            'trade_eligibility',
            'is_blocked',
            'primary_freeze',
            'final_freeze',
        ]
        widgets = {
            'avatar': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First Name'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last Name'}),
            'username': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Username', 'readonly': 'readonly'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email Address'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone Number'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Profile bio / notes'}),
            'broker': forms.Select(attrs={'class': 'form-select'}),
            'broker_client_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Broker Client ID'}),
            'api_key': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'API Key / Secret'}),
            'app_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'App ID / Client Secret'}),
            'is_email_verified': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_mobile_verified': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'trade_eligibility': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_blocked': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'primary_freeze': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'final_freeze': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, request_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        user = self.instance
        req_user = request_user or user

        # Check if requesting user is Admin or Developer
        is_admin_or_dev = (
            getattr(req_user, 'is_superuser', False) or 
            getattr(req_user, 'role', '') in ['admin', 'developer']
        )

        # 1. Username is always read-only
        self.fields['username'].disabled = True

        # 2. Regular users cannot edit phone_number, verification badges, or control flags
        if not is_admin_or_dev:
            self.fields['phone_number'].disabled = True
            self.fields['is_email_verified'].disabled = True
            self.fields['is_mobile_verified'].disabled = True
            self.fields['trade_eligibility'].disabled = True
            self.fields['is_blocked'].disabled = True
            self.fields['primary_freeze'].disabled = True
            self.fields['final_freeze'].disabled = True

            # Broker credentials cannot be modified by user once created
            has_broker = bool(user and (user.broker or user.broker_client_id or user.api_key))
            if has_broker:
                self.fields['broker'].disabled = True
                self.fields['broker_client_id'].disabled = True
                self.fields['api_key'].disabled = True
                self.fields['app_id'].disabled = True


class UserProfilePasswordChangeForm(PasswordChangeForm):
    """Form for users and admins to change their own password."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'old_password' in self.fields:
            self.fields['old_password'].widget.attrs.update({
                'class': 'form-control',
                'placeholder': 'Enter current password',
                'autocomplete': 'current-password'
            })
        if 'new_password1' in self.fields:
            self.fields['new_password1'].widget.attrs.update({
                'class': 'form-control',
                'placeholder': 'Enter new password',
                'autocomplete': 'new-password'
            })
        if 'new_password2' in self.fields:
            self.fields['new_password2'].widget.attrs.update({
                'class': 'form-control',
                'placeholder': 'Confirm new password',
                'autocomplete': 'new-password'
            })

