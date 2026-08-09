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
    # Trade Exec Config Views
    AdminTradeExecConfigListView,
    AdminTradeExecConfigCreateView,
    AdminTradeExecConfigDetailView,
    AdminTradeExecConfigUpdateView,
    AdminTradeExecConfigDeleteView,
    # Postback Views
    PostbackLogListView,
    PostbackLogDetailView,
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

    # Postback & Webhook Audit Logs
    path('postbacks/', PostbackLogListView.as_view(), name='postback_list'),
    path('postbacks/<int:pk>/', PostbackLogDetailView.as_view(), name='postback_detail'),

    # Trade Execution Configurations
    path('trade-configs/', AdminTradeExecConfigListView.as_view(), name='trade_exec_config_list'),
    path('trade-configs/create/', AdminTradeExecConfigCreateView.as_view(), name='trade_exec_config_create'),
    path('trade-configs/<int:pk>/', AdminTradeExecConfigDetailView.as_view(), name='trade_exec_config_detail'),
    path('trade-configs/<int:pk>/edit/', AdminTradeExecConfigUpdateView.as_view(), name='trade_exec_config_edit'),
    path('trade-configs/<int:pk>/delete/', AdminTradeExecConfigDeleteView.as_view(), name='trade_exec_config_delete'),
]