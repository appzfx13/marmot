from django.urls import path
from .views import (
    BacktestDashboardView,
    BacktestCreateView,
    BacktestDetailView,
    BacktestTradesScrollView,
    BacktestDashboardScrollView,
    BacktestControlView,
    BacktestEditModalView,
    BacktestStatusView,
    BacktestDeleteView,
    BacktestBulkDeleteView,
    StrategyListView,
    StrategyDetailView,
    StrategySaveCodeView,
    StrategyDeleteView,
    BacktestRuleListView,
    BacktestRuleCreateView,
    BacktestRuleUpdateView,
    BacktestRuleDeleteView,
    BacktestRuleToggleView,
    RLTrainingIndexView,
    RLTrainingForexView,
    BacktestExportExcelView,
    BacktestTradeCandlesView,
    BacktestTradeChartView,
    BacktestLogsModalView,
    BacktestApplyAiRuleView,
)

app_name = 'backtest'

urlpatterns = [
    # RL AI Engine Dedicated Portals
    path('rl-training/index-fo/', RLTrainingIndexView.as_view(), name='rl_training_index_fo'),
    path('rl-training/forex-futures/', RLTrainingForexView.as_view(), name='rl_training_forex_futures'),
    path('list/', BacktestDashboardView.as_view(), name='backtest_dashboard'),
    path('scroll/', BacktestDashboardScrollView.as_view(), name='backtest_dashboard_scroll'),
    path('bulk-delete/', BacktestBulkDeleteView.as_view(), name='backtest_bulk_delete'),
    path('create/', BacktestCreateView.as_view(), name='backtest_create'),
    path('<int:pk>/', BacktestDetailView.as_view(), name='backtest_detail'),
    path('<int:pk>/export-excel/', BacktestExportExcelView.as_view(), name='backtest_export_excel'),
    path('<int:pk>/trades-scroll/', BacktestTradesScrollView.as_view(), name='backtest_trades_scroll'),
    path('<int:pk>/trade/<int:trade_num>/candles/', BacktestTradeCandlesView.as_view(), name='backtest_trade_candles'),
    path('<int:pk>/trade/<int:trade_num>/chart/', BacktestTradeChartView.as_view(), name='backtest_trade_chart'),
    path('<int:pk>/logs/', BacktestLogsModalView.as_view(), name='backtest_logs_modal'),
    path('<int:pk>/apply-ai-rule/', BacktestApplyAiRuleView.as_view(), name='backtest_apply_ai_rule'),
    path('<int:pk>/status/', BacktestStatusView.as_view(), name='backtest_status'),
    path('<int:pk>/control/', BacktestControlView.as_view(), name='backtest_control'),
    path('<int:pk>/edit-modal/', BacktestEditModalView.as_view(), name='backtest_edit_modal'),
    path('<int:pk>/delete/', BacktestDeleteView.as_view(), name='backtest_delete'),
    
    # Strategy Hub & Web UI Code Editor Endpoints
    path('strategies/', StrategyListView.as_view(), name='strategy_list'),
    path('strategies/<int:pk>/', StrategyDetailView.as_view(), name='strategy_detail'),
    path('strategies/<int:pk>/save-code/', StrategySaveCodeView.as_view(), name='strategy_save_code'),
    path('strategies/<int:pk>/delete/', StrategyDeleteView.as_view(), name='strategy_delete'),

    # Rule Management & CRUD Endpoints
    path('rules/', BacktestRuleListView.as_view(), name='rule_list'),
    path('rules/create/', BacktestRuleCreateView.as_view(), name='rule_create'),
    path('rules/<int:pk>/edit/', BacktestRuleUpdateView.as_view(), name='rule_update'),
    path('rules/<int:pk>/delete/', BacktestRuleDeleteView.as_view(), name='rule_delete'),
    path('rules/<int:pk>/toggle/', BacktestRuleToggleView.as_view(), name='rule_toggle'),
]
