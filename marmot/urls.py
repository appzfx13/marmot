from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include

urlpatterns = [
    # Admin Interface
    path('admin/', admin.site.urls),

    # Core App Routes (Web / HTMX)
    path('admins/', include(('apps.admins.urls', 'admins'), namespace='admins')),
    path('backtest/', include(('apps.backtest.urls', 'backtest'), namespace='backtest')),
    path('common/', include(('apps.common.urls', 'common'), namespace='common')),
    path('market/', include(('apps.market.urls', 'market'), namespace='market')),
    path('masters/', include(('apps.masters.urls', 'masters'), namespace='masters')),
    path('notifications/', include(('apps.notifications.urls', 'notifications'), namespace='notifications')),
    path('trade-config/', include(('apps.trade_config.urls', 'trade_config'), namespace='trade_config')),
    path('trade-core/', include(('apps.trade_core.urls', 'trade_core'), namespace='trade_core')),
    path('users/', include(('apps.users.urls', 'users'), namespace='users')),

    # REST API & Webhook Routes
    path('api/', include(('apps.postback.urls', 'postback'), namespace='postback')),
    path('api/', include(('apps.api.urls', 'api'), namespace='api')),
]

# Static + Media files (Development only)
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)