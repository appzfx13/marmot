from django.shortcuts import render
from apps.common.models import SiteSettings


def handler404(request, exception=None):
    """Custom 404 error handler injecting dynamic site settings."""
    site_settings = SiteSettings.load()
    return render(request, '404.html', {'site_settings': site_settings}, status=404)


def handler500(request):
    """Custom 500 server error handler injecting dynamic site settings."""
    site_settings = SiteSettings.load()
    return render(request, '404.html', {'site_settings': site_settings, 'is_500': True}, status=500)


def page_not_found_preview(request):
    """Preview route for testing the 404 page directly in development."""
    return handler404(request)