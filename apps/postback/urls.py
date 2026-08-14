from django.urls import path
from apps.trade_core.views import DhanConsentCallbackView
from .views import DhanPostbackWebhookView, GenericBrokerPostbackWebhookView

app_name = 'postback'

urlpatterns = [
    # DhanHQ OAuth / Consent Callback
    path('dhan/callback/', DhanConsentCallbackView.as_view(), name='dhan_callback'),

    # DhanHQ Specific Endpoints
    path('dhan/postback/', DhanPostbackWebhookView.as_view(), name='dhan_postback'),
    path('dhan/postback/<int:user_id>/', DhanPostbackWebhookView.as_view(), name='dhan_postback_user'),

    # Dynamic Multi-Broker Endpoints
    path('<str:broker>/postback/', GenericBrokerPostbackWebhookView.as_view(), name='broker_postback'),
    path('<str:broker>/postback/<int:user_id>/', GenericBrokerPostbackWebhookView.as_view(), name='broker_postback_user'),
]

