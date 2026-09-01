from django.urls import path
from .views import PostbackWebhookView, AIChatAPIView

app_name = 'api'

urlpatterns = [
    path('postback/', PostbackWebhookView.as_view(), name='postback_global'),
    path('postback/<int:user_id>/', PostbackWebhookView.as_view(), name='postback_user'),
    path('ai-chat/', AIChatAPIView.as_view(), name='ai_chat'),
]