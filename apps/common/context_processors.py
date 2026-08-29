from django.conf import settings

from apps.common.cache import get_site_settings


def theme_context(request):
    """Inject the active UI theme configuration into template context."""
    return {
        'UI_THEME': getattr(settings, 'UI_THEME', 'default'),
    }


def site_settings_context(request):
    """Inject cached SiteSettings globally into template context."""
    return {
        'site_settings': get_site_settings(),
    }

