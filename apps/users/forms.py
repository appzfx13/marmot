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
        if 'username' in self.fields:
            self.fields['username'].disabled = True

        # 2. Regular users cannot edit phone_number, verification badges, or control flags
        if not is_admin_or_dev:
            for fname in ['phone_number', 'is_email_verified', 'is_mobile_verified', 'trade_eligibility', 'is_blocked', 'primary_freeze', 'final_freeze']:
                if fname in self.fields:
                    self.fields[fname].disabled = True


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


from apps.backtest.models import BacktestTask
from apps.market.models import MarketBackupTask

class UserBacktestTaskForm(forms.ModelForm):
    backup_task = forms.ModelChoiceField(
        queryset=MarketBackupTask.objects.filter(is_deleted=False),
        required=False,
        empty_label="-- Select Existing Backup File (Optional) --",
        widget=forms.Select(attrs={'class': 'form-select bg-transparent theme-text-main border-secondary border-opacity-25', 'id': 'id_user_backup_task'})
    )
    risk_reward_ratio = forms.FloatField(initial=2.0, required=False, help_text="Risk to Reward Ratio (e.g. 2.0)")
    stop_loss_pct = forms.FloatField(initial=0.5, required=False, help_text="Stop Loss Percentage (e.g. 0.5%)")

    class Meta:
        model = BacktestTask
        fields = ['backup_task', 'strategy_name', 'index_name', 'start_date', 'end_date', 'initial_capital']
        widgets = {
            'strategy_name': forms.Select(attrs={'class': 'form-select bg-transparent theme-text-main border-secondary border-opacity-25'}),
            'index_name': forms.Select(attrs={'class': 'form-select bg-transparent theme-text-main border-secondary border-opacity-25', 'id': 'id_user_index_name'}),
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25', 'id': 'id_user_start_date'}),
            'end_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25', 'id': 'id_user_end_date'}),
            'initial_capital': forms.NumberInput(attrs={'class': 'form-control bg-transparent theme-text-main border-secondary border-opacity-25', 'step': '1000'}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            self.fields['backup_task'].queryset = MarketBackupTask.objects.filter(is_deleted=False, created_by=user)

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        initial_capital = cleaned_data.get('initial_capital')
        if start_date and end_date and start_date > end_date:
            raise forms.ValidationError("Start date cannot be after End date.")
        if initial_capital is not None and initial_capital <= 0:
            raise forms.ValidationError("Initial capital must be a positive amount.")
        return cleaned_data



