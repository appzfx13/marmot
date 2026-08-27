from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.forms import PasswordChangeForm, PasswordResetForm
from django.core.exceptions import ValidationError
from apps.common.choices import MemberRoleChoices
from .models import User


class TraderSignUpForm(forms.ModelForm):
    first_name = forms.CharField(
        max_length=50,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Your first name',
            'id': 'firstName'
        })
    )
    last_name = forms.CharField(
        max_length=50,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Your last name',
            'id': 'lastName'
        })
    )
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Your email address',
            'id': 'email'
        })
    )
    password = forms.CharField(
        required=True,
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your password (min 6 characters)',
            'id': 'password'
        })
    )
    remember_me = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input',
            'id': 'remember_me'
        })
    )

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'password']

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("An account with this email address already exists.")
        return email

    def clean_password(self):
        password = self.cleaned_data.get('password')
        if len(password) < 6:
            raise ValidationError("Password must be at least 6 characters.")
        return password

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.role = MemberRoleChoices.TRADERS
        user.is_active = False
        user.is_email_verified = False
        user.set_password(self.cleaned_data['password'])
        if commit:
            user.save()
            # Ensure Sandbox trading account is auto-created
            user.get_active_trading_account()
        return user


class OtpVerificationForm(forms.Form):
    otp = forms.CharField(
        max_length=6,
        min_length=6,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control text-center font-monospace fs-3 fw-bold',
            'placeholder': '000000',
            'id': 'otpInput',
            'maxlength': '6',
            'inputmode': 'numeric',
            'pattern': '[0-9]*',
            'autocomplete': 'one-time-code',
            'autofocus': 'autofocus'
        })
    )

    def clean_otp(self):
        otp = self.cleaned_data.get('otp', '').strip()
        if not otp.isdigit() or len(otp) != 6:
            raise ValidationError("Please enter a valid 6-digit numeric verification code.")
        return otp


class EmailSsoRequestForm(forms.Form):
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your email address',
            'id': 'ssoEmailField',
            'autocomplete': 'email'
        })
    )

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if not User.objects.filter(email__iexact=email).exists():
            raise ValidationError("No registered account found with this email. Please sign up first.")
        return email


class TraderLoginForm(forms.Form):
    username = forms.CharField(
        max_length=150,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Your email or username',
            'id': 'usernameField',
            'autocomplete': 'username'
        })
    )
    password = forms.CharField(
        required=True,
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your password',
            'id': 'passwordField',
            'autocomplete': 'current-password'
        })
    )
    remember_me = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input',
            'id': 'rememberMe'
        })
    )

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.user_cache = None
        super().__init__(*args, **kwargs)

    def clean(self):
        username_or_email = self.cleaned_data.get('username', '').strip()
        password = self.cleaned_data.get('password')

        if username_or_email and password:
            # Try authenticating directly by username
            user = authenticate(self.request, username=username_or_email, password=password)

            # If not authenticated, check if they passed email instead
            if user is None:
                user_obj = User.objects.filter(email__iexact=username_or_email).first()
                if user_obj:
                    user = authenticate(self.request, username=user_obj.username, password=password)

            if user is None:
                # Check if credentials match an unverified / inactive user
                candidate = User.objects.filter(username__iexact=username_or_email).first()
                if not candidate:
                    candidate = User.objects.filter(email__iexact=username_or_email).first()
                if candidate and candidate.check_password(password) and not candidate.is_email_verified:
                    self.unverified_user = candidate
                    raise ValidationError("EMAIL_NOT_VERIFIED")
                raise ValidationError("Invalid email/username or password. Please verify your credentials.")
            elif not user.is_active or not getattr(user, 'is_email_verified', False):
                if not getattr(user, 'is_email_verified', False):
                    self.unverified_user = user
                    raise ValidationError("EMAIL_NOT_VERIFIED")
                raise ValidationError("This account is inactive. Please contact support.")
            elif getattr(user, 'is_blocked', False):
                raise ValidationError("This account is currently suspended. Please contact platform administrators.")

            self.user_cache = user

        return self.cleaned_data

    def get_user(self):
        return self.user_cache


class TraderPasswordResetForm(PasswordResetForm):
    email = forms.EmailField(
        max_length=254,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Your email address',
            'id': 'id_email',
            'autocomplete': 'email'
        })
    )



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
from apps.backtest.forms import BackupTaskSelectWidget
from apps.market.models import MarketBackupTask
from apps.common.choices import IndexChoices, ForexInstrumentChoices, MarketTypeChoices

class UserBacktestTaskForm(forms.ModelForm):
    market_type = forms.ChoiceField(
        choices=MarketTypeChoices.choices,
        initial=MarketTypeChoices.INDEX_FO,
        widget=forms.Select(attrs={'class': 'form-select bg-transparent theme-text-main border-secondary border-opacity-25', 'id': 'id_user_market_type'})
    )
    backup_task = forms.ModelChoiceField(
        queryset=MarketBackupTask.objects.filter(is_deleted=False),
        required=False,
        empty_label="-- Select Existing Backup File (Optional) --",
        widget=BackupTaskSelectWidget(attrs={'class': 'form-select bg-transparent theme-text-main border-secondary border-opacity-25', 'id': 'id_user_backup_task'})
    )
    index_name = forms.ChoiceField(
        choices=IndexChoices.choices + ForexInstrumentChoices.choices,
        required=True,
        widget=forms.Select(attrs={'class': 'form-select bg-transparent theme-text-main border-secondary border-opacity-25', 'id': 'id_user_index_name'})
    )
    risk_reward_ratio = forms.FloatField(initial=2.0, required=False, help_text="Risk to Reward Ratio (e.g. 2.0)")
    stop_loss_pct = forms.FloatField(initial=0.5, required=False, help_text="Stop Loss Percentage (e.g. 0.5%)")

    class Meta:
        model = BacktestTask
        fields = ['market_type', 'backup_task', 'strategy_name', 'index_name', 'start_date', 'end_date', 'initial_capital']
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



