from django.urls import path
from .views import (
    BacktestDashboardView,
    BacktestCreateView,
    BacktestDetailView,
    BacktestControlView,
    BacktestDeleteView,
    BacktestBulkDeleteView,
    StrategyListView,
    StrategyDetailView,
    StrategySaveCodeView,
    StrategyDeleteView,
)

app_name = 'backtest'

urlpatterns = [
    path('list/', BacktestDashboardView.as_view(), name='backtest_dashboard'),
    path('bulk-delete/', BacktestBulkDeleteView.as_view(), name='backtest_bulk_delete'),
    path('create/', BacktestCreateView.as_view(), name='backtest_create'),
    path('<int:pk>/', BacktestDetailView.as_view(), name='backtest_detail'),
    path('<int:pk>/control/', BacktestControlView.as_view(), name='backtest_control'),
    path('<int:pk>/delete/', BacktestDeleteView.as_view(), name='backtest_delete'),
    
    # Strategy Hub & Web UI Code Editor Endpoints
    path('strategies/', StrategyListView.as_view(), name='strategy_list'),
    path('strategies/<int:pk>/', StrategyDetailView.as_view(), name='strategy_detail'),
    path('strategies/<int:pk>/save-code/', StrategySaveCodeView.as_view(), name='strategy_save_code'),
    path('strategies/<int:pk>/delete/', StrategyDeleteView.as_view(), name='strategy_delete'),
]
