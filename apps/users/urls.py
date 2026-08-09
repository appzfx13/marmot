from django.urls import path
from .views import LoginView, UserDashboardView, LogoutView, UserProfileView

app_name = 'users'

urlpatterns = [
    path('login/', LoginView.as_view(), name='marmot-login'),
    path('dashboard/', UserDashboardView.as_view(), name='marmot-dashboard'),
    path('logout/', LogoutView.as_view(), name='marmot-logout'),
    path('profile/', UserProfileView.as_view(), name='marmot-profile'),
    path('profile/<int:pk>/', UserProfileView.as_view(), name='marmot-profile-user'),
]