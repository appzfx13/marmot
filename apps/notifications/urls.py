from django.urls import path
from .views import LiveNotificationsView

app_name = 'notifications'

urlpatterns = [
    path('api/live/', LiveNotificationsView.as_view(), name='live_notifications'),
]