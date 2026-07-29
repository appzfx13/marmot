from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('apps.admins.urls')),
    path('', include('apps.api.urls')),
    path('', include('apps.common.urls')),
    path('', include('apps.market.urls')),
    path('', include('apps.masters.urls')),
    path('', include('apps.notifications.urls')),
    path('', include('apps.trade_config.urls')),
    path('', include('apps.trade_core.urls')),
    path('', include('apps.users.urls')),
]

# Static + Media files (Development only)
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)