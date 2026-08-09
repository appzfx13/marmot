from django.urls import path
from .views import (
    MarketBackupListView,
    MarketBackupCreateView,
    MarketBackupDetailView,
    MarketBackupDownloadView,
    MarketBackupControlView,
    MarketBackupDeleteView,
    BacktestDashboardView,
)

app_name = 'market'

urlpatterns = [
    # Dashboard / List View aliases (Fixes NoReverseMatch for both patterns)
    path('backup/', MarketBackupListView.as_view(), name='market_backup_view'),
    path('backup/list/', MarketBackupListView.as_view(), name='market_backup_list'),
    
    # Backtest Engine Placeholder Route
    path('backtest/', BacktestDashboardView.as_view(), name='backtest_dashboard'),
    
    # CRUD & Lifecycle Operations
    path('backup/create/', MarketBackupCreateView.as_view(), name='market_backup_create'),
    path('backup/<int:pk>/', MarketBackupDetailView.as_view(), name='market_backup_detail'),
    path('backup/<int:pk>/download/', MarketBackupDownloadView.as_view(), name='market_backup_download'),
    path('backup/<int:pk>/control/', MarketBackupControlView.as_view(), name='market_backup_control'),
    path('backup/<int:pk>/delete/', MarketBackupDeleteView.as_view(), name='market_backup_delete'),
]