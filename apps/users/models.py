import os
import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser

from cloudinary.models import CloudinaryField
from apps.common.choices import AccountTypeChoices, BrokerChoices, MemberRoleChoices, PLStatusChoices
from apps.common.models import BaseModel, SoftDeleteUserModelManager


class User(AbstractUser, BaseModel):
    username = models.CharField(max_length=150, unique=True, null=True, blank=True)
    email = models.EmailField(unique=True, null=True, blank=True)
    phone_number = models.CharField(max_length=15, unique=True, null=True, blank=True)
    avatar = CloudinaryField('avatar', blank=True, null=True, help_text="Profile picture stored on Cloudinary")

    # Verification Flags
    is_mobile_verified = models.BooleanField(default=False)
    is_email_verified = models.BooleanField(default=False)

    role = models.CharField(
        max_length=20,
        choices=MemberRoleChoices.choices,
        default=MemberRoleChoices.TRADERS,
    )
    description = models.TextField(blank=True)

    # Freeze / Control Flags
    primary_freeze = models.BooleanField(default=False)
    final_freeze = models.BooleanField(default=False)
    is_blocked = models.BooleanField(default=False)
    trade_eligibility = models.BooleanField(default=True)

    # P&L & Performance Metrics
    pl_integer = models.DecimalField(
        max_digits=12, decimal_places=2, default=0.00, help_text="Current P&L value"
    )
    stats = models.CharField(
        max_length=20,
        choices=PLStatusChoices.choices,
        default=PLStatusChoices.NO_TRADE,
    )

    # Primary Freeze Metrics
    primary_freeze_time = models.DateTimeField(blank=True, null=True)
    primary_freeze_pl = models.DecimalField(
        max_digits=12, decimal_places=2, blank=True, null=True
    )

    # Final Freeze Metrics
    final_freeze_time = models.DateTimeField(blank=True, null=True)
    final_freeze_pl = models.DecimalField(
        max_digits=12, decimal_places=2, blank=True, null=True
    )

    REQUIRED_FIELDS = ['phone_number']

    # Custom Manager to support AbstractUser features (like createsuperuser) + SoftDelete
    objects = SoftDeleteUserModelManager()
    all_objects = SoftDeleteUserModelManager(with_deleted=True)

    @property
    def broker(self):
        active = self.get_active_trading_account()
        return active.broker.code if active and active.broker else 'dhan'

    @property
    def broker_client_id(self):
        active = self.get_active_trading_account()
        return active.broker_client_id if active else ''

    @property
    def client_id(self):
        return self.broker_client_id

    def get_active_trading_account(self, request=None):
        """
        Resolves active UserTradingAccount for this user.
        Priority:
        1. Account ID stored in request session ('active_account_id')
        2. Account flagged as is_default=True
        3. First active account
        4. Auto-creates default Sandbox paper-trading account
        """
        from apps.trade_config.models import UserTradingAccount, BrokerMaster

        account_id = None
        if request and hasattr(request, 'session'):
            account_id = request.session.get('active_account_id')

        if account_id:
            account = self.trading_accounts.filter(id=account_id, is_active=True).first()
            if account:
                return account

        account = self.trading_accounts.filter(is_default=True, is_active=True).first()
        if account:
            return account

        account = self.trading_accounts.filter(is_active=True).first()
        if account:
            return account

        # Fallback: auto-seed Sandbox Broker Master and default account
        sandbox_broker, _ = BrokerMaster.objects.get_or_create(
            code='sandbox',
            defaults={'name': 'SANDBOX', 'description': 'Default Paper Trading Broker Platform'}
        )
        return UserTradingAccount.objects.create(
            user=self,
            broker=sandbox_broker,
            account_name='Default Sandbox Account',
            account_type=AccountTypeChoices.SANDBOX,
            is_default=True,
            is_active=True,
            is_configured=True
        )

    def get_role_prefix(self):
        role_str = str(self.role).upper()
        default_prefix = role_str[:3]
        env_key = f"PREFIX_{role_str}"
        return os.environ.get(env_key, default_prefix)

    def generate_unique_username(self):
        prefix = self.get_role_prefix()
        unique_suffix = uuid.uuid4().hex[:8]
        return f"{prefix}_{unique_suffix}"

    def save(self, *args, **kwargs):
        if not self.pk and not self.username:
            new_username = self.generate_unique_username()
            while User.objects.filter(username=new_username).exists():
                new_username = self.generate_unique_username()
            self.username = new_username

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"