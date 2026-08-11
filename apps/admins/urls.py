from django.urls import path
from .views import (
    AdminLoginView,
    AdminDashboardView,
    AdminLogoutView,
    AdminTraderListView,
    AdminTraderCreateView,
    AdminTraderDetailView,
    AdminTraderUpdateView,
    AdminTraderDeleteView,
    AdminTraderPasswordResetView,
    # Trade Exec Config Views
    AdminTradeExecConfigListView,
    AdminTradeExecConfigCreateView,
    AdminTradeExecConfigDetailView,
    AdminTradeExecConfigUpdateView,
    AdminTradeExecConfigDeleteView,
    # Postback Views
    PostbackLogListView,
    PostbackLogDetailView,
    # Broker Master Views
    AdminBrokerMasterListView,
    AdminBrokerMasterCreateModalView,
    AdminBrokerMasterSaveView,
    AdminBrokerMasterUpdateModalView,
    AdminBrokerMasterDeleteModalView,
    AdminBrokerMasterDeleteView,
)

from apps.market.views import MarketBackupListView, MarketBackupChartView
from apps.backtest.views import BacktestDashboardView

app_name = 'admins' 

urlpatterns = [
    # Auth & Dashboard
    path('login/', AdminLoginView.as_view(), name='admin-login'),
    path('dashboard/', AdminDashboardView.as_view(), name='admin-dashboard'),
    path('logout/', AdminLogoutView.as_view(), name='admin-logout'),

    # Control Routes for Market Backup & Backtest
    path('market-backup/', MarketBackupListView.as_view(), name='market_backup_list'),
    path('market-backup/<int:pk>/chart/', MarketBackupChartView.as_view(), name='market_backup_chart'),
    path('backtest/', BacktestDashboardView.as_view(), name='backtest_dashboard'),

    # Traders Management (Aligned with template route names)
    path('traders/', AdminTraderListView.as_view(), name='trader_list'),
    path('traders/create/', AdminTraderCreateView.as_view(), name='trader_create'),
    path('traders/<int:pk>/', AdminTraderDetailView.as_view(), name='trader_detail'),
    path('traders/<int:pk>/edit/', AdminTraderUpdateView.as_view(), name='trader_edit'),
    path('traders/<int:pk>/delete/', AdminTraderDeleteView.as_view(), name='trader_delete'),
    path('traders/<int:pk>/password-reset/', AdminTraderPasswordResetView.as_view(), name='trader_password_reset'),

    # Postback & Webhook Audit Logs
    path('postbacks/', PostbackLogListView.as_view(), name='postback_list'),
    path('postbacks/<int:pk>/', PostbackLogDetailView.as_view(), name='postback_detail'),

    # Trade Execution Configurations
    path('trade-configs/', AdminTradeExecConfigListView.as_view(), name='trade_exec_config_list'),
    path('trade-configs/create/', AdminTradeExecConfigCreateView.as_view(), name='trade_exec_config_create'),
    path('trade-configs/<int:pk>/', AdminTradeExecConfigDetailView.as_view(), name='trade_exec_config_detail'),
    path('trade-configs/<int:pk>/edit/', AdminTradeExecConfigUpdateView.as_view(), name='trade_exec_config_edit'),
    path('trade-configs/<int:pk>/delete/', AdminTradeExecConfigDeleteView.as_view(), name='trade_exec_config_delete'),

    # Master Brokers Management
    path('masters/brokers/', AdminBrokerMasterListView.as_view(), name='broker-master-list'),
    path('masters/brokers/create-modal/', AdminBrokerMasterCreateModalView.as_view(), name='broker-master-create-modal'),
    path('masters/brokers/create/', AdminBrokerMasterSaveView.as_view(), name='broker-master-create'),
    path('masters/brokers/<int:pk>/edit-modal/', AdminBrokerMasterUpdateModalView.as_view(), name='broker-master-edit-modal'),
    path('masters/brokers/<int:pk>/edit/', AdminBrokerMasterSaveView.as_view(), name='broker-master-edit'),
    path('masters/brokers/<int:pk>/delete-modal/', AdminBrokerMasterDeleteModalView.as_view(), name='broker-master-delete-modal'),
    path('masters/brokers/<int:pk>/delete/', AdminBrokerMasterDeleteView.as_view(), name='broker-master-delete'),
]