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
)

app_name = 'admins' 

urlpatterns = [
    # Auth & Dashboard
    path('login/', AdminLoginView.as_view(), name='admin-login'),
    path('dashboard/', AdminDashboardView.as_view(), name='admin-dashboard'),
    path('logout/', AdminLogoutView.as_view(), name='admin-logout'),

    # Traders Management (Aligned with template route names)
    path('traders/', AdminTraderListView.as_view(), name='trader_list'),
    path('traders/create/', AdminTraderCreateView.as_view(), name='trader_create'),
    path('traders/<int:pk>/', AdminTraderDetailView.as_view(), name='trader_detail'),
    path('traders/<int:pk>/edit/', AdminTraderUpdateView.as_view(), name='trader_edit'),
    path('traders/<int:pk>/delete/', AdminTraderDeleteView.as_view(), name='trader_delete'),

    # Trade Execution Configurations
    path('trade-configs/', AdminTradeExecConfigListView.as_view(), name='trade_exec_config_list'),
    path('trade-configs/create/', AdminTradeExecConfigCreateView.as_view(), name='trade_exec_config_create'),
    path('trade-configs/<int:pk>/', AdminTradeExecConfigDetailView.as_view(), name='trade_exec_config_detail'),
    path('trade-configs/<int:pk>/edit/', AdminTradeExecConfigUpdateView.as_view(), name='trade_exec_config_edit'),
    path('trade-configs/<int:pk>/delete/', AdminTradeExecConfigDeleteView.as_view(), name='trade_exec_config_delete'),
]