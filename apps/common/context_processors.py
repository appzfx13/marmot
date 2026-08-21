from django.conf import settings


def theme_context(request):
    """Inject the active UI theme configuration into template context."""
    return {
        'UI_THEME': getattr(settings, 'UI_THEME', 'default'),
    }
