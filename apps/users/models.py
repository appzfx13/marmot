import os
import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser

from cloudinary.models import CloudinaryField
from apps.common.choices import BrokerChoices, MemberRoleChoices, PLStatusChoices
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

    # Generic Broker & API Credentials
    broker = models.CharField(
        max_length=20,
        choices=BrokerChoices.choices,
        blank=True,
        null=True,
        default=BrokerChoices.DHAN
    )
    broker_client_id = models.CharField(max_length=100, blank=True, null=True, db_index=True, help_text="Generic Broker Client ID")
    api_key = models.CharField(max_length=255, blank=True, null=True, help_text="Generic Broker API Key / Secret")
    app_id = models.CharField(max_length=255, blank=True, null=True, help_text="Generic Broker App ID / Client Secret")

    @property
    def client_id(self):
        return self.broker_client_id

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

    def get_role_prefix(self):
        """
        Retrieves prefix from ENV using the role name (e.g. PREFIX_TRADERS).
        If ENV is not set, falls back to the first 3 letters of the role.
        """
        role_str = str(self.role).upper()
        default_prefix = role_str[:3]
        env_key = f"PREFIX_{role_str}"
        return os.environ.get(env_key, default_prefix)

    def generate_unique_username(self):
        """Generates a username using the role prefix + random string."""
        prefix = self.get_role_prefix()
        unique_suffix = uuid.uuid4().hex[:8]
        return f"{prefix}_{unique_suffix}"

    def save(self, *args, **kwargs):
        # Generate username on creation if not explicitly provided
        if not self.pk and not self.username:
            new_username = self.generate_unique_username()
            while User.objects.filter(username=new_username).exists():
                new_username = self.generate_unique_username()
            self.username = new_username

        super().save(*args, **kwargs)

    def __str__(self):
        display_name = self.get_full_name() or self.username or f"User-{self.pk}"
        return f"{display_name} (@{self.username})"