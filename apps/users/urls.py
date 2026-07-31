from django.urls import path
from .views import LoginView, UserDashboardView, LogoutView

app_name = 'users'

urlpatterns = [
    path('login/', LoginView.as_view(), name='marmot-login'),
    path('dashboard/', UserDashboardView.as_view(), name='marmot-dashboard'),
    path('logout/', LogoutView.as_view(), name='marmot-logout'),
]