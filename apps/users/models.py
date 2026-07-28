import uuid
import os
from django.db import models
from django.conf import settings    
from django.contrib.auth.models import AbstractUser


from apps.users.choices import BrokerChoices, MemberRoleChoices, PLStatusChoices, MemberRoleChoices


class User(AbstractUser):
    username = models.CharField(max_length=150, unique=True, null=True, blank=True)
    email = models.EmailField(unique=True, null=True, blank=True)
    phone_number = models.CharField(max_length=15, unique=True, null=True, blank=True)
    
    # Verification Flags
    is_mobile_verified = models.BooleanField(default=False)
    is_email_verified = models.BooleanField(default=False)

    role = models.CharField(
        max_length=20,
        choices=MemberRoleChoices.choices,
        default=MemberRoleChoices.TRADERS,
    )
    description = models.TextField(blank=True)
    
    # Broker & API Credentials
    broker = models.CharField(
        max_length=20,
        choices=BrokerChoices.choices,
        blank=True,
        null=True
    )
    api_key = models.CharField(max_length=255, blank=True, null=True)
    app_id = models.CharField(max_length=255, blank=True, null=True)

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


    def get_role_prefix(self):
        """
        Retrieves prefix from ENV using the role name (e.g. PREFIX_TRADERS).
        If ENV is not set, falls back to the first 3 letters of the role.
        """
        role_str = str(self.role).upper()
        
        # 1. First 3 letters of the role as default prefix
        default_prefix = role_str[:3]  # e.g., 'TRA' for 'TRADERS'
        
        # 2. Check ENV for custom key (e.g., PREFIX_TRADERS or TRADERS_PREFIX)
        env_key = f"PREFIX_{role_str}"
        return os.environ.get(env_key, default_prefix)

    def generate_unique_username(self):
        """Generates a username using the role prefix + random string/counter."""
        prefix = self.get_role_prefix()
        # Generates format like: TRA_a1b2c3d4
        unique_suffix = uuid.uuid4().hex[:8]
        return f"{prefix}_{unique_suffix}"

    def save(self, *args, **kwargs):
        # Generate username on creation if not explicitly provided
        if not self.pk and not self.username:
            new_username = self.generate_unique_username()
            # Ensure uniqueness check
            while User.objects.filter(username=new_username).exists():
                new_username = self.generate_unique_username()
            self.username = new_username
            
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} (@{self.username})"


class Team(models.Model):
    name = models.CharField(max_length=100)
    role = models.CharField(max_length=15, blank=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


    def __str__(self):
        return self.name



class TeamMember(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="team_member",
    )
    role = models.CharField(
        max_length=15,
        choices=MemberRoleChoices.choices,
        blank=True,
    )
    team = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, blank=True)
    phone = models.CharField(max_length=15, blank=True)
    employee_id = models.CharField(max_length=20, blank=True)
    date_joined_company = models.DateField(null=True, blank=True)
    is_active_developer = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def has_management_role(self):
        return self.role in getattr(settings, 'MANAGEMENT_ROLES', [])


    def __str__(self):
        return f"{self.user.get_full_name()} ({self.user.username})"