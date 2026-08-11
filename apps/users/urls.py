from django.urls import path
from .views import (
    LoginView, 
    UserDashboardView, 
    UserJournalView, 
    UserBacktestView, 
    UserSandboxSettingsView, 
    UserKillSwitchView, 
    LogoutView, 
    UserProfileView, 
    UserProfilePasswordChangeView
)

app_name = 'users'

urlpatterns = [
    path('login/', LoginView.as_view(), name='marmot-login'),
    path('dashboard/', UserDashboardView.as_view(), name='marmot-dashboard'),
    path('journal/', UserJournalView.as_view(), name='user-journal'),
    path('backtest/', UserBacktestView.as_view(), name='user-backtest'),
    path('sandbox/', UserSandboxSettingsView.as_view(), name='user-sandbox'),
    path('kill-switch/', UserKillSwitchView.as_view(), name='user-kill-switch'),
    path('logout/', LogoutView.as_view(), name='marmot-logout'),
    path('profile/', UserProfileView.as_view(), name='marmot-profile'),
    path('profile/<int:pk>/', UserProfileView.as_view(), name='marmot-profile-user'),
    path('profile/change-password/', UserProfilePasswordChangeView.as_view(), name='marmot-profile-password'),
]