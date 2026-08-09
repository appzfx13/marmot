from django.urls import path
from .views import (
    BacktestDashboardView,
    BacktestCreateView,
    BacktestDetailView,
    BacktestControlView,
    BacktestDeleteView,
)

app_name = 'backtest'

urlpatterns = [
    path('list/', BacktestDashboardView.as_view(), name='backtest_dashboard'),
    path('create/', BacktestCreateView.as_view(), name='backtest_create'),
    path('<int:pk>/', BacktestDetailView.as_view(), name='backtest_detail'),
    path('<int:pk>/control/', BacktestControlView.as_view(), name='backtest_control'),
    path('<int:pk>/delete/', BacktestDeleteView.as_view(), name='backtest_delete'),
]
