"""Django signals for SiteSettings cache invalidation."""
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from apps.common.models import SiteSettings
from apps.common.cache import clear_site_settings_cache


@receiver(post_save, sender=SiteSettings)
def site_settings_post_save_receiver(sender, instance, **kwargs):
    """Invalidate Redis cache when SiteSettings is saved."""
    clear_site_settings_cache()


@receiver(post_delete, sender=SiteSettings)
def site_settings_post_delete_receiver(sender, instance, **kwargs):
    """Invalidate Redis cache when SiteSettings is deleted."""
    clear_site_settings_cache()
