from django.urls import path
from .views import DhanAdminConsentLoginView, DhanUserConsentLoginView, DhanConsentCallbackView

app_name = 'trade_core'

urlpatterns = [
    # DhanHQ Consent / OAuth Authentication Routes
    path('dhan/admin-login/', DhanAdminConsentLoginView.as_view(), name='dhan-admin-login'),
    path('dhan/user-login/', DhanUserConsentLoginView.as_view(), name='dhan-user-login'),
    path('dhan/user-login/<int:account_id>/', DhanUserConsentLoginView.as_view(), name='dhan-user-login-account'),
    path('dhan/callback/', DhanConsentCallbackView.as_view(), name='dhan-callback'),
]