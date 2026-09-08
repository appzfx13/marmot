from django.contrib import admin
from .models import BrokerMaster, UserTradingAccount, TradeExecConfig, LiveStrategy, DailyPortfolioSnapshot


@admin.register(BrokerMaster)
class BrokerMasterAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'is_active', 'created_at')
    search_fields = ('name', 'code')


@admin.register(UserTradingAccount)
class UserTradingAccountAdmin(admin.ModelAdmin):
    list_display = ('account_name', 'user', 'broker', 'account_type', 'is_default', 'is_active', 'is_configured')
    list_filter = ('account_type', 'is_default', 'is_active', 'broker')
    search_fields = ('account_name', 'user__username', 'broker_client_id')


@admin.register(TradeExecConfig)
class TradeExecConfigAdmin(admin.ModelAdmin):
    list_display = ('name', 'admins_user', 'account_type', 'market_type', 'is_active', 'execution_status', 'realtime_pnl')
    list_filter = ('account_type', 'market_type', 'is_active', 'execution_status')
    search_fields = ('name', 'admins_user__username')


@admin.register(LiveStrategy)
class LiveStrategyAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'strategy_name', 'index_name', 'is_active', 'status', 'realtime_pnl', 'total_trades')
    list_filter = ('strategy_name', 'is_active', 'status', 'execution_mode')
    search_fields = ('name', 'user__username', 'index_name')


@admin.register(DailyPortfolioSnapshot)
class DailyPortfolioSnapshotAdmin(admin.ModelAdmin):
    list_display = ('date', 'user', 'trading_account', 'account_type', 'net_pnl', 'total_trades', 'closing_balance')
    list_filter = ('account_type', 'date')
    search_fields = ('user__username', 'trading_account__account_name')
    date_hierarchy = 'date'

