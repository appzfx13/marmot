from django.urls import path
from .views import UserNotificationAPIView, UserNotificationListView

app_name = 'notifications'

urlpatterns = [
    path('notifications/api/live/', UserNotificationAPIView.as_view(), name='live_api'),
    # Full page list viewer endpoint
    path('notifications/inbox/', UserNotificationListView.as_view(), name='inbox_list'),
]