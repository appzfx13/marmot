from django.urls import path
from .views import (
    MarketBackupListView,
    MarketBackupCreateView,
    MarketBackupDetailView,
    MarketBackupPreviewView,
    MarketBackupScrollView,
    MarketBackupChartView,
    MarketBackupCandlesView,
    MarketBackupDownloadView,
    MarketBackupControlView,
    MarketBackupDeleteView,
    MarketBackupBulkDeleteView,
    MarketBackupStatusView,
    MacroBackupModalView,
    MacroBackupCreateView,
    MacroBackupCreatePageView,
    MacroBackupListView,
    DailyTicksListView,
    DailyTicksMergeActionView,
    DailyTicksDownloadView,
)

app_name = 'market'

urlpatterns = [
    # Daily 1S Ticks & Consolidated Datasets
    path('backup/daily-ticks/', DailyTicksListView.as_view(), name='daily_ticks_list'),
    path('backup/daily-ticks/<str:date_str>/merge/', DailyTicksMergeActionView.as_view(), name='daily_ticks_merge'),
    path('backup/daily-ticks/<str:date_str>/download/<str:file_type>/', DailyTicksDownloadView.as_view(), name='daily_ticks_download'),
    # Backup Dashboard / List
    path('backup/', MarketBackupListView.as_view(), name='market_backup_view'),
    path('backup/list/', MarketBackupListView.as_view(), name='market_backup_list'),
    path('backup/scroll/', MarketBackupScrollView.as_view(), name='market_backup_scroll'),
    path('backup/bulk-delete/', MarketBackupBulkDeleteView.as_view(), name='market_backup_bulk_delete'),
    path('backup/create/', MarketBackupCreateView.as_view(), name='market_backup_create'),
    # AI Macro Assist Suite
    path('backup/macro/', MacroBackupListView.as_view(), name='market_macro_backup_list'),
    path('backup/macro/list/', MacroBackupListView.as_view(), name='market_macro_backup_list_alias'),
    path('backup/macro/create/', MacroBackupCreatePageView.as_view(), name='market_macro_backup_create_page'),
    path('backup/macro-modal/', MacroBackupModalView.as_view(), name='market_macro_backup_modal'),
    path('backup/macro-create/', MacroBackupCreateView.as_view(), name='market_macro_backup_create'),
    path('backup/macro/<int:pk>/', MarketBackupDetailView.as_view(), name='market_macro_backup_detail'),
    path('backup/<int:pk>/', MarketBackupDetailView.as_view(), name='market_backup_detail'),
    path('backup/<int:pk>/preview/', MarketBackupPreviewView.as_view(), name='market_backup_preview'),
    path('backup/<int:pk>/chart/', MarketBackupChartView.as_view(), name='market_backup_chart'),
    path('backup/<int:pk>/candles/', MarketBackupCandlesView.as_view(), name='market_backup_candles'),
    path('backup/<int:pk>/download/', MarketBackupDownloadView.as_view(), name='market_backup_download'),
    path('backup/<int:pk>/control/', MarketBackupControlView.as_view(), name='market_backup_control'),
    path('backup/<int:pk>/delete/', MarketBackupDeleteView.as_view(), name='market_backup_delete'),
    path('backup/<int:pk>/status/', MarketBackupStatusView.as_view(), name='market_backup_status'),
]