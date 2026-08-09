from django.urls import path
from .views import (
    MarketBackupListView,
    MarketBackupCreateView,
    MarketBackupDetailView,
    MarketBackupChartView,
    MarketBackupDownloadView,
    MarketBackupControlView,
    MarketBackupDeleteView,
)

app_name = 'market'

urlpatterns = [
    # Backup Dashboard / List
    path('backup/', MarketBackupListView.as_view(), name='market_backup_view'),
    path('backup/list/', MarketBackupListView.as_view(), name='market_backup_list'),
    path('backup/create/', MarketBackupCreateView.as_view(), name='market_backup_create'),
    path('backup/<int:pk>/', MarketBackupDetailView.as_view(), name='market_backup_detail'),
    path('backup/<int:pk>/chart/', MarketBackupChartView.as_view(), name='market_backup_chart'),
    path('backup/<int:pk>/download/', MarketBackupDownloadView.as_view(), name='market_backup_download'),
    path('backup/<int:pk>/control/', MarketBackupControlView.as_view(), name='market_backup_control'),
    path('backup/<int:pk>/delete/', MarketBackupDeleteView.as_view(), name='market_backup_delete'),
]