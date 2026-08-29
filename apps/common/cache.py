"""Caching utilities for SiteSettings and platform configuration."""
from django.core.cache import cache

SITE_SETTINGS_CACHE_KEY = 'marmot:site_settings'
SITE_SETTINGS_CACHE_TIMEOUT = 86400  # 24 hours


def get_site_settings():
    """Fetch cached site settings dictionary from Redis or load from DB if cache missed."""
    cached_data = cache.get(SITE_SETTINGS_CACHE_KEY)
    if cached_data is not None:
        return cached_data

    from apps.common.models import SiteSettings

    obj = SiteSettings.load()
    data = {
        'brand_name': obj.brand_name,
        'logo_dark': obj.logo_dark.url if obj.logo_dark else None,
        'logo_light': obj.logo_light.url if obj.logo_light else None,
        'favicon': obj.favicon.url if obj.favicon else None,
        'meta_config': obj.meta_config or {},
    }
    cache.set(SITE_SETTINGS_CACHE_KEY, data, timeout=SITE_SETTINGS_CACHE_TIMEOUT)
    return data


def clear_site_settings_cache():
    """Invalidate and clear the SiteSettings Redis cache key."""
    cache.delete(SITE_SETTINGS_CACHE_KEY)
