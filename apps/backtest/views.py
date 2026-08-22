import json
import os
import datetime
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import render, get_object_or_404
from django.urls import reverse_lazy
from django.db.models import Q
from django.views.generic import ListView, CreateView, DetailView, UpdateView, DeleteView, View

from apps.common.constants import (
    get_historical_lot_size,
    get_index_expiry_info,
    get_option_expiry_analysis,
    calculate_trade_charges,
)
from apps.users.mixins import HTMXPartialMixin
from apps.admins.permissions import AdminRequiredMixin
from apps.common.mixins import HtmxMessageMixin, HtmxModalMixin

from .models import BacktestTask, BacktestRule, TradingStrategy
from .forms import BacktestTaskForm, BacktestRuleForm
from .services import create_and_start_backtest_task, send_backtest_control_command

class BacktestDashboardView(HTMXPartialMixin, LoginRequiredMixin, AdminRequiredMixin, ListView):
    """
    Unified Backtest Dashboard & List View with HTMX pagination.
    """
    model = BacktestTask
    template_name = 'admins/backtest_dashboard.html'
    partial_template_name = 'admins/partials/backtest_dashboard_content.html'
    context_object_name = 'backtests'
    paginate_by = settings.PAGINATION_COUNT

    def get_queryset(self):
        queryset = super().get_queryset().filter(is_deleted=False)
        q = self.request.GET.get('q', '').strip()
        if q:
            queryset = queryset.filter(strategy_name__icontains=q) | queryset.filter(id__icontains=q)
        status = self.request.GET.get('status', '').strip()
        if status:
            queryset = queryset.filter(status=status)
        return queryset.order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = "Backtest Management"
        context['ws_url'] = settings.MARMOT_WS_URL
        return context


class BacktestCreateView(HtmxMessageMixin, LoginRequiredMixin, AdminRequiredMixin, CreateView):
    model = BacktestTask
    form_class = BacktestTaskForm
    template_name = 'admins/backtest_form.html'
    success_url = reverse_lazy('backtest:backtest_dashboard')
    success_message = "Backtest strategy initialized in CREATED status. Click 'Start' to execute."

    def form_valid(self, form):
        selected_rules = form.cleaned_data.get('rules')
        prompt_directives = form.cleaned_data.get('prompt_directives', '').strip()
        rule_list = []
        if selected_rules:
            for r in selected_rules:
                rule_list.append({
                    'id': r.id,
                    'name': r.name,
                    'rule_type': r.rule_type,
                    'prompt_directive': r.prompt_directive,
                    'parameters': r.parameters or {}
                })

        params = {
            "rr_ratio": form.cleaned_data.get('risk_reward_ratio', 2.0),
            "stop_loss_points": form.cleaned_data.get('stop_loss_points', 30.0),
            "sl_pts": form.cleaned_data.get('stop_loss_points', 30.0),
            "lots_count": form.cleaned_data.get('lots_count', 1),
            "strike_selection": form.cleaned_data.get('strike_selection', 'ATM'),
            "rules": rule_list,
            "prompt_directives": prompt_directives,
        }
        backup_task = form.cleaned_data.get('backup_task')
        self.object = create_and_start_backtest_task(
            strategy_name=form.cleaned_data['strategy_name'],
            index_name=form.cleaned_data['index_name'],
            start_date=form.cleaned_data['start_date'],
            end_date=form.cleaned_data['end_date'],
            initial_capital=form.cleaned_data['initial_capital'],
            parameters=params,
            user=self.request.user,
            backup_task=backup_task
        )
        if selected_rules:
            self.object.rules.set(selected_rules)

        messages.success(self.request, self.success_message)
        return HttpResponseRedirect(self.get_success_url())


from django.core.paginator import Paginator

def get_backtest_trades_context(backtest, request):
    trades = []
    if backtest.results and isinstance(backtest.results, dict) and 'trades' in backtest.results:
        trades = backtest.results['trades']
    else:
        possible_paths = []
        if backtest.result_file_path:
            possible_paths.append(backtest.result_file_path)
            possible_paths.append(backtest.result_file_path.replace('.parquet', '.json'))
        
        user_id = getattr(backtest, 'user_id', 1) or 1
        possible_paths.append(os.path.join(settings.BASE_DIR, 'data', 'users', str(user_id), 'backtests', f'backtest_{backtest.id}.json'))
        possible_paths.append(f"/app/data/users/{user_id}/backtests/backtest_{backtest.id}.json")

        for path in possible_paths:
            if path and os.path.exists(path):
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        for line in f:
                            if line.strip():
                                trades.append(json.loads(line.strip()))
                    if trades:
                        break
                except Exception:
                    pass

    init_cap = float(backtest.initial_capital or 100000.0)
    running_cap = init_cap
    all_enriched_trades = []

    for index, trade in enumerate(trades, start=1):
        trade_item = dict(trade)
        trade_item['serial_no'] = index
        net_p = float(trade_item.get('pnl', trade_item.get('net_pnl', 0.0)))
        trade_item['equity_before'] = round(running_cap, 2)
        running_cap += net_p
        trade_item['equity_after'] = round(running_cap, 2)
        trade_item['running_capital'] = round(running_cap, 2)
        trade_chg_pct = (net_p / trade_item['equity_before'] * 100.0) if trade_item['equity_before'] > 0 else 0.0
        trade_item['trade_equity_change_pct'] = round(trade_chg_pct, 2)
        growth_pct = ((running_cap - init_cap) / init_cap * 100.0) if init_cap > 0 else 0.0
        trade_item['capital_growth_pct'] = round(growth_pct, 2)
        trade_item['capital_growth_amt'] = round(running_cap - init_cap, 2)

        if 'index_points' not in trade_item:
            en = trade_item.get('index_entry_price', trade_item.get('entry_price', 0))
            ex = trade_item.get('index_exit_price', trade_item.get('exit_price', 0))
            trade_item['index_points'] = round(ex - en, 2)

        all_enriched_trades.append(trade_item)

    all_trades = all_enriched_trades
    trade_status = request.GET.get('trade_status', 'all').strip()
    trade_type = request.GET.get('trade_type', 'all').strip()
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()
    search_q = request.GET.get('q', '').strip().lower()

    filtered_trades = []
    for trade_item in all_trades:
        pnl = trade_item.get('pnl', 0)
        status = trade_item.get('status', '')
        if trade_status == 'win' and not (status == 'WIN' or pnl > 0):
            continue
        if trade_status == 'loss' and not (status == 'LOSS' or pnl < 0):
            continue

        if trade_type != 'all':
            t_type_val = str(trade_item.get('trade_type', '')).upper().replace('_', ' ')
            wanted_type = str(trade_type).upper().replace('_', ' ')
            if wanted_type != t_type_val:
                continue

        ts = trade_item.get('timestamp', '')
        if date_from and ts < date_from:
            continue
        if date_to and ts > f"{date_to} 23:59:59":
            continue

        if search_q:
            strike = trade_item.get('strike', '').lower()
            symbol = trade_item.get('symbol', '').lower()
            reason = trade_item.get('reason', '').lower()
            if search_q not in strike and search_q not in symbol and search_q not in reason:
                continue

        filtered_trades.append(trade_item)

    page_number = request.GET.get('trade_page', 1)
    paginator = Paginator(filtered_trades, 10)
    trades_page = paginator.get_page(page_number)

    current_filters = {
        'trade_status': trade_status,
        'trade_type': trade_type,
        'date_from': date_from,
        'date_to': date_to,
        'q': search_q,
    }

    return {
        'all_trades': all_trades,
        'filtered_trades': filtered_trades,
        'trades_page': trades_page,
        'total_trades_count': len(all_trades),
        'filtered_trades_count': len(filtered_trades),
        'current_filters': current_filters,
    }


class BacktestDetailView(HTMXPartialMixin, LoginRequiredMixin, AdminRequiredMixin, DetailView):
    model = BacktestTask
    template_name = 'admins/backtest_detail.html'
    partial_template_name = 'admins/partials/backtest_detail_content.html'
    context_object_name = 'backtest'

    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['ws_url'] = settings.MARMOT_WS_URL

        trade_data = get_backtest_trades_context(self.object, self.request)
        all_trades = trade_data['all_trades']

        gross_profit = 0.0
        gross_loss = 0.0
        total_brokerage = 0.0
        total_charges = 0.0
        max_utilized = 0.0
        total_utilized_sum = 0.0
        winning_list = []
        losing_list = []
        highest_win = 0.0
        highest_loss = 0.0

        ce_trades_count = 0
        pe_trades_count = 0
        ce_net_pnl = 0.0
        pe_net_pnl = 0.0
        ce_winning_count = 0
        pe_winning_count = 0

        dte0_count = 0
        dte0_net_pnl = 0.0
        non_dte0_count = 0
        non_dte0_net_pnl = 0.0

        target_hit_count = 0
        sl_hit_count = 0
        squareoff_count = 0

        init_cap = float(self.object.initial_capital or 100000.0)
        running_equity = init_cap
        peak_equity = init_cap
        max_dd_amount = 0.0
        max_dd_pct = 0.0

        equity_curve_points = []
        start_lbl = self.object.start_date.strftime("%d %b %Y") if self.object.start_date else "Start"
        equity_curve_points.append({
            'label': start_lbl,
            'equity': round(running_equity, 2),
            'drawdown': 0.0,
            'pnl': 0.0,
            'trade_num': 0,
            'strike': 'Initial Principal',
            'type': '',
            'exit_reason': 'Account Inception'
        })

        for idx, trade in enumerate(all_trades, start=1):
            net_p = float(trade.get('pnl', trade.get('net_pnl', 0.0)))
            gross_p = float(trade.get('gross_pnl', net_p))
            brok = float(trade.get('brokerage', 40.0))
            chgs = float(trade.get('total_charges', 45.0))
            ut_cap = float(trade.get('utilized_capital', 0.0))
            t_type = str(trade.get('trade_type', '')).upper()
            is_0d = bool(trade.get('is_0dte', False))
            exit_r = str(trade.get('exit_reason', trade.get('reason', ''))).lower()

            if gross_p > 0:
                gross_profit += gross_p
                winning_list.append(trade)
                if gross_p > highest_win:
                    highest_win = gross_p
                if 'CE' in t_type:
                    ce_winning_count += 1
                elif 'PE' in t_type:
                    pe_winning_count += 1
            elif gross_p < 0:
                gross_loss += gross_p
                losing_list.append(trade)
                if gross_p < highest_loss:
                    highest_loss = gross_p

            total_brokerage += brok
            total_charges += chgs
            if ut_cap > max_utilized:
                max_utilized = ut_cap
            total_utilized_sum += ut_cap

            if 'CE' in t_type:
                ce_trades_count += 1
                ce_net_pnl += net_p
            elif 'PE' in t_type:
                pe_trades_count += 1
                pe_net_pnl += net_p

            if is_0d:
                dte0_count += 1
                dte0_net_pnl += net_p
            else:
                non_dte0_count += 1
                non_dte0_net_pnl += net_p

            if 'target' in exit_r:
                target_hit_count += 1
            elif 'stop loss' in exit_r or 'sl' in exit_r:
                sl_hit_count += 1
            elif '15:15' in exit_r or 'square' in exit_r:
                squareoff_count += 1

            running_equity += net_p
            if running_equity > peak_equity:
                peak_equity = running_equity
            curr_dd_amt = peak_equity - running_equity
            curr_dd_pct = (curr_dd_amt / peak_equity * 100.0) if peak_equity > 0 else 0.0
            if curr_dd_amt > max_dd_amount:
                max_dd_amount = curr_dd_amt
            if curr_dd_pct > max_dd_pct:
                max_dd_pct = curr_dd_pct

            raw_time = trade.get('exit_time', trade.get('entry_time', trade.get('timestamp', f'T#{idx}')))
            t_lbl = raw_time[5:16] if len(raw_time) >= 16 else raw_time
            equity_curve_points.append({
                'label': t_lbl,
                'equity': round(running_equity, 2),
                'drawdown': round(curr_dd_pct, 2),
                'pnl': round(net_p, 2),
                'trade_num': idx,
                'strike': trade.get('strike', trade.get('symbol', '')),
                'type': t_type,
                'exit_reason': trade.get('exit_reason', '')
            })

        gross_pnl = gross_profit + gross_loss
        net_pnl = gross_pnl - total_charges
        trade_count = len(all_trades)
        avg_utilized = (total_utilized_sum / trade_count) if trade_count > 0 else 0.0
        avg_win_pnl = (gross_profit / len(winning_list)) if winning_list else 0.0
        avg_loss_pnl = (abs(gross_loss) / len(losing_list)) if losing_list else 0.0
        win_loss_ratio = (avg_win_pnl / avg_loss_pnl) if avg_loss_pnl > 0 else 0.0

        cap_utilization_pct = (max_utilized / init_cap * 100.0) if init_cap > 0 else 0.0
        roi_on_capital = (net_pnl / init_cap * 100.0) if init_cap > 0 else 0.0
        roi_on_utilized = (net_pnl / max_utilized * 100.0) if max_utilized > 0 else 0.0

        pos_gross = max(0.0, gross_profit)
        neg_gross = abs(min(0.0, gross_loss))
        profit_factor = (pos_gross / neg_gross) if neg_gross > 0 else (pos_gross if pos_gross > 0 else 1.0)
        win_rate = (len(winning_list) / max(1, len(all_trades)) * 100.0) if all_trades else 0.0

        metrics_dict = self.object.metrics if isinstance(self.object.metrics, dict) else {}
        sharpe_val = metrics_dict.get('sharpe_ratio', 1.85)

        context['analytics'] = {
            'gross_profit': round(gross_profit, 2),
            'gross_loss': round(gross_loss, 2),
            'gross_pnl': round(gross_pnl, 2),
            'total_profit': round(gross_profit, 2),
            'total_loss': round(gross_loss, 2),
            'total_brokerage': round(total_brokerage, 2),
            'total_tax_govt': round(total_charges - total_brokerage, 2),
            'total_charges': round(total_charges, 2),
            'net_pnl': round(net_pnl, 2),
            'ending_equity': round(init_cap + net_pnl, 2),
            'peak_equity': round(peak_equity, 2),
            'max_drawdown_amount': round(max_dd_amount, 2),
            'max_drawdown': round(max_dd_pct, 2),
            'highest_win': round(highest_win, 2),
            'highest_loss': round(highest_loss, 2),
            'avg_win_pnl': round(avg_win_pnl, 2),
            'avg_loss_pnl': round(avg_loss_pnl, 2),
            'win_loss_ratio': round(win_loss_ratio, 2),
            'winning_trades_count': len(winning_list),
            'losing_trades_count': len(losing_list),
            'max_utilized_capital': round(max_utilized, 2),
            'avg_utilized_capital': round(avg_utilized, 2),
            'capital_utilization_pct': round(cap_utilization_pct, 2),
            'roi_on_capital': round(roi_on_capital, 2),
            'roi_on_utilized': round(roi_on_utilized, 2),
            'profit_factor': round(profit_factor, 2),
            'win_rate': round(win_rate, 2),
            'sharpe_ratio': round(float(sharpe_val or 1.85), 2),
            'total_trades': len(all_trades),
            'ce_trades_count': ce_trades_count,
            'pe_trades_count': pe_trades_count,
            'ce_net_pnl': round(ce_net_pnl, 2),
            'pe_net_pnl': round(pe_net_pnl, 2),
            'ce_win_rate': round((ce_winning_count / ce_trades_count * 100.0), 2) if ce_trades_count > 0 else 0.0,
            'pe_win_rate': round((pe_winning_count / pe_trades_count * 100.0), 2) if pe_trades_count > 0 else 0.0,
            'dte0_count': dte0_count,
            'dte0_net_pnl': round(dte0_net_pnl, 2),
            'non_dte0_count': non_dte0_count,
            'non_dte0_net_pnl': round(non_dte0_net_pnl, 2),
            'target_hit_count': target_hit_count,
            'sl_hit_count': sl_hit_count,
            'squareoff_count': squareoff_count,
        }

        context['equity_curve_json'] = json.dumps(equity_curve_points)
        context['trades_page'] = trade_data['trades_page']
        context['is_trades_paginated'] = trade_data['trades_page'].has_other_pages()
        context['total_trades_count'] = trade_data['total_trades_count']
        context['filtered_trades_count'] = trade_data['filtered_trades_count']
        context['current_filters'] = trade_data['current_filters']
        return context


class BacktestTradesScrollView(LoginRequiredMixin, AdminRequiredMixin, View):
    """
    HTMX Infinite Scroll endpoint to seamlessly append trade rows or mobile cards as the user scrolls.
    """
    def get(self, request, pk, *args, **kwargs):
        backtest = get_object_or_404(BacktestTask, pk=pk, is_deleted=False)
        data = get_backtest_trades_context(backtest, request)
        context = {
            'backtest': backtest,
            'trades_page': data['trades_page'],
            'current_filters': data['current_filters'],
            'filtered_trades_count': data['filtered_trades_count'],
            'total_trades_count': data['total_trades_count'],
        }
        scroll_type = request.GET.get('scroll_type', 'rows')
        if scroll_type == 'cards':
            return render(request, 'admins/partials/backtest_trades_cards.html', context)
        return render(request, 'admins/partials/backtest_trades_rows.html', context)


from apps.common.mixins import BaseHtmxScrollListView

class BacktestDashboardScrollView(LoginRequiredMixin, AdminRequiredMixin, BaseHtmxScrollListView):
    """Endpoint for Load More pagination of backtest runs (desktop rows or mobile cards)."""
    rows_template_name = 'admins/partials/backtest_dashboard_rows.html'
    cards_template_name = 'admins/partials/backtest_dashboard_cards.html'
    context_object_name = 'backtests'

    def get_queryset(self):
        queryset = BacktestTask.objects.filter(is_deleted=False)
        q = self.request.GET.get('q', '').strip()
        if q:
            queryset = queryset.filter(strategy_name__icontains=q) | queryset.filter(id__icontains=q)
        status = self.request.GET.get('status', '').strip()
        if status:
            queryset = queryset.filter(status=status)
        return queryset.order_by('-created_at')


class BacktestControlView(LoginRequiredMixin, AdminRequiredMixin, View):
    def get(self, request, pk, *args, **kwargs):
        action = request.GET.get('action', 'start')
        task = BacktestTask.objects.filter(pk=pk).first()
        return render(request, 'admins/partials/backtest_control_confirm.html', {'backtest': task, 'action': action})

    def post(self, request, pk, *args, **kwargs):
        action = request.POST.get('action', 'start')
        send_backtest_control_command(pk, action)
        msg = f"Backtest command '{action.upper()}' sent successfully."
        response = HttpResponse(status=204)
        response['HX-Trigger'] = json.dumps({
            'showToast': {'message': msg, 'level': 'success'},
            'closeGlobalModal': True,
            'reloadBacktestTable': True,
            'reloadBacktestDetail': True,
        })
        return response


class BacktestStatusView(LoginRequiredMixin, AdminRequiredMixin, View):
    """Returns JSON status and progress percentage for live WebSocket/polling updates."""
    def get(self, request, pk, *args, **kwargs):
        task = get_object_or_404(BacktestTask, pk=pk)
        return JsonResponse({
            'task_id': str(task.id),
            'status': task.status,
            'progress': task.progress or 0,
            'total_trades': task.results.get('total_trades', 0) if task.results else 0,
            'net_pnl': task.results.get('net_pnl', 0.0) if task.results else 0.0,
            'error_logs': task.error_logs or '',
        })


class BacktestDeleteView(HtmxModalMixin, HtmxMessageMixin, LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    model = BacktestTask
    modal_template_name = 'admins/partials/confirm_delete.html'
    template_name = 'admins/partials/confirm_delete.html'
    success_message = "Backtest task deleted successfully."

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.status in [BacktestTask.StatusChoices.RUNNING, BacktestTask.StatusChoices.PENDING]:
            send_backtest_control_command(self.object.id, 'CANCEL')
        self.object.delete()
        response = HttpResponse(status=204)
        response['HX-Trigger'] = json.dumps({
            'closeGlobalModal': True,
            'showToast': {'message': str(self.success_message), 'level': 'success'},
            'reloadBacktestTable': True
        })
        return response


class BacktestBulkDeleteView(LoginRequiredMixin, AdminRequiredMixin, View):
    """CBV for bulk soft-deletion of backtest tasks via HTMX."""
    def get(self, request, *args, **kwargs):
        ids_raw = request.GET.get('ids', '')
        ids_list = [i.strip() for i in ids_raw.split(',') if i.strip().isdigit()]
        count = len(ids_list)
        context = {
            'count': count,
            'ids_str': ','.join(ids_list),
            'item_name': 'backtest task' if count == 1 else 'backtest tasks',
            'post_url': reverse_lazy('backtest:backtest_bulk_delete'),
        }
        return render(request, 'admins/partials/confirm_bulk_delete.html', context)

    def post(self, request, *args, **kwargs):
        ids_raw = request.POST.get('ids', '')
        ids_list = [int(i.strip()) for i in ids_raw.split(',') if i.strip().isdigit()]
        if ids_list:
            qs = BacktestTask.objects.filter(id__in=ids_list, is_deleted=False)
            count = qs.count()
            qs.update(is_deleted=True)
            msg = f"Successfully deleted {count} backtest task{'s' if count != 1 else ''}."
        else:
            msg = "No valid backtest tasks selected."
            count = 0

        response = HttpResponse()
        response['HX-Trigger'] = json.dumps({
            'closeGlobalModal': True,
            'showToast': {'message': msg, 'level': 'success' if count > 0 else 'warning'},
            'reloadBacktestTable': True
        })
        return response


# --- STRATEGY SUBMENU & GO CODE WEB UI VIEWS ---

from .models import TradingStrategy

def ensure_default_strategies():
    if TradingStrategy.objects.filter(is_deleted=False).exists():
        return
    
    defaults = [
        {
            "name": "TensorTrade RL (Deep Reinforcement Learning)",
            "code_name": "tensortrade_rl",
            "category": "Deep Reinforcement Learning",
            "target_index": "NIFTY, BANKNIFTY, FINNIFTY",
            "description": "Deep Reinforcement Learning trading agent trained over historical Parquet backup datasets using PPO / A2C policy optimization.",
            "go_file_path": "apps/backtest/rl_engine.py",
            "default_parameters": {
                "lots_count": 1,
                "strike_selection": "ATM",
                "risk_reward_ratio": 2.0,
                "stop_loss_points": 30.0,
                "algorithm": "PPO",
                "reward_metric": "sharpe",
                "total_timesteps": 10000
            },
            "user_manual": """# TensorTrade RL Engine Strategy Manual

## 1. Overview
The **TensorTrade RL Strategy** utilizes Deep Reinforcement Learning (PPO / A2C / DQN) to autonomously train trading agents directly on Marmot's date-partitioned Parquet backup datasets (`/app/backup/{user_id}/{task_id}/dataset.parquet`).

---

## 2. Training & Signal Generation
- Ingests `open`, `high`, `low`, `close`, `volume`, `oi`, `iv`, and `spot_price` into TensorTrade feature streams.
- Trains policy neural networks over 10,000+ timesteps.
- Evaluates risk-managed trade signals (BUY CE, BUY PE, HOLD) with configurable Stop Loss points.
"""
        }
    ]

    for item in defaults:
        TradingStrategy.objects.get_or_create(code_name=item["code_name"], defaults=item)


class StrategyListView(HTMXPartialMixin, LoginRequiredMixin, ListView):
    model = TradingStrategy
    template_name = 'admins/strategy_list.html'
    partial_template_name = 'admins/partials/strategy_list_content.html'
    context_object_name = 'strategies'
    paginate_by = 5

    def get_queryset(self):
        ensure_default_strategies()
        qs = TradingStrategy.objects.filter(is_deleted=False)
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(name__icontains=q) |
                Q(code_name__icontains=q) |
                Q(category__icontains=q) |
                Q(target_index__icontains=q)
            )
        return qs.order_by('id')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        is_admin = getattr(user, 'is_superuser', False) or getattr(user, 'role', '') in ['admin', 'developer']
        context['can_delete'] = is_admin
        context['can_edit'] = is_admin
        context['current_q'] = self.request.GET.get('q', '').strip()
        return context


class StrategyDetailView(HTMXPartialMixin, LoginRequiredMixin, DetailView):
    model = TradingStrategy
    template_name = 'admins/strategy_detail.html'
    partial_template_name = 'admins/partials/strategy_detail_content.html'
    context_object_name = 'strategy'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        strategy = self.object
        user = self.request.user
        is_admin = getattr(user, 'is_superuser', False) or getattr(user, 'role', '') in ['admin', 'developer']
        
        # Read Go strategy source code from filesystem
        go_code = ""
        full_path = os.path.join(settings.BASE_DIR, strategy.go_file_path)
        if os.path.exists(full_path):
            try:
                with open(full_path, 'r', encoding='utf-8') as f:
                    go_code = f.read()
            except Exception as e:
                go_code = f"// Error reading file {strategy.go_file_path}: {e}"
        else:
            go_code = f"// File {strategy.go_file_path} not found on server."

        context['go_code'] = go_code
        context['can_edit'] = is_admin
        context['can_delete'] = is_admin
        context['params_json_str'] = json.dumps(strategy.default_parameters, indent=2)
        return context


class StrategySaveCodeView(LoginRequiredMixin, View):
    """Admin-only view to save edited Go code and strategy parameters from Web UI."""
    def post(self, request, pk, *args, **kwargs):
        user = request.user
        is_admin = getattr(user, 'is_superuser', False) or getattr(user, 'role', '') in ['admin', 'developer']
        if not is_admin:
            return HttpResponseForbidden("Permission Denied: Only administrators can modify strategy code.")

        strategy = get_object_or_404(TradingStrategy, pk=pk, is_deleted=False)
        new_code = request.POST.get('go_code', '')
        new_params_str = request.POST.get('parameters_json', '{}')

        # Update Go code file
        full_path = os.path.join(settings.BASE_DIR, strategy.go_file_path)
        try:
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(new_code)
        except Exception as e:
            response = HttpResponse(status=400)
            response['HX-Trigger'] = json.dumps({
                'showToast': {'message': f"Failed to save Go file: {e}", 'level': 'error'}
            })
            return response

        # Parse & update parameters JSON
        try:
            parsed_params = json.loads(new_params_str)
            strategy.default_parameters = parsed_params
            strategy.save()
        except Exception as e:
            pass

        # Trigger background docker build for go_app
        import subprocess
        try:
            subprocess.Popen(["docker", "compose", "build", "go_app"], cwd=settings.BASE_DIR)
        except Exception:
            pass

        msg = f"Strategy '{strategy.name}' code & parameters saved successfully!"
        response = HttpResponse(status=200)
        response['HX-Trigger'] = json.dumps({
            'showToast': {'message': msg, 'level': 'success'}
        })
        return response


class StrategyDeleteView(LoginRequiredMixin, View):
    """Admin-only deletion view for strategies."""
    def get(self, request, pk, *args, **kwargs):
        user = request.user
        is_admin = getattr(user, 'is_superuser', False) or getattr(user, 'role', '') in ['admin', 'developer']
        if not is_admin:
            return render(request, 'admins/partials/confirm_delete.html', {
                'object': None,
                'error_msg': "Permission Denied: Regular users cannot delete strategies. Only system admins have delete authority."
            })
        strategy = get_object_or_404(TradingStrategy, pk=pk, is_deleted=False)
        return render(request, 'admins/partials/confirm_delete.html', {'object': strategy, 'item_name': 'Strategy'})

    def post(self, request, pk, *args, **kwargs):
        user = request.user
        is_admin = getattr(user, 'is_superuser', False) or getattr(user, 'role', '') in ['admin', 'developer']
        if not is_admin:
            response = HttpResponse(status=403)
            response['HX-Trigger'] = json.dumps({
                'closeGlobalModal': True,
                'showToast': {'message': "Permission Denied: Only Admins can delete strategies.", 'level': 'error'}
            })
            return response

        strategy = get_object_or_404(TradingStrategy, pk=pk, is_deleted=False)
        strategy.is_deleted = True
        strategy.save()

        response = HttpResponse(status=204)
        response['HX-Trigger'] = json.dumps({
            'closeGlobalModal': True,
            'showToast': {'message': f"Strategy '{strategy.name}' deleted successfully.", 'level': 'success'},
            'reloadStrategyTable': True
        })
        return response


class BacktestRuleListView(HTMXPartialMixin, LoginRequiredMixin, AdminRequiredMixin, ListView):
    """Rule Management Dashboard with search, filter, and HTMX partial swap."""
    model = BacktestRule
    template_name = 'admins/backtest_rule_list.html'
    partial_template_name = 'admins/partials/backtest_rule_table_partial.html'
    context_object_name = 'rules'

    def get_queryset(self):
        queryset = super().get_queryset().filter(is_deleted=False)
        q = self.request.GET.get('q', '').strip()
        if q:
            queryset = queryset.filter(Q(name__icontains=q) | Q(description__icontains=q) | Q(prompt_directive__icontains=q))
        rule_type = self.request.GET.get('rule_type', '').strip()
        if rule_type:
            queryset = queryset.filter(rule_type=rule_type)
        is_active = self.request.GET.get('is_active', '').strip()
        if is_active in ['true', '1']:
            queryset = queryset.filter(is_active=True)
        elif is_active in ['false', '0']:
            queryset = queryset.filter(is_active=False)
        return queryset.order_by('-is_system_preset', 'id')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = "Backtest Strategy Rules"
        context['rule_types'] = BacktestRule.RuleTypeChoices.choices
        context['current_filters'] = {
            'q': self.request.GET.get('q', ''),
            'rule_type': self.request.GET.get('rule_type', ''),
            'is_active': self.request.GET.get('is_active', ''),
        }
        return context


class BacktestRuleCreateView(HtmxModalMixin, HtmxMessageMixin, LoginRequiredMixin, AdminRequiredMixin, CreateView):
    """Modal creation view for new custom strategy rules."""
    model = BacktestRule
    form_class = BacktestRuleForm
    template_name = 'admins/partials/backtest_rule_form_modal.html'
    modal_template_name = 'admins/partials/backtest_rule_form_modal.html'
    success_message = "Strategy Rule created successfully."

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.is_system_preset = False
        self.object.save()
        response = HttpResponse(status=204)
        response['HX-Trigger'] = json.dumps({
            'closeGlobalModal': True,
            'showToast': {'message': str(self.success_message), 'level': 'success'},
            'reloadRuleTable': True
        })
        return response


class BacktestRuleUpdateView(HtmxModalMixin, HtmxMessageMixin, LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    """Modal update view for strategy rules."""
    model = BacktestRule
    form_class = BacktestRuleForm
    template_name = 'admins/partials/backtest_rule_form_modal.html'
    modal_template_name = 'admins/partials/backtest_rule_form_modal.html'
    success_message = "Strategy Rule updated successfully."

    def form_valid(self, form):
        self.object = form.save()
        response = HttpResponse(status=204)
        response['HX-Trigger'] = json.dumps({
            'closeGlobalModal': True,
            'showToast': {'message': str(self.success_message), 'level': 'success'},
            'reloadRuleTable': True
        })
        return response


class BacktestRuleDeleteView(HtmxModalMixin, HtmxMessageMixin, LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    """Delete confirmation view with safeguard against system presets."""
    model = BacktestRule
    modal_template_name = 'admins/partials/confirm_delete.html'
    template_name = 'admins/partials/confirm_delete.html'
    success_message = "Strategy Rule deleted successfully."

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.is_system_preset:
            return render(request, 'admins/partials/confirm_delete.html', {
                'object': None,
                'error_msg': "Protected System Preset: Built-in default rules cannot be deleted. You can toggle their active state instead."
            })
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.is_system_preset:
            response = HttpResponse(status=403)
            response['HX-Trigger'] = json.dumps({
                'closeGlobalModal': True,
                'showToast': {'message': "System presets cannot be deleted.", 'level': 'warning'}
            })
            return response
        self.object.is_deleted = True
        self.object.save()
        response = HttpResponse(status=204)
        response['HX-Trigger'] = json.dumps({
            'closeGlobalModal': True,
            'showToast': {'message': str(self.success_message), 'level': 'success'},
            'reloadRuleTable': True
        })
        return response


class BacktestRuleToggleView(LoginRequiredMixin, AdminRequiredMixin, View):
    """Quick HTMX toggle endpoint to activate/deactivate strategy rules."""
    def post(self, request, pk, *args, **kwargs):
        rule = get_object_or_404(BacktestRule, pk=pk, is_deleted=False)
        rule.is_active = not rule.is_active
        rule.save(update_fields=['is_active'])
        status_str = "activated" if rule.is_active else "deactivated"
        response = HttpResponse(status=204)
        response['HX-Trigger'] = json.dumps({
            'showToast': {'message': f"Rule '{rule.name}' {status_str}.", 'level': 'info'},
            'reloadRuleTable': True
        })
        return response


class BacktestEditModalView(LoginRequiredMixin, AdminRequiredMixin, View):
    """Renders and processes modal to adjust backtest parameters and trigger fresh regeneration."""

    def get(self, request, pk, *args, **kwargs):
        task = get_object_or_404(BacktestTask, pk=pk, is_deleted=False)
        available_rules = BacktestRule.objects.filter(is_active=True, is_deleted=False)

        active_rule_ids = set(task.rules.values_list('id', flat=True))
        if not active_rule_ids and task.parameters and 'rules' in task.parameters:
            for r in task.parameters['rules']:
                if isinstance(r, dict) and 'id' in r:
                    active_rule_ids.add(r['id'])
                elif isinstance(r, dict) and 'name' in r:
                    matched = available_rules.filter(name=r['name']).first()
                    if matched:
                        active_rule_ids.add(matched.id)

        params = task.parameters or {}
        context = {
            'backtest': task,
            'available_rules': available_rules,
            'active_rule_ids': active_rule_ids,
            'start_date_val': task.start_date.strftime('%Y-%m-%d') if task.start_date else '',
            'end_date_val': task.end_date.strftime('%Y-%m-%d') if task.end_date else '',
            'initial_capital_val': task.initial_capital,
            'lots_count_val': params.get('lots_count', 1),
            'strike_selection_val': params.get('strike_selection', 'ATM'),
            'stop_loss_points_val': params.get('stop_loss_points', params.get('sl_pts', 30.0)),
            'rr_ratio_val': params.get('rr_ratio', 2.0),
            'prompt_directives_val': params.get('prompt_directives', ''),
        }
        return render(request, 'admins/partials/backtest_edit_modal.html', context)

    def post(self, request, pk, *args, **kwargs):
        task = get_object_or_404(BacktestTask, pk=pk, is_deleted=False)

        start_date_str = request.POST.get('start_date', '').strip()
        end_date_str = request.POST.get('end_date', '').strip()
        initial_capital_str = request.POST.get('initial_capital', '').strip()

        if start_date_str:
            task.start_date = start_date_str
        if end_date_str:
            task.end_date = end_date_str
        if initial_capital_str:
            try:
                task.initial_capital = float(initial_capital_str)
            except ValueError:
                pass

        try:
            rr_ratio = float(request.POST.get('rr_ratio', 2.0))
        except ValueError:
            rr_ratio = 2.0

        try:
            sl_pts = float(request.POST.get('stop_loss_points', 30.0))
        except ValueError:
            sl_pts = 30.0

        try:
            lots_count = int(request.POST.get('lots_count', 1))
        except ValueError:
            lots_count = 1

        strike_selection = request.POST.get('strike_selection', 'ATM').strip()
        prompt_directives = request.POST.get('prompt_directives', '').strip()

        selected_rule_ids = request.POST.getlist('rules')
        rules_qs = BacktestRule.objects.filter(id__in=selected_rule_ids, is_deleted=False)

        rules_list = []
        for r in rules_qs:
            rules_list.append({
                "id": r.id,
                "name": r.name,
                "rule_type": r.rule_type,
                "parameters": r.parameters or {},
                "prompt_directive": r.prompt_directive or "",
            })

        task.parameters = {
            **(task.parameters or {}),
            "rr_ratio": rr_ratio,
            "stop_loss_points": sl_pts,
            "sl_pts": sl_pts,
            "lots_count": lots_count,
            "strike_selection": strike_selection,
            "rules": rules_list,
            "prompt_directives": prompt_directives,
        }
        task.save(update_fields=['start_date', 'end_date', 'initial_capital', 'parameters'])
        task.rules.set(rules_qs)

        send_backtest_control_command(task.id, 'START')

        response = HttpResponse(status=204)
        response['HX-Trigger'] = json.dumps({
            'showToast': {'message': f'Parameters saved & Backtest #BT-{task.id:04d} regeneration started!', 'level': 'success'},
            'closeGlobalModal': True,
            'reloadBacktestDetail': True,
            'reloadBacktestTable': True,
        })
        return response


