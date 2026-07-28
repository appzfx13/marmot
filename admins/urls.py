from django.urls import path
from .views import (
    AdminMarmotTraderListView,
    AdminMarmotTraderCreateView,
    AdminMarmotTraderDetailView,  # <--- Import here
    AdminMarmotTraderUpdateView,
    AdminMarmotTraderDeleteView,
)

app_name = 'admins' 

urlpatterns = [
    path('marmot/traders/', AdminMarmotTraderListView.as_view(), name='marmot_trader_list'),
    path('marmot/traders/create/', AdminMarmotTraderCreateView.as_view(), name='marmot_trader_create'),
    path('marmot/traders/<int:pk>/', AdminMarmotTraderDetailView.as_view(), name='marmot_trader_detail'),  # <--- Added detail path
    path('marmot/traders/<int:pk>/edit/', AdminMarmotTraderUpdateView.as_view(), name='marmot_trader_edit'),
    path('marmot/traders/<int:pk>/delete/', AdminMarmotTraderDeleteView.as_view(), name='marmot_trader_delete'),
]