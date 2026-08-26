from django.urls import path
from .views import (
    MarketBackupListView,
    MarketBackupCreateView,
    MarketBackupDetailView,
    MarketBackupPreviewView,
    MarketBackupScrollView,
    MarketBackupChartView,
    MarketBackupDownloadView,
    MarketBackupControlView,
    MarketBackupDeleteView,
    MarketBackupBulkDeleteView,
    MarketBackupStatusView,
)

app_name = 'market'

urlpatterns = [
    # Backup Dashboard / List
    path('backup/', MarketBackupListView.as_view(), name='market_backup_view'),
    path('backup/list/', MarketBackupListView.as_view(), name='market_backup_list'),
    path('backup/scroll/', MarketBackupScrollView.as_view(), name='market_backup_scroll'),
    path('backup/bulk-delete/', MarketBackupBulkDeleteView.as_view(), name='market_backup_bulk_delete'),
    path('backup/create/', MarketBackupCreateView.as_view(), name='market_backup_create'),
    path('backup/<int:pk>/', MarketBackupDetailView.as_view(), name='market_backup_detail'),
    path('backup/<int:pk>/preview/', MarketBackupPreviewView.as_view(), name='market_backup_preview'),
    path('backup/<int:pk>/chart/', MarketBackupChartView.as_view(), name='market_backup_chart'),
    path('backup/<int:pk>/download/', MarketBackupDownloadView.as_view(), name='market_backup_download'),
    path('backup/<int:pk>/control/', MarketBackupControlView.as_view(), name='market_backup_control'),
    path('backup/<int:pk>/delete/', MarketBackupDeleteView.as_view(), name='market_backup_delete'),
    path('backup/<int:pk>/status/', MarketBackupStatusView.as_view(), name='market_backup_status'),
]