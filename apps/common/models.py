from django.db import models

# Create your models here.
import uuid
import os
from django.db import models
from django.utils import timezone
from django.conf import settings    
from django.contrib.auth.models import AbstractUser, UserManager

from apps.users.choices import BrokerChoices, MemberRoleChoices, PLStatusChoices

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