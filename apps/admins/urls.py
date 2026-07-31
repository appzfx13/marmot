from django.urls import path
from .views import (
    AdminLoginView,
    AdminDashboardView,
    AdminLogoutView,
    AdminMarmotTraderListView,
    AdminMarmotTraderCreateView,
    AdminMarmotTraderDetailView,
    AdminMarmotTraderUpdateView,
    AdminMarmotTraderDeleteView,
)

app_name = 'admins' 

urlpatterns = [
    # Auth & Dashboard
    path('login/', AdminLoginView.as_view(), name='admin-login'),
    path('dashboard/', AdminDashboardView.as_view(), name='admin-dashboard'),
    path('logout/', AdminLogoutView.as_view(), name='admin-logout'),

    # Marmot Traders Management
    path('marmot/traders/', AdminMarmotTraderListView.as_view(), name='marmot_trader_list'),
    path('marmot/traders/create/', AdminMarmotTraderCreateView.as_view(), name='marmot_trader_create'),
    path('marmot/traders/<int:pk>/', AdminMarmotTraderDetailView.as_view(), name='marmot_trader_detail'),
    path('marmot/traders/<int:pk>/edit/', AdminMarmotTraderUpdateView.as_view(), name='marmot_trader_edit'),
    path('marmot/traders/<int:pk>/delete/', AdminMarmotTraderDeleteView.as_view(), name='marmot_trader_delete'),
]