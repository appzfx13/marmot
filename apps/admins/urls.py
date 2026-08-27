from django.urls import path
from .views import (
    AdminLoginView,
    AdminDashboardView,
    AdminTerminalView,
    AdminLogoutView,
    AdminTraderListView,
    AdminTraderScrollView,
    AdminTraderCreateView,
    AdminTraderDetailView,
    AdminTraderUpdateView,
    AdminTraderDeleteView,
    AdminTraderPasswordResetView,
    # Trade Exec Config Views
    AdminTradeExecConfigListView,
    AdminTradeExecConfigScrollView,
    AdminTradeExecConfigCreateView,
    AdminTradeExecConfigDetailView,
    AdminTradeExecConfigUpdateView,
    AdminTradeExecConfigDeleteView,
    AdminTradeExecConfigToggleView,
    AdminTradeExecUserAccountInfoView,
    # Postback Views
    PostbackLogListView,
    PostbackLogScrollView,
    PostbackLogDetailView,
    # Broker Master Views
    AdminBrokerMasterListView,
    AdminBrokerMasterCreateModalView,
    AdminBrokerMasterSaveView,
    AdminBrokerMasterUpdateModalView,
    AdminBrokerMasterDeleteModalView,
    AdminBrokerMasterDeleteView,
    AdminTraderBulkDeleteView,
    AdminTradeExecConfigBulkDeleteView,
    PostbackLogBulkDeleteView,
    AdminBrokerMasterBulkDeleteView,
    AdminLiveDashboardView,
    AdminSandboxDashboardView,
)

from apps.market.views import MarketBackupListView, MarketBackupChartView, MarketBackupBulkDeleteView
from apps.backtest.views import BacktestDashboardView, BacktestBulkDeleteView

app_name = 'admins' 

urlpatterns = [
    # Auth & Dashboards
    path('login/', AdminLoginView.as_view(), name='admin-login'),
    path('dashboard/', AdminDashboardView.as_view(), name='admin-dashboard'),
    path('dashboard/live/', AdminLiveDashboardView.as_view(), name='admin-live-dashboard'),
    path('dashboard/sandbox/', AdminSandboxDashboardView.as_view(), name='admin-sandbox-dashboard'),
    path('terminal/', AdminTerminalView.as_view(), name='admin-terminal'),
    path('logout/', AdminLogoutView.as_view(), name='admin-logout'),

    # Control Routes for Market Backup & Backtest
    path('market-backup/', MarketBackupListView.as_view(), name='market_backup_list'),
    path('market-backup/bulk-delete/', MarketBackupBulkDeleteView.as_view(), name='market_backup_bulk_delete'),
    path('market-backup/<int:pk>/chart/', MarketBackupChartView.as_view(), name='market_backup_chart'),
    path('backtest/', BacktestDashboardView.as_view(), name='backtest_dashboard'),
    path('backtest/bulk-delete/', BacktestBulkDeleteView.as_view(), name='backtest_bulk_delete'),

    # Traders Management (Aligned with template route names)
    path('traders/', AdminTraderListView.as_view(), name='trader_list'),
    path('traders/scroll/', AdminTraderScrollView.as_view(), name='trader_scroll'),
    path('traders/bulk-delete/', AdminTraderBulkDeleteView.as_view(), name='trader_bulk_delete'),
    path('traders/create/', AdminTraderCreateView.as_view(), name='trader_create'),
    path('traders/<int:pk>/', AdminTraderDetailView.as_view(), name='trader_detail'),
    path('traders/<int:pk>/edit/', AdminTraderUpdateView.as_view(), name='trader_edit'),
    path('traders/<int:pk>/delete/', AdminTraderDeleteView.as_view(), name='trader_delete'),
    path('traders/<int:pk>/password-reset/', AdminTraderPasswordResetView.as_view(), name='trader_password_reset'),

    # Postback & Webhook Audit Logs
    path('postbacks/', PostbackLogListView.as_view(), name='postback_list'),
    path('postbacks/scroll/', PostbackLogScrollView.as_view(), name='postback_scroll'),
    path('postbacks/bulk-delete/', PostbackLogBulkDeleteView.as_view(), name='postback_bulk_delete'),
    path('postbacks/<int:pk>/', PostbackLogDetailView.as_view(), name='postback_detail'),

    # Trade Execution Configurations
    path('trade-configs/', AdminTradeExecConfigListView.as_view(), name='trade_exec_config_list'),
    path('trade-configs/scroll/', AdminTradeExecConfigScrollView.as_view(), name='trade_exec_config_scroll'),
    path('trade-configs/bulk-delete/', AdminTradeExecConfigBulkDeleteView.as_view(), name='trade_exec_config_bulk_delete'),
    path('trade-configs/create/', AdminTradeExecConfigCreateView.as_view(), name='trade_exec_config_create'),
    path('trade-configs/user-account-info/', AdminTradeExecUserAccountInfoView.as_view(), name='trade_exec_user_account_info'),
    path('trade-configs/<int:pk>/', AdminTradeExecConfigDetailView.as_view(), name='trade_exec_config_detail'),
    path('trade-configs/<int:pk>/edit/', AdminTradeExecConfigUpdateView.as_view(), name='trade_exec_config_edit'),
    path('trade-configs/<int:pk>/delete/', AdminTradeExecConfigDeleteView.as_view(), name='trade_exec_config_delete'),
    path('trade-configs/<int:pk>/toggle/', AdminTradeExecConfigToggleView.as_view(), name='trade_exec_config_toggle'),

    # Master Brokers Management
    path('masters/brokers/', AdminBrokerMasterListView.as_view(), name='broker-master-list'),
    path('masters/brokers/bulk-delete/', AdminBrokerMasterBulkDeleteView.as_view(), name='broker-master-bulk-delete'),
    path('masters/brokers/create-modal/', AdminBrokerMasterCreateModalView.as_view(), name='broker-master-create-modal'),
    path('masters/brokers/create/', AdminBrokerMasterSaveView.as_view(), name='broker-master-create'),
    path('masters/brokers/<int:pk>/edit-modal/', AdminBrokerMasterUpdateModalView.as_view(), name='broker-master-edit-modal'),
    path('masters/brokers/<int:pk>/edit/', AdminBrokerMasterSaveView.as_view(), name='broker-master-edit'),
    path('masters/brokers/<int:pk>/delete-modal/', AdminBrokerMasterDeleteModalView.as_view(), name='broker-master-delete-modal'),
    path('masters/brokers/<int:pk>/delete/', AdminBrokerMasterDeleteView.as_view(), name='broker-master-delete'),
]