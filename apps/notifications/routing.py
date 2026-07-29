# your_app_name/routing.py
from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # Matches /ws/notifications/
    re_path(r"^ws/notifications/$", consumers.GlobalEventConsumer.as_asgi()),
]