from django.db import models

# Create your models here.
import uuid
import os
from django.db import models
from django.utils import timezone
from django.conf import settings    
from django.contrib.auth.models import AbstractUser, UserManager

from apps.common.choices import BrokerChoices, MemberRoleChoices, PLStatusChoices

# --- Soft Delete Model & Manager setup ---

class SoftDeleteQuerySet(models.QuerySet):
    def delete(self):
        return super().update(is_deleted=True, deleted_at=timezone.now())

    def hard_delete(self):
        return super().delete()

    def alive(self):
        return self.filter(is_deleted=False)

    def dead(self):
        return self.filter(is_deleted=True)


class SoftDeleteManager(models.Manager):
    def __init__(self, *args, **kwargs):
        self._with_deleted = kwargs.pop('with_deleted', False)
        super().__init__(*args, **kwargs)

    def get_queryset(self):
        if self._with_deleted:
            return SoftDeleteQuerySet(self.model, using=self._db)
        return SoftDeleteQuerySet(self.model, using=self._db).filter(is_deleted=False)


class SoftDeleteUserModelManager(UserManager, SoftDeleteManager):
    """Custom manager for AbstractUser to handle soft delete and superuser creation properly."""
    pass


class BaseModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey( settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,  blank=True, related_name="%(class)s_created_by")
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = SoftDeleteManager()
    all_objects = SoftDeleteManager(with_deleted=True)

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False):
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=['is_deleted', 'deleted_at'])

    def hard_delete(self):
        super().delete()


class PostbackLog(BaseModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='postback_logs',
        null=True,
        blank=True,
        help_text="User associated with the postback webhook"
    )
    broker = models.CharField(max_length=50, default='DHAN', help_text="Broker origin e.g. DHAN, FYERS")
    broker_client_id = models.CharField(max_length=100, blank=True, null=True, db_index=True, help_text="Generic Broker Client ID")
    order_id = models.CharField(max_length=100, blank=True, null=True, help_text="Broker Order ID")
    symbol = models.CharField(max_length=100, blank=True, null=True, help_text="Trading Symbol e.g. NIFTY-Jan2024-21500-CE")
    order_status = models.CharField(max_length=50, blank=True, null=True, help_text="Order Status e.g. TRADED, CANCELLED")
    transaction_type = models.CharField(max_length=20, blank=True, null=True, help_text="BUY / SELL")
    quantity = models.IntegerField(default=0, help_text="Order Quantity")
    price = models.FloatField(default=0.0, help_text="Execution Price")
    payload = models.JSONField(default=dict, help_text="Complete raw webhook JSON payload")
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Postback Log"
        verbose_name_plural = "Postback Logs"

    def __str__(self):
        user_str = self.user.username if self.user else "Anonymous"
        return f"Postback [{self.broker}] - User: {user_str} | Order: {self.order_id} ({self.order_status})"


def site_setting_logo_path(instance, filename):
    ext = filename.split('.')[-1].lower()
    return f"site/logos/{uuid.uuid4().hex[:8]}.{ext}"


class SiteSettings(BaseModel):
    """Singleton site configuration model for branding, logos, and meta configs."""
    brand_name = models.CharField(max_length=100, default='Marmot', help_text="Platform brand name")
    logo_dark = models.ImageField(upload_to=site_setting_logo_path, null=True, blank=True, help_text="Dark theme logo (.svg, .png, .jpg)")
    logo_light = models.ImageField(upload_to=site_setting_logo_path, null=True, blank=True, help_text="Light theme logo (.svg, .png, .jpg)")
    favicon = models.ImageField(upload_to=site_setting_logo_path, null=True, blank=True, help_text="Favicon icon (.ico, .png, .svg)")
    meta_config = models.JSONField(default=dict, blank=True, help_text="Extensible metadata & SEO configuration")

    class Meta:
        verbose_name = "Site Settings"
        verbose_name_plural = "Site Settings"

    def __str__(self):
        return f"SiteSettings ({self.brand_name})"

    def save(self, *args, **kwargs):
        self.id = 1
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj