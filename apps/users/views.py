import json
import logging
import os
from django.conf import settings
from django.contrib import messages
from django.core.mail import send_mail
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

logger = logging.getLogger(__name__)
from django.contrib.auth import login as auth_login, logout as auth_logout, update_session_auth_hash
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import (
    PasswordResetView,
    PasswordResetDoneView,
    PasswordResetConfirmView,
    PasswordResetCompleteView,
)
from django.http import HttpResponse, HttpResponseForbidden, FileResponse, Http404, HttpResponseRedirect
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import FormView, TemplateView, UpdateView

from apps.backtest.models import BacktestTask
from apps.common.choices import BrokerChoices, AccountTypeChoices
from apps.common.mixins import HtmxMessageMixin, HtmxModalMixin
from apps.common.models import SiteSettings
from apps.common.services.live_feed_service import (
    get_ist_market_clock,
    get_current_month_calendar_pnl,
    get_today_intraday_equity_curve,
    get_nifty_mini_option_chain,
)
from apps.market.forms import MarketBackupForm
from apps.market.models import MarketBackupTask
from apps.trade_config.models import TradeExecConfig, UserTradingAccount, BrokerMaster, LiveStrategy, DailyPortfolioSnapshot
from apps.trade_core.brokers import BrokerFactory
from .forms import (
    TraderSignUpForm,
    TraderLoginForm,
    TraderPasswordResetForm,
    OtpVerificationForm,
    EmailSsoRequestForm,
    UserProfileForm,
    UserProfilePasswordChangeForm,
    UserBacktestTaskForm,
)
from apps.common.constants import UserMessages
from .mixins import HTMXPartialMixin, MarmotRoleRequiredMixin
from .models import User
from .permissions import is_user_authorized_for_dashboard
from .services import get_user_profile, generate_and_send_email_otp, verify_email_otp


class SignUpView(FormView):
    template_name = 'registration/signup.html'
    form_class = TraderSignUpForm
    success_url = reverse_lazy('users:marmot-verify-otp')

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect(reverse_lazy('users:marmot-dashboard'))
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        user = form.save()
        if form.cleaned_data.get('remember_me'):
            self.request.session['remember_me_pending'] = True

        # Generate and dispatch 6-digit OTP code to the user's email
        success, msg = generate_and_send_email_otp(
            user_or_email=user,
            request=self.request,
            purpose='signup_activation'
        )
        if not success:
            messages.warning(self.request, msg)

        success_url = self.get_success_url()
        if self.request.headers.get('HX-Request'):
            response = HttpResponse()
            response['HX-Redirect'] = str(success_url)
            return response
        return redirect(success_url)

    def get_success_url(self):
        return reverse_lazy('users:marmot-verify-otp')


class VerifyOtpView(FormView):
    template_name = 'registration/verify_otp.html'
    form_class = OtpVerificationForm
    success_url = reverse_lazy('users:marmot-dashboard')

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect(self.get_success_url())
        if not request.session.get('auth_otp_email'):
            messages.info(request, "Please enter your email or credentials first.")
            return redirect(reverse_lazy('users:marmot-login'))
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['email'] = self.request.session.get('auth_otp_email', '')
        context['purpose'] = self.request.session.get('auth_otp_purpose', 'signup_activation')
        context['expiry_minutes'] = self.request.session.get('auth_otp_expiry_minutes', 10)
        return context

    def form_valid(self, form):
        otp = form.cleaned_data['otp']
        valid, user, msg = verify_email_otp(otp, self.request)

        if not valid or not user:
            form.add_error('otp', msg)
            return self.form_invalid(form)

        # Authenticate and login verified active user
        auth_login(self.request, user, backend='django.contrib.auth.backends.ModelBackend')

        if self.request.session.pop('remember_me_pending', False):
            self.request.session.set_expiry(60 * 60 * 24 * 30)  # 30 days
        else:
            self.request.session.set_expiry(0)

        messages.success(self.request, "Email verified successfully! Welcome to Marmot.")

        success_url = self.get_success_url()
        if self.request.headers.get('HX-Request'):
            response = HttpResponse()
            response['HX-Redirect'] = str(success_url)
            return response
        return redirect(success_url)


class ResendOtpView(View):
    def post(self, request, *args, **kwargs):
        email = request.session.get('auth_otp_email')
        purpose = request.session.get('auth_otp_purpose', 'signup_activation')
        if not email:
            messages.error(request, "No pending email verification session found.")
            return redirect(reverse_lazy('users:marmot-login'))

        success, msg = generate_and_send_email_otp(email, request, purpose=purpose)
        if success:
            messages.success(request, f"New 6-digit verification code sent to {email}.")
        else:
            messages.error(request, msg)

        return redirect(reverse_lazy('users:marmot-verify-otp'))


class EmailSsoLoginView(FormView):
    template_name = 'registration/email_sso.html'
    form_class = EmailSsoRequestForm
    success_url = reverse_lazy('users:marmot-verify-otp')

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect(reverse_lazy('users:marmot-dashboard'))
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        email = form.cleaned_data['email']
        user = User.objects.filter(email__iexact=email).first()

        success, msg = generate_and_send_email_otp(
            user_or_email=user or email,
            request=self.request,
            purpose='email_sso'
        )
        if success:
            messages.info(self.request, f"A 6-digit verification code has been sent to {email}.")
        else:
            messages.error(self.request, msg)

        return redirect(self.get_success_url())


class LoginView(FormView):
    template_name = 'registration/login.html'
    form_class = TraderLoginForm

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect(self.get_success_url())
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs

    def form_valid(self, form):
        user = form.get_user()
        auth_login(self.request, user, backend='django.contrib.auth.backends.ModelBackend')

        if form.cleaned_data.get('remember_me'):
            self.request.session.set_expiry(60 * 60 * 24 * 30)  # 30 days
        else:
            self.request.session.set_expiry(0)

        success_url = self.get_success_url()
        if self.request.headers.get('HX-Request'):
            response = HttpResponse()
            response['HX-Redirect'] = str(success_url)
            return response
        return redirect(success_url)

    def form_invalid(self, form):
        unverified_user = getattr(form, 'unverified_user', None)
        if unverified_user:
            # Dispatch verification OTP and redirect to OTP screen
            generate_and_send_email_otp(
                user_or_email=unverified_user,
                request=self.request,
                purpose='signup_activation'
            )
            messages.info(self.request, f"Please verify your email address to activate your account. A new code has been sent to {unverified_user.email}.")
            return redirect(reverse_lazy('users:marmot-verify-otp'))
        return super().form_invalid(form)

    def get_success_url(self):
        next_url = self.request.GET.get('next')
        if next_url:
            return next_url
        user = self.request.user
        if user.is_authenticated:
            user_role = getattr(user, 'role', '')
            if user.is_superuser or user_role in ['admin', 'developer', 'staff']:
                return reverse_lazy('admins:admin-dashboard')
            return reverse_lazy('users:marmot-dashboard')
        return reverse_lazy('users:marmot-login')


class MarmotPasswordResetView(PasswordResetView):
    template_name = 'registration/password_reset_form.html'
    form_class = TraderPasswordResetForm
    email_template_name = 'registration/password_reset_email.html'
    subject_template_name = 'registration/password_reset_subject.txt'
    success_url = reverse_lazy('users:password_reset_done')


class MarmotPasswordResetDoneView(PasswordResetDoneView):
    template_name = 'registration/password_reset_done.html'


class MarmotPasswordResetConfirmView(PasswordResetConfirmView):
    template_name = 'registration/password_reset_confirm.html'
    success_url = reverse_lazy('users:password_reset_complete')


class MarmotPasswordResetCompleteView(PasswordResetCompleteView):
    template_name = 'registration/password_reset_complete.html'



def populate_account_context(context, user, request):
    """Helper function to populate active trading account context across user views."""
    active_acc = user.get_active_trading_account(request)
    accounts = list(user.trading_accounts.filter(is_active=True).order_by('-is_default', 'account_type', 'account_name'))
    
    context['active_trading_account'] = active_acc
    context['user_trading_accounts'] = accounts
    context['watching_on'] = active_acc.account_type if active_acc else 'SANDBOX'
    return active_acc


class UserDashboardView(HTMXPartialMixin, MarmotRoleRequiredMixin, TemplateView):
    """Default User Dashboard route - Routes Admins to Admin Dashboard and Traders to Live Dashboard."""
    def get(self, request, *args, **kwargs):
        user = request.user
        user_role = getattr(user, 'role', '')
        if user.is_authenticated and (user.is_superuser or user_role in ['admin', 'developer', 'staff']):
            if request.GET.get('trader_view') != '1':
                return redirect('admins:admin-dashboard')
        return redirect('users:user-live-dashboard')


class UserLiveDashboardView(HTMXPartialMixin, MarmotRoleRequiredMixin, TemplateView):
    """Dedicated Live Trading Dashboard powered by live broker API telemetry."""
    template_name = 'users/live_dashboard.html'
    partial_template_name = 'users/partials/live_dashboard_content.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        live_accounts = user.trading_accounts.filter(is_active=True, account_type='LIVE').order_by('-is_default', 'account_name')
        live_account = live_accounts.filter(is_default=True).first() or live_accounts.first()
        
        context['active_tab'] = 'live-dashboard'
        context['live_account'] = live_account
        context['live_accounts'] = list(live_accounts)
        context['has_live_account'] = bool(live_account)
        context['marmot_profile'] = get_user_profile(user.username)
        
        context['live_strategy_configs'] = TradeExecConfig.objects.filter(
            admins_user=user,
            account_type='LIVE',
            is_deleted=False
        ).select_related('trading_account')
        
        is_token_active = False
        needs_consent = False
        broker_name = 'Dhan HQ'
        available_margin = "0.00"
        cash_balance = "0.00"
        collateral = "0.00"
        margin_utilized = "0.00"
        live_net_pnl = 0.00
        realized_pnl = 0.00
        unrealized_pnl = 0.00
        open_positions_count = 0
        closed_positions_count = 0
        todays_orders_count = 0
        open_orders_count = 0
        traded_orders_count = 0
        total_invested = 0.00
        current_value = 0.00
        holdings_pnl = 0.00
        holdings_pnl_pct = 0.00
        holdings_count = 0

        context['live_positions'] = []
        context['live_holdings'] = []
        context['live_orders'] = []

        if live_account:
            broker_name = live_account.broker.name if live_account.broker else 'DHAN'
            try:
                adapter = BrokerFactory.get_adapter(live_account)
                if hasattr(adapter, 'get_live_dashboard_summary'):
                    summary = adapter.get_live_dashboard_summary()
                    is_token_active = summary.get('is_token_active', False)
                    needs_consent = summary.get('needs_consent', False)
                    available_margin = summary.get('available_margin', '0.00')
                    cash_balance = summary.get('cash', '0.00')
                    collateral = summary.get('collateral', '0.00')
                    margin_utilized = summary.get('margin_utilized', '0.00')
                    live_net_pnl = summary.get('live_net_pnl', 0.00)
                    realized_pnl = summary.get('realized_pnl', 0.00)
                    unrealized_pnl = summary.get('unrealized_pnl', 0.00)
                    open_positions_count = summary.get('open_positions_count', 0)
                    closed_positions_count = summary.get('closed_positions_count', 0)
                    todays_orders_count = summary.get('todays_orders_count', 0)
                    open_orders_count = summary.get('open_orders_count', 0)
                    traded_orders_count = summary.get('traded_orders_count', 0)
                    total_invested = summary.get('total_invested', 0.00)
                    current_value = summary.get('current_value', 0.00)
                    holdings_pnl = summary.get('holdings_pnl', 0.00)
                    holdings_pnl_pct = summary.get('holdings_pnl_pct', 0.00)
                    holdings_count = summary.get('holdings_count', 0)
                    raw_pos = summary.get('positions', [])
                    context['all_positions_count'] = len(raw_pos)
                    pos_paginator = Paginator(raw_pos, 10)
                    context['live_positions'] = pos_paginator.page(1).object_list
                    context['page_obj'] = pos_paginator.page(1)
                    context['is_paginated'] = pos_paginator.num_pages > 1

                    raw_hld = summary.get('holdings', [])
                    hld_paginator = Paginator(raw_hld, 10)
                    context['live_holdings'] = hld_paginator.page(1).object_list

                    raw_ord = summary.get('orders', [])
                    context['orders_count'] = len(raw_ord)
                    ord_paginator = Paginator(raw_ord, 10)
                    context['live_orders'] = ord_paginator.page(1).object_list
                else:
                    auth_res = adapter.test_connection()
                    is_token_active = auth_res.get('success', False)
                    needs_consent = not is_token_active
            except Exception as e:
                logger.warning("Error loading live dashboard telemetry: %s", e)
                is_token_active = False
                needs_consent = True

        context['broker_name'] = broker_name
        context['is_token_active'] = is_token_active
        context['needs_consent'] = needs_consent
        context['available_margin'] = available_margin
        context['cash_balance'] = cash_balance
        context['collateral'] = collateral
        context['margin_utilized'] = margin_utilized
        context['live_net_pnl'] = live_net_pnl
        context['realized_pnl'] = realized_pnl
        context['unrealized_pnl'] = unrealized_pnl
        context['open_positions_count'] = open_positions_count
        context['closed_positions_count'] = closed_positions_count
        context['todays_orders_count'] = todays_orders_count
        context['open_orders_count'] = open_orders_count
        context['traded_orders_count'] = traded_orders_count
        context['total_invested'] = total_invested
        context['current_value'] = current_value
        context['holdings_pnl'] = holdings_pnl
        context['holdings_pnl_pct'] = holdings_pnl_pct
        context['holdings_count'] = holdings_count

        # Live Execution Telemetry & Isolated Strategies
        site_settings = SiteSettings.load()
        context['site_settings'] = site_settings
        context['master_live_switch'] = site_settings.live_execution_master_switch
        context['live_strategies'] = user.live_strategies.filter(is_deleted=False, execution_mode=AccountTypeChoices.LIVE).select_related('trading_account__broker', 'backtest_task').order_by('-created_at')
        context['market_clock'] = get_ist_market_clock()
        context['calendar_pnl'] = get_current_month_calendar_pnl(user)
        context['intraday_graph'] = get_today_intraday_equity_curve(user)
        context['option_chain'] = get_nifty_mini_option_chain()
        return context


class UserSandboxDashboardView(HTMXPartialMixin, MarmotRoleRequiredMixin, TemplateView):
    """Dedicated Sandbox Paper-Trading Dashboard running on local simulated ledger."""
    template_name = 'users/sandbox_dashboard.html'
    partial_template_name = 'users/partials/sandbox_dashboard_content.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        sandbox_accounts = user.trading_accounts.filter(is_active=True, account_type='SANDBOX').order_by('-is_default', 'account_name')
        sandbox_account = sandbox_accounts.filter(is_default=True).first() or sandbox_accounts.first()

        telemetry_summary = {}
        try:
            from apps.market.services import redis_client
            import json
            telemetry_raw = redis_client.get(f"marmot:sandbox:telemetry:{user.id}")
            if telemetry_raw:
                t_data = json.loads(telemetry_raw)
                telemetry_summary = t_data.get("summary", {})
        except Exception:
            pass

        context['active_tab'] = 'sandbox-dashboard'
        context['sandbox_account'] = sandbox_account
        context['sandbox_accounts'] = list(sandbox_accounts)
        context['marmot_profile'] = get_user_profile(user.username)

        context['sandbox_strategy_configs'] = TradeExecConfig.objects.filter(
            admins_user=user,
            account_type='SANDBOX',
            is_deleted=False
        ).select_related('trading_account')
        context['live_strategies'] = user.live_strategies.filter(
            is_deleted=False, execution_mode=AccountTypeChoices.SANDBOX
        ).select_related('trading_account__broker', 'backtest_task').order_by('-created_at')

        acc_summary = sandbox_account.account_summary if sandbox_account else {}
        base_cap = acc_summary.get('balance') or acc_summary.get('initial_capital') or 100000.00
        formatted_base_cap = f"{float(base_cap):,.2f}"

        context['virtual_capital'] = telemetry_summary.get('cash') or telemetry_summary.get('cash_balance') or formatted_base_cap
        context['virtual_available_margin'] = telemetry_summary.get('available_margin') or formatted_base_cap
        context['simulated_pnl'] = telemetry_summary.get('live_net_pnl', 0.00)
        context['simulated_win_rate'] = telemetry_summary.get('win_rate', "0.0%")
        context['simulated_trades_count'] = telemetry_summary.get('todays_orders_count') or telemetry_summary.get('trades_count', 0)
        return context


class UserAIDashboardView(HTMXPartialMixin, MarmotRoleRequiredMixin, TemplateView):
    """View for Trader AI Intelligence Dashboard and Gemini Copilot."""
    template_name = 'users/dashboard.html'
    partial_template_name = 'users/partials/ai_dashboard_content.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        populate_account_context(context, user, self.request)
        context['active_tab'] = 'ai-dashboard'
        context['gemini_active'] = bool(getattr(settings, 'GEMINI_API_KEY', ''))
        return context


class UserTerminalView(HTMXPartialMixin, MarmotRoleRequiredMixin, TemplateView):
    """View for user absolute trading terminal supporting Dhan & Fyers."""
    template_name = 'users/dashboard.html'
    partial_template_name = 'users/partials/terminal_content.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        active_acc = populate_account_context(context, user, self.request)
        context['active_tab'] = 'terminal'

        broker_code = getattr(active_acc.broker, 'code', 'dhan').lower() if (active_acc and active_acc.broker) else 'dhan'
        context['broker_code'] = broker_code
        context['broker_name'] = active_acc.broker.name if (active_acc and active_acc.broker) else ('DHAN' if broker_code == 'dhan' else 'FYERS')
        context['account_type'] = active_acc.account_type if active_acc else 'SANDBOX'
        context['account_id_display'] = active_acc.broker_client_id if active_acc else 'DEMO-8888'

        is_token_active = False
        if active_acc and broker_code == 'dhan' and active_acc.broker_client_id:
            try:
                from apps.trade_core.services.dhan_token_service import UserDhanClient
                client = UserDhanClient(active_acc.broker_client_id)
                token = client.get_access_token()
                if token:
                    is_token_active = True
            except Exception:
                is_token_active = False
        elif active_acc and broker_code == 'fyers':
            is_token_active = bool(active_acc.broker_api_secret or active_acc.broker_api_key)

        has_configured_account = bool(active_acc and (active_acc.broker_client_id or active_acc.account_name))
        context['has_configured_account'] = has_configured_account
        context['is_token_active'] = is_token_active
        return context


def _get_user_journal_calendar_and_stats(user, target_year, active_acc=None):
    """Compute 12-month calendar grid and summary statistics for a user's trading journal."""
    import calendar as cal
    from datetime import datetime
    from apps.common.models import PostbackLog

    try:
        selected_year = int(target_year)
    except (ValueError, TypeError):
        selected_year = datetime.now().year

    account_type = active_acc.account_type if active_acc else 'SANDBOX'
    acc_summary = active_acc.account_summary if active_acc else {}
    base_capital = float(acc_summary.get('balance') or acc_summary.get('initial_capital') or 100000.0)

    # 1. Query DailyPortfolioSnapshot for the user & account
    snapshots_qs = DailyPortfolioSnapshot.objects.filter(
        user=user,
        date__year=selected_year
    )
    if active_acc:
        snapshots_qs = snapshots_qs.filter(trading_account=active_acc)

    daily_map = {}
    for s in snapshots_qs:
        d_str = s.date.strftime('%Y-%m-%d')
        net_val = float(s.net_pnl)
        gross_val = float(s.gross_pnl)
        charges_val = float(s.total_charges)
        daily_map[d_str] = {
            'date_str': s.date.strftime('%d %b %Y'),
            'ymd': d_str,
            'net_pnl': net_val,
            'net_pnl_abs': abs(net_val),
            'gross_pnl': gross_val,
            'gross_pnl_abs': abs(gross_val),
            'brokerage': charges_val * 0.7,
            'govt_charges': charges_val * 0.3,
            'trades': s.total_trades,
            'margin_utilized': float(s.margin_utilized),
            'closing_balance': float(s.closing_balance),
        }

    # 2. If LIVE account, incorporate broker / postback data
    if account_type == 'LIVE' and active_acc and active_acc.broker and active_acc.broker.code == 'dhan':
        try:
            adapter = BrokerFactory.get_adapter(active_acc)
            from_d = f"{selected_year}-01-01"
            to_d = f"{selected_year}-12-31"
            t_res = adapter.get_trade_history(from_d, to_d, page=0, fetch_all=True)
            if t_res.get('success') and t_res.get('trades'):
                from apps.admins.views import _calculate_daily_pnl_map
                broker_daily = _calculate_daily_pnl_map(t_res['trades'])
                for k, v in broker_daily.items():
                    if k not in daily_map:
                        daily_map[k] = v
        except Exception:
            pass

    # 3. Check PostbackLog
    postback_logs = PostbackLog.objects.filter(created_at__year=selected_year)
    for p_log in postback_logs:
        p_date_str = p_log.created_at.strftime('%Y-%m-%d')
        pnl_val = float(getattr(p_log, 'pnl', 0.0) or 0.0)
        if p_date_str not in daily_map:
            daily_map[p_date_str] = {
                'gross_pnl': pnl_val,
                'gross_pnl_abs': abs(pnl_val),
                'net_pnl': pnl_val,
                'net_pnl_abs': abs(pnl_val),
                'brokerage': 20.0,
                'govt_charges': 5.0,
                'trades': 1,
                'date_str': p_log.created_at.strftime('%d %b %Y'),
                'ymd': p_date_str,
            }

    # Aggregate Year-Wise Stats
    total_net_pnl = round(sum(d['net_pnl'] for d in daily_map.values()), 2)
    total_gross_pnl = round(sum(d['gross_pnl'] for d in daily_map.values()), 2)
    total_brokerage = round(sum(d['brokerage'] for d in daily_map.values()), 2)
    total_govt = round(sum(d['govt_charges'] for d in daily_map.values()), 2)
    total_charges = round(total_brokerage + total_govt, 2)
    total_trades = sum(d['trades'] for d in daily_map.values())

    winning_days = sum(1 for d in daily_map.values() if d['net_pnl'] >= 0)
    losing_days = sum(1 for d in daily_map.values() if d['net_pnl'] < 0)
    win_rate = round((winning_days / max(len(daily_map), 1)) * 100, 1) if len(daily_map) > 0 else 0.0

    gross_profit = round(sum(d['gross_pnl'] for d in daily_map.values() if d['gross_pnl'] > 0), 2)
    gross_loss = round(sum(d['gross_pnl'] for d in daily_map.values() if d['gross_pnl'] < 0), 2)
    gross_loss_abs = abs(gross_loss)
    profit_factor = round(gross_profit / max(gross_loss_abs, 1.0), 2) if gross_loss_abs > 0 else (2.45 if gross_profit > 0 else 1.0)

    avg_win = round(gross_profit / max(winning_days, 1), 2) if winning_days > 0 else 0.0
    avg_loss_abs = round(gross_loss_abs / max(losing_days, 1), 2) if losing_days > 0 else 0.0
    real_rr = round(avg_win / max(avg_loss_abs, 1.0), 2) if avg_loss_abs > 0 else (round(avg_win, 2) if avg_win > 0 else 1.0)
    real_expectancy = round(((win_rate / 100.0) * avg_win) - (((100.0 - win_rate) / 100.0) * avg_loss_abs), 2)

    stats = {
        'total_pnl': total_net_pnl,
        'total_pnl_abs': abs(total_net_pnl),
        'pnl_pct': round((total_net_pnl / max(base_capital, 1.0)) * 100, 1) if total_net_pnl != 0 else 0.0,
        'win_rate': win_rate,
        'wins_count': winning_days,
        'losses_count': losing_days,
        'total_trades': total_trades,
        'profit_factor': profit_factor,
        'risk_reward_ratio': real_rr,
        'expectancy': real_expectancy,
        'avg_win': avg_win,
        'avg_loss_abs': avg_loss_abs,
        'total_charges': total_charges,
        'net_capital': round(base_capital, 2),
        'account_type': account_type,
    }

    # Build 12-Month Calendar Grid
    months_data = []
    month_names = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
    for m_idx in range(1, 13):
        m_name = month_names[m_idx - 1]
        cal_obj = cal.Calendar(firstweekday=0)
        month_days = []
        m_pnl = 0.0
        p_days = 0
        l_days = 0

        for day_date in cal_obj.itermonthdates(selected_year, m_idx):
            is_cur = (day_date.month == m_idx)
            d_str = day_date.strftime('%Y-%m-%d')
            if is_cur and d_str in daily_map:
                d_info = daily_map[d_str]
                p_val = d_info['net_pnl']
                t_cnt = d_info['trades']
                status = 'profit' if p_val >= 0 else 'loss'
                if p_val >= 0:
                    p_days += 1
                else:
                    l_days += 1
                m_pnl += p_val
                g_pnl = d_info['gross_pnl']
                b_val = d_info['brokerage']
                gov_val = d_info['govt_charges']
            else:
                p_val = 0.0
                t_cnt = 0
                status = 'neutral'
                g_pnl = 0.0
                b_val = 0.0
                gov_val = 0.0

            abs_p = abs(p_val)
            intensity = 'high' if abs_p >= 2000.0 else ('med' if abs_p >= 500.0 else 'low')
            month_days.append({
                'date': day_date,
                'day_num': day_date.day,
                'is_current_month': is_cur,
                'pnl': p_val,
                'pnl_abs': abs_p,
                'intensity': intensity,
                'gross_pnl': g_pnl,
                'brokerage': b_val,
                'govt_charges': gov_val,
                'trades': t_cnt,
                'status': status,
                'weekday': day_date.weekday(),
            })

        months_data.append({
            'month_num': m_idx,
            'name': m_name,
            'days': month_days,
            'monthly_pnl': round(m_pnl, 2),
            'monthly_pnl_abs': abs(round(m_pnl, 2)),
            'profit_days': p_days,
            'loss_days': l_days,
        })

    return stats, months_data, daily_map


class UserJournalView(HTMXPartialMixin, MarmotRoleRequiredMixin, TemplateView):
    """View for user execution journal with calendar analytics and trade history."""
    template_name = 'users/dashboard.html'
    partial_template_name = 'users/partials/journal_content.html'

    def get_context_data(self, **kwargs):
        from datetime import datetime
        context = super().get_context_data(**kwargs)
        user = self.request.user
        active_acc = populate_account_context(context, user, self.request)
        context['active_tab'] = 'journal'

        current_year = datetime.now().year
        raw_year = str(self.request.GET.get('year', current_year)).strip()
        try:
            selected_year = int(raw_year)
        except (ValueError, TypeError):
            selected_year = current_year

        stats, months, daily_map = _get_user_journal_calendar_and_stats(user, selected_year, active_acc)

        context['stats'] = stats
        context['months'] = months
        context['year'] = selected_year
        context['active_year'] = str(selected_year)
        context['prev_year'] = selected_year - 1
        context['next_year'] = selected_year + 1
        context['current_year'] = current_year
        context['can_go_next'] = (selected_year < current_year)
        context['account_type'] = active_acc.account_type if active_acc else 'SANDBOX'
        return context


class UserJournalCalendarView(LoginRequiredMixin, View):
    """HTMX partial view returning 12-month calendar grid for the user."""
    def get(self, request, *args, **kwargs):
        from datetime import datetime
        user = request.user
        active_acc = user.get_active_trading_account(request)
        current_year = datetime.now().year
        raw_year = str(request.GET.get('year', current_year)).strip()
        try:
            selected_year = int(raw_year)
        except (ValueError, TypeError):
            selected_year = current_year

        stats, months, _ = _get_user_journal_calendar_and_stats(user, selected_year, active_acc)
        context = {
            'year': selected_year,
            'prev_year': selected_year - 1,
            'next_year': selected_year + 1,
            'current_year': current_year,
            'can_go_next': (selected_year < current_year),
            'months': months,
            'stats': stats,
            'active_year': str(selected_year),
            'account_type': active_acc.account_type if active_acc else 'SANDBOX',
        }
        return render(request, 'users/partials/journal_calendar_partial.html', context)


class UserJournalTradesView(LoginRequiredMixin, View):
    """HTMX partial view returning trade logs for a selected calendar date or year."""
    def get(self, request, *args, **kwargs):
        user = request.user
        active_acc = user.get_active_trading_account(request)
        filter_date = str(request.GET.get('date', '')).strip()
        filter_year = str(request.GET.get('year', '')).strip()

        trades = []
        day_summary = None

        # Fetch from DailyPortfolioSnapshot telemetry if available
        if filter_date:
            snapshot = DailyPortfolioSnapshot.objects.filter(
                user=user,
                date=filter_date
            )
            if active_acc:
                snapshot = snapshot.filter(trading_account=active_acc)
            snap = snapshot.first()
            if snap and snap.telemetry_snapshot:
                raw_orders = snap.telemetry_snapshot.get('orders', [])
                for idx, ord_item in enumerate(raw_orders):
                    trades.append({
                        'id': f"SB-{idx+1}",
                        'order_id': f"SB-{idx+1}",
                        'time': ord_item.get('Time', '09:30:00'),
                        'date_str': snap.date.strftime('%d %b %Y'),
                        'symbol': ord_item.get('TradingSymbol', 'NIFTY 23750 CE'),
                        'segment': ord_item.get('ExchangeSegment', 'NSE_FNO'),
                        'type': ord_item.get('TransactionType', 'BUY'),
                        'order_type': ord_item.get('OrderType', 'MARKET'),
                        'qty': ord_item.get('Qty', 50),
                        'entry': ord_item.get('Price', 92.50),
                        'turnover': round(float(ord_item.get('Qty', 50)) * float(ord_item.get('Price', 92.50)), 2),
                        'status': ord_item.get('Status', 'COMPLETE'),
                    })
                day_summary = {
                    'date_str': snap.date.strftime('%d %b %Y'),
                    'gross_pnl': float(snap.gross_pnl),
                    'gross_pnl_abs': abs(float(snap.gross_pnl)),
                    'net_pnl': float(snap.net_pnl),
                    'net_pnl_abs': abs(float(snap.net_pnl)),
                    'brokerage': float(snap.total_charges) * 0.7,
                    'govt_charges': float(snap.total_charges) * 0.3,
                    'trades': snap.total_trades,
                }

        context = {
            'trades': trades,
            'day_summary': day_summary,
            'filter_date': filter_date,
            'filter_year': filter_year,
            'total_trades_count': len(trades),
            'account_type': active_acc.account_type if active_acc else 'SANDBOX',
        }
        return render(request, 'users/partials/journal_trades_partial.html', context)


class UserBacktestView(HTMXPartialMixin, MarmotRoleRequiredMixin, TemplateView):
    """View for user strategy backtesting."""
    template_name = 'users/dashboard.html'
    partial_template_name = 'users/partials/backtest_content.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        populate_account_context(context, user, self.request)
        context['active_tab'] = 'backtest'
        user_backtests = BacktestTask.objects.filter(is_deleted=False, created_by=user).order_by('-id')
        context['backtests'] = user_backtests
        context['total_backtests'] = user_backtests.count()
        return context


class UserBacktestCreateView(HtmxModalMixin, LoginRequiredMixin, FormView):
    """Modal view for user to trigger a new backtest simulation."""
    form_class = UserBacktestTaskForm
    modal_template_name = 'users/partials/user_backtest_create_modal.html'
    template_name = 'users/partials/user_backtest_create_modal.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        task = form.save(commit=False)
        task.created_by = self.request.user
        task.status = 'CREATED'
        task.save()

        response = HttpResponse(status=204)
        msg = f"Backtest simulation #{task.id} started successfully!"
        response['HX-Trigger'] = json.dumps({
            'closeGlobalModal': True,
            'showToast': {'message': msg, 'level': 'success'},
            'reloadBacktestList': True
        })
        return response

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))


class UserBacktestDetailView(HTMXPartialMixin, LoginRequiredMixin, View):
    """Modal view to inspect backtest simulation details."""
    def get(self, request, pk, *args, **kwargs):
        backtest = BacktestTask.objects.filter(pk=pk, is_deleted=False).first()
        if not backtest or (backtest.created_by and backtest.created_by != request.user and not request.user.is_superuser):
            return HttpResponseForbidden("You do not have permission to view this backtest.")
        return render(request, 'users/partials/user_backtest_detail_modal.html', {'backtest': backtest})


class UserBackupListView(HTMXPartialMixin, MarmotRoleRequiredMixin, TemplateView):
    """View for user market backup downloads and tasks."""
    template_name = 'users/dashboard.html'
    partial_template_name = 'users/partials/backup_content.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        populate_account_context(context, user, self.request)
        context['active_tab'] = 'backup'
        user_backups = MarketBackupTask.objects.filter(is_deleted=False, created_by=user).order_by('-id')
        context['backup_tasks'] = user_backups
        context['total_backups'] = user_backups.count()
        return context


class UserBackupCreateView(HtmxModalMixin, LoginRequiredMixin, FormView):
    """Modal view for user to trigger a new market data backup task."""
    form_class = MarketBackupForm
    modal_template_name = 'users/partials/user_backup_create_modal.html'
    template_name = 'users/partials/user_backup_create_modal.html'

    def form_valid(self, form):
        task = form.save(commit=False)
        task.created_by = self.request.user
        task.status = MarketBackupTask.StatusChoices.CREATED
        task.save()

        response = HttpResponse(status=204)
        msg = f"Market backup task #{task.id} requested successfully!"
        response['HX-Trigger'] = json.dumps({
            'closeGlobalModal': True,
            'showToast': {'message': msg, 'level': 'success'},
            'reloadBackupList': True
        })
        return response

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))


class UserBackupDownloadView(LoginRequiredMixin, View):
    """View to download generated parquet dataset file for user."""
    def get(self, request, pk, *args, **kwargs):
        task = MarketBackupTask.objects.filter(pk=pk, is_deleted=False).first()
        if not task:
            raise Http404("Market backup task not found.")

        # Check permissions
        if not (request.user.is_superuser or task.created_by == request.user or getattr(request.user, 'role', '') in ['admin', 'developer']):
            return HttpResponseForbidden("Access Denied.")

        user_id = str(task.created_by.id if task.created_by else 1)
        candidates = [
            task.parquet_file_path,
            os.path.join(settings.BASE_DIR, 'backup', user_id, str(task.id), 'dataset.parquet'),
            os.path.join('/app', 'backup', user_id, str(task.id), 'dataset.parquet'),
            os.path.join(settings.BASE_DIR, 'backup', user_id, str(task.id)),
            os.path.join('/app', 'backup', user_id, str(task.id)),
        ]

        target_file = None
        for p in candidates:
            if p and os.path.exists(p):
                if os.path.isfile(p):
                    target_file = p
                    break
                elif os.path.isdir(p):
                    ds_p = os.path.join(p, 'dataset.parquet')
                    if os.path.exists(ds_p):
                        target_file = ds_p
                        break

        if not target_file:
            messages.error(request, "Backup dataset file is not available on disk or still in progress.")
            return HttpResponseRedirect(reverse_lazy('users:user-backup-list'))

        filename = f"{task.index_name.lower()}_{task.start_date}_{task.end_date}.parquet"
        response = FileResponse(open(target_file, 'rb'), content_type='application/vnd.apache.parquet')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

class UserEnvironmentToggleModalView(HtmxModalMixin, LoginRequiredMixin, View):
    """Render confirmation modal before switching watching environment mode."""
    modal_template_name = 'users/partials/env_toggle_modal.html'
    template_name = 'users/partials/env_toggle_modal.html'

    def get(self, request, *args, **kwargs):
        return render(request, self.modal_template_name)


class UserEnvironmentToggleView(LoginRequiredMixin, View):
    """Toggle trading environment watching_on mode between LIVE and SANDBOX."""
    def post(self, request, *args, **kwargs):
        user = request.user
        current_mode = getattr(user, 'watching_on', 'SANDBOX') or 'SANDBOX'
        new_mode = 'LIVE' if current_mode == 'SANDBOX' else 'SANDBOX'
        
        user.watching_on = new_mode
        user.save(update_fields=['watching_on'])
        request.session['user_trading_env'] = new_mode

        msg = f"Watching environment switched to {new_mode} mode."
        messages.success(request, msg)

        response = HttpResponse()
        response['HX-Trigger'] = json.dumps({
            'closeGlobalModal': True,
            'showToast': {'message': msg, 'level': 'success'},
            'reloadPage': True
        })
        return response


class UserAccountSelectView(LoginRequiredMixin, View):
    """View to handle switching active trading account from top header dropdown."""
    def post(self, request, *args, **kwargs):
        account_id = request.POST.get('account_id')
        user = request.user
        account = user.trading_accounts.filter(id=account_id, is_active=True).first() if account_id else None

        if account:
            request.session['active_account_id'] = account.id
            msg = f"Switched active trading account to '{account.account_name}' ({account.broker.name})."
            messages.success(request, msg)
        else:
            default_acc = user.get_active_trading_account(request)
            request.session['active_account_id'] = default_acc.id if default_acc else None
            msg = f"Switched active trading account to default '{default_acc.account_name}'."
            messages.success(request, msg)

        response = HttpResponse()
        response['HX-Trigger'] = json.dumps({
            'showToast': {'message': msg, 'level': 'success'},
            'reloadPage': True
        })
        return response


class UserAccountCreateModalView(HtmxModalMixin, LoginRequiredMixin, View):
    """Render HTMX modal for creating a Live or Sandbox trading account."""
    modal_template_name = 'users/partials/account_create_modal.html'
    template_name = 'users/partials/account_create_modal.html'

    def get(self, request, *args, **kwargs):
        brokers = BrokerMaster.objects.filter(is_active=True).exclude(code='sandbox')
        if not brokers.exists():
            BrokerMaster.objects.get_or_create(code='dhan', defaults={'name': 'DHAN', 'description': 'Dhan Broker Platform'})
            BrokerMaster.objects.get_or_create(code='fyers', defaults={'name': 'FYERS', 'description': 'Fyers Broker Platform'})
            brokers = BrokerMaster.objects.filter(is_active=True).exclude(code='sandbox')

        return render(request, self.modal_template_name, {'brokers': brokers})


class UserAccountCreateView(LoginRequiredMixin, View):
    """Handle creating a new trading account with Live API Auth Hit verification."""
    def post(self, request, *args, **kwargs):
        user = request.user
        account_type = request.POST.get('account_type', 'LIVE').upper()
        is_default = request.POST.get('is_default') == 'on'

        try:
            if account_type == 'SANDBOX':
                account_name = request.POST.get('sandbox_account_name') or request.POST.get('account_name') or 'Sandbox Demo Account'
                try:
                    capital = float(request.POST.get('initial_capital', 100000))
                except ValueError:
                    capital = 100000.0

                sandbox_broker, _ = BrokerMaster.objects.get_or_create(
                    code='sandbox',
                    defaults={'name': 'SANDBOX', 'description': 'Paper Trading Sandbox'}
                )

                account = UserTradingAccount.objects.create(
                    user=user,
                    broker=sandbox_broker,
                    account_name=account_name,
                    account_type='SANDBOX',
                    is_default=is_default,
                    is_active=True,
                    is_configured=True,
                    account_summary={'initial_capital': capital, 'balance': capital}
                )

                if is_default or not user.trading_accounts.filter(is_default=True).exists():
                    user.trading_accounts.exclude(id=account.id).update(is_default=False)
                    account.is_default = True
                    account.save(update_fields=['is_default'])

                request.session['active_account_id'] = account.id
                msg = f"Sandbox Account '{account_name}' created with ₹{capital:,.2f} virtual capital!"
                messages.success(request, msg)
                level = 'success'

            else:
                # LIVE Account Creation with Auth Hit
                broker_id = request.POST.get('broker_id')
                broker = BrokerMaster.objects.filter(id=broker_id, is_deleted=False).first() if broker_id else None
                if not broker:
                    broker = BrokerMaster.objects.filter(code='dhan', is_deleted=False).first()
                if not broker:
                    broker = BrokerMaster.objects.filter(is_deleted=False).first()
                if not broker:
                    broker, _ = BrokerMaster.objects.get_or_create(code='dhan', defaults={'name': 'DHAN', 'description': 'Dhan Broker Platform'})

                account_name = request.POST.get('account_name') or f"{broker.name} Live Account"
                client_id = str(request.POST.get('broker_client_id', '')).strip().strip('"').strip("'")
                api_key = str(request.POST.get('api_key', '')).strip().strip('"').strip("'")
                app_id = str(request.POST.get('app_id', '')).strip().strip('"').strip("'")

                if not client_id or not api_key:
                    raise ValueError("Live trading accounts require Client ID and API Key / Access Token.")

                # Pre-save Live Authentication Validation Hit
                candidate_account = UserTradingAccount(
                    user=user,
                    broker=broker,
                    account_name=account_name,
                    account_type='LIVE',
                    broker_client_id=client_id,
                    api_key=api_key,
                    app_id=app_id,
                    is_default=is_default,
                    keep_alive=(request.POST.get('keep_alive') == 'on'),
                    is_active=True,
                    is_configured=False
                )

                adapter = BrokerFactory.get_adapter(candidate_account)
                auth_res = adapter.test_connection()
                is_auth_valid = (
                    auth_res.get('success') is True or 
                    auth_res.get('connected') is True or 
                    str(auth_res.get('status', '')).upper() in ['SUCCESS', 'CONNECTED', 'OK']
                )

                if not is_auth_valid:
                    err_msg = auth_res.get('message', 'Broker rejected authentication credentials.')
                    raise ValueError(f"Live Auth Validation Failed: {err_msg}")

                # Save only after live authentication passes
                candidate_account.is_configured = True
                candidate_account.account_summary = auth_res
                candidate_account.save()
                account = candidate_account

                if is_default or not user.trading_accounts.filter(is_default=True).exists():
                    user.trading_accounts.exclude(id=account.id).update(is_default=False)
                    account.is_default = True
                    account.save(update_fields=['is_default'])

                request.session['active_account_id'] = account.id
                msg = f"Live Account '{account_name}' ({broker.name}) verified and saved successfully!"
                messages.success(request, msg)
                level = 'success'

        except Exception as ex:
            logger.error(f"Error creating trading account: {ex}")
            msg = f"Failed to create account: {str(ex)}"
            messages.error(request, msg)
            level = 'error'

        if request.headers.get('HX-Request'):
            trigger_dict = {'showToast': {'message': msg, 'level': level}, 'refreshAccountsCards': True}
            if level == 'success':
                trigger_dict['closeGlobalModal'] = True
                trigger_dict['refreshAccounts'] = True

            status_code = 204 if level == 'success' else 200
            response = HttpResponse(status=status_code)
            response['HX-Trigger'] = json.dumps(trigger_dict)
            return response
        else:
            redirect_url = request.META.get('HTTP_REFERER') or reverse('users:marmot-profile')
            return redirect(redirect_url)


class UserAccountEditModalView(HtmxModalMixin, LoginRequiredMixin, View):
    """Render HTMX modal for editing an existing Live or Sandbox trading account."""
    modal_template_name = 'users/partials/account_edit_modal.html'
    template_name = 'users/partials/account_edit_modal.html'

    def get(self, request, pk, *args, **kwargs):
        user = request.user
        account = user.trading_accounts.filter(pk=pk, is_deleted=False).first()
        if not account and (user.is_superuser or getattr(user, 'role', '') in ['admin', 'developer']):
            account = UserTradingAccount.objects.filter(pk=pk, is_deleted=False).first()
        if not account:
            messages.error(request, "Trading account not found.")
            return HttpResponse('<div class="p-3 text-danger">Trading account not found.</div>')

        brokers = BrokerMaster.objects.filter(is_active=True).exclude(code='sandbox')
        return render(request, self.modal_template_name, {'account': account, 'brokers': brokers})


class UserAccountEditView(LoginRequiredMixin, View):
    """Handle editing an existing trading account with optional Live API re-validation."""
    def post(self, request, pk, *args, **kwargs):
        user = request.user
        account = user.trading_accounts.filter(pk=pk, is_deleted=False).first()
        if not account and (user.is_superuser or getattr(user, 'role', '') in ['admin', 'developer']):
            account = UserTradingAccount.objects.filter(pk=pk, is_deleted=False).first()

        if not account:
            msg = "Trading account not found."
            level = 'error'
        else:
            try:
                is_default = request.POST.get('is_default') == 'on'

                if account.account_type == 'SANDBOX':
                    account_name = request.POST.get('sandbox_account_name') or request.POST.get('account_name') or account.account_name
                    try:
                        capital = float(request.POST.get('initial_capital', 100000))
                    except ValueError:
                        capital = float(account.account_summary.get('initial_capital', 100000))

                    account.account_name = account_name
                    summary = dict(account.account_summary) if isinstance(account.account_summary, dict) else {}
                    summary['initial_capital'] = capital
                    summary['balance'] = capital
                    account.account_summary = summary
                    account.is_default = is_default
                    account.save()

                    if is_default:
                        account.user.trading_accounts.exclude(id=account.id).update(is_default=False)

                    msg = f"Sandbox Account '{account_name}' updated successfully!"
                    messages.success(request, msg)
                    level = 'success'
                else:
                    # LIVE Account Update
                    broker_id = request.POST.get('broker_id')
                    if broker_id:
                        broker = BrokerMaster.objects.filter(id=broker_id, is_deleted=False).first()
                        if broker:
                            account.broker = broker

                    account_name = request.POST.get('account_name') or account.account_name
                    client_id = str(request.POST.get('broker_client_id', '')).strip().strip('"').strip("'")
                    api_key = str(request.POST.get('api_key', '')).strip().strip('"').strip("'")
                    app_id = str(request.POST.get('app_id', '')).strip().strip('"').strip("'")

                    account.account_name = account_name
                    if client_id:
                        account.broker_client_id = client_id
                    if app_id:
                        account.app_id = app_id

                    # If a new API key was provided, re-test connection
                    if api_key:
                        account.api_key = api_key
                        adapter = BrokerFactory.get_adapter(account)
                        auth_res = adapter.test_connection()
                        is_auth_valid = (
                            auth_res.get('success') is True or 
                            auth_res.get('connected') is True or 
                            str(auth_res.get('status', '')).upper() in ['SUCCESS', 'CONNECTED', 'OK']
                        )
                        if not is_auth_valid:
                            err_msg = auth_res.get('message', 'Broker rejected authentication credentials.')
                            raise ValueError(f"Live Auth Validation Failed: {err_msg}")
                        account.is_configured = True
                        account.account_summary = auth_res

                    account.is_default = is_default
                    account.keep_alive = (request.POST.get('keep_alive') == 'on')
                    account.save()

                    if is_default:
                        account.user.trading_accounts.exclude(id=account.id).update(is_default=False)

                    msg = f"Live Account '{account_name}' updated successfully!"
                    messages.success(request, msg)
                    level = 'success'

            except Exception as ex:
                logger.error(f"Error updating trading account: {ex}")
                msg = f"Failed to update account: {str(ex)}"
                messages.error(request, msg)
                level = 'error'

        if request.headers.get('HX-Request'):
            trigger_dict = {'showToast': {'message': msg, 'level': level}, 'refreshAccountsCards': True}
            if level == 'success':
                trigger_dict['closeGlobalModal'] = True
                trigger_dict['refreshAccounts'] = True

            status_code = 204 if level == 'success' else 200
            response = HttpResponse(status=status_code)
            response['HX-Trigger'] = json.dumps(trigger_dict)
            return response
        else:
            redirect_url = request.META.get('HTTP_REFERER') or reverse('users:marmot-profile')
            return redirect(redirect_url)


class UserAccountsCardsView(LoginRequiredMixin, View):
    """Render the My Configured Trading Accounts cards partial on demand."""
    def get(self, request, *args, **kwargs):
        accounts = request.user.trading_accounts.filter(is_deleted=False).order_by('-is_default', 'id')
        context = {'user_trading_accounts': accounts}
        return render(request, 'users/partials/profile_accounts_cards.html', context)


class UserAccountTestAuthView(LoginRequiredMixin, View):
    """Trigger API connection test auth hit on an existing trading account."""
    def post(self, request, pk, *args, **kwargs):
        user = request.user
        account = user.trading_accounts.filter(pk=pk).first()

        if not account:
            msg = "Account not found."
            level = 'error'
        elif account.account_type == 'SANDBOX':
            msg = "Sandbox accounts operate locally in paper-trading mode."
            level = 'info'
        else:
            try:
                adapter = BrokerFactory.get_adapter(account)
                auth_res = adapter.test_connection()
            except Exception as e:
                auth_res = {'success': False, 'message': str(e)}

            if auth_res.get('success') is True or auth_res.get('connected') is True or str(auth_res.get('status', '')).upper() in ['SUCCESS', 'CONNECTED', 'OK']:
                account.is_configured = True
                account.account_summary = auth_res
                account.save(update_fields=['is_configured', 'account_summary'])
                msg = f"API Connection Verified for '{account.account_name}' ({account.broker.name})!"
                messages.success(request, msg)
                level = 'success'
            else:
                err_msg = auth_res.get('message', 'Authentication failed.')
                account.is_configured = False
                account.save(update_fields=['is_configured'])
                msg = f"Auth Verification Failed: {err_msg}"
                messages.error(request, msg)
                level = 'error'

        if request.headers.get('HX-Request'):
            accounts = user.trading_accounts.filter(is_deleted=False).order_by('-is_default', 'id')
            response = render(request, 'users/partials/profile_accounts_cards.html', {'user_trading_accounts': accounts})
            response['HX-Trigger'] = json.dumps({
                'showToast': {'message': msg, 'level': level},
                'refreshAccounts': True
            })
            return response

        return redirect(request.META.get('HTTP_REFERER') or reverse('users:marmot-profile'))


class UserAccountSetDefaultView(LoginRequiredMixin, View):
    """Set an account as the primary default account."""
    def post(self, request, pk, *args, **kwargs):
        user = request.user
        account = user.trading_accounts.filter(pk=pk).first()

        if account:
            user.trading_accounts.update(is_default=False)
            account.is_default = True
            account.save(update_fields=['is_default'])
            request.session['active_account_id'] = account.id
            msg = f"'{account.account_name}' is now your Primary Default Trading Account."
            messages.success(request, msg)
            level = 'success'
        else:
            msg = "Account not found."
            level = 'error'

        if request.headers.get('HX-Request'):
            accounts = user.trading_accounts.filter(is_deleted=False).order_by('-is_default', 'id')
            response = render(request, 'users/partials/profile_accounts_cards.html', {'user_trading_accounts': accounts})
            response['HX-Trigger'] = json.dumps({
                'showToast': {'message': msg, 'level': level},
                'refreshAccounts': True
            })
            return response

        return redirect(request.META.get('HTTP_REFERER') or reverse('users:marmot-profile'))


class UserAccountDeleteView(LoginRequiredMixin, View):
    """Delete a user trading account."""
    def post(self, request, pk, *args, **kwargs):
        user = request.user
        account = user.trading_accounts.filter(pk=pk).first()

        if account:
            acc_name = account.account_name
            account.delete()
            msg = f"Trading Account '{acc_name}' deleted."
            messages.success(request, msg)
            level = 'success'
        else:
            msg = "Account not found."
            level = 'error'

        if request.headers.get('HX-Request'):
            accounts = user.trading_accounts.filter(is_deleted=False).order_by('-is_default', 'id')
            response = render(request, 'users/partials/profile_accounts_cards.html', {'user_trading_accounts': accounts})
            response['HX-Trigger'] = json.dumps({
                'showToast': {'message': msg, 'level': level},
                'refreshAccounts': True
            })
            return response

        return redirect(request.META.get('HTTP_REFERER') or reverse('users:marmot-profile'))


class UserAccountConsentModalView(HtmxModalMixin, LoginRequiredMixin, View):
    """Render modal to authorize daily session or update Dhan/Fyers Access Token."""
    modal_template_name = 'users/partials/account_consent_modal.html'

    def get(self, request, pk, *args, **kwargs):
        account = get_object_or_404(UserTradingAccount, pk=pk, user=request.user, is_deleted=False)
        oauth_login_url = ""
        totp_login_url = "https://web.dhan.co"
        try:
            from apps.trade_core.services.dhan_token_service import UserDhanClient
            client = UserDhanClient(account)
            if account.app_id and account.api_key:
                consent_data = client.generate_login_url()
                oauth_login_url = consent_data.get('login_url', '')
        except Exception:
            pass

        if not oauth_login_url and account.broker and account.broker.name.lower() == 'dhan':
            oauth_login_url = reverse('trade_core:dhan-user-login-account', kwargs={'account_id': account.id})

        return render(request, self.modal_template_name, {
            'account': account,
            'oauth_login_url': oauth_login_url,
            'totp_login_url': totp_login_url,
        })


class UserAccountTotpTokenView(HtmxMessageMixin, LoginRequiredMixin, View):
    """Generates Dhan access token instantly via PIN & TOTP 2FA code (DhanHQ v2)."""

    def post(self, request, pk, *args, **kwargs):
        account = get_object_or_404(UserTradingAccount, pk=pk, user=request.user, is_deleted=False)
        pin = request.POST.get('pin', '').strip()
        totp = request.POST.get('totp', '').strip()

        if not pin or not totp:
            messages.error(request, "Please enter both 6-digit Dhan PIN and TOTP code.")
            response = HttpResponse(status=400)
            response['HX-Trigger'] = 'showToast'
            return response

        try:
            from apps.trade_core.services.dhan_token_service import UserDhanClient
            client = UserDhanClient(account)
            res = client.generate_access_token_via_totp(pin=pin, totp=totp)
            access_token = res.get('accessToken', '')
            if access_token:
                account.api_key = access_token
                account.save(update_fields=['api_key'])
                messages.success(request, f"✅ Dhan session authorized successfully for {account.broker_client_id} via TOTP!")
            else:
                messages.error(request, "Failed to acquire access token from Dhan API.")
        except Exception as e:
            logger.error("Dhan TOTP token generation error for account #%s: %s", account.id, e)
            messages.error(request, f"Dhan TOTP authentication failed: {e}")

        response = HttpResponse(status=200)
        response['HX-Trigger'] = 'reloadAccounts, closeHtmxModal'
        return response


class UserAccountRefreshTokenView(LoginRequiredMixin, View):
    """Update and validate fresh Access Token for a trading account."""
    def post(self, request, pk, *args, **kwargs):
        account = get_object_or_404(UserTradingAccount, pk=pk, user=request.user, is_deleted=False)
        fresh_token = str(request.POST.get('access_token', '')).strip().strip('"').strip("'")
        
        if not fresh_token:
            response = HttpResponse(status=400)
            response['HX-Trigger'] = json.dumps({'showToast': {'message': 'Please provide a valid Access Token.', 'level': 'danger'}})
            return response

        account.api_key = fresh_token
        adapter = BrokerFactory.get_adapter(account)
        auth_res = adapter.test_connection()

        if auth_res.get('success') is True or str(auth_res.get('status', '')).upper() in ['CONNECTED', 'SUCCESS', 'OK']:
            account.is_configured = True
            account.account_summary = auth_res
            account.save(update_fields=['api_key', 'is_configured', 'account_summary'])
            
            response = HttpResponse(status=200)
            response['HX-Trigger'] = json.dumps({
                'closeGlobalModal': True,
                'reloadPage': True,
                'showToast': {'message': 'Dhan Live Session authorized and connected successfully!', 'level': 'success'}
            })
            return response
        else:
            err_msg = auth_res.get('message', 'Authentication failed.')
            response = HttpResponse(status=422)
            response['HX-Trigger'] = json.dumps({'showToast': {'message': f'Validation Failed: {err_msg}', 'level': 'danger'}})
            return response


class UserAccountSettingsView(HTMXPartialMixin, MarmotRoleRequiredMixin, TemplateView):
    """View for user account & risk settings."""
    template_name = 'users/dashboard.html'
    partial_template_name = 'users/partials/account_settings_content.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        active_acc = populate_account_context(context, user, self.request)

        context['active_tab'] = 'accounts'
        context['strategy_configs'] = TradeExecConfig.objects.filter(
            admins_user=user,
            account_type=active_acc.account_type if active_acc else 'SANDBOX',
            is_deleted=False
        )
        return context


class UserKillSwitchView(HtmxModalMixin, LoginRequiredMixin, View):
    """View for user emergency kill switch trigger."""
    modal_template_name = 'users/partials/kill_switch_modal.html'
    template_name = 'users/partials/kill_switch_modal.html'

    def get(self, request, *args, **kwargs):
        return render(request, self.modal_template_name)

    def post(self, request, *args, **kwargs):
        user = request.user
        
        user_broker = getattr(user, 'broker', '')
        if user_broker and user_broker.lower() != 'dhan' and user_broker != BrokerChoices.DHAN:
            response = HttpResponse()
            msg = "Kill Switch trigger is currently implemented for Dhan broker users."
            response['HX-Trigger'] = json.dumps({
                'closeGlobalModal': True,
                'showToast': {'message': msg, 'level': 'warning'}
            })
            return response

        adapter = BrokerFactory.get_adapter(user)
        adapter.emergency_kill_switch()

        user.primary_freeze = True
        user.final_freeze = True
        user.trade_eligibility = False
        user.is_sandbox_trader_active = False
        user.is_live_trader_active = False
        user.save()

        response = HttpResponse()
        msg = f"EMERGENCY KILL SWITCH ACTIVATED! All active Dhan trades and orders for @{user.username} frozen."
        response['HX-Trigger'] = json.dumps({
            'closeGlobalModal': True,
            'showToast': {'message': msg, 'level': 'danger'}
        })
        return response


class LogoutView(View):
    """
    Logs out the user and redirects to login page.
    Supports HTMX client redirects if triggered via HTMX button.
    """
    def post(self, request, *args, **kwargs):
        auth_logout(request)
        login_url = str(reverse_lazy('users:marmot-login'))

        if request.headers.get('HX-Request'):
            response = HttpResponse(status=204)
            response['HX-Redirect'] = login_url
            return response

        return redirect(login_url)


# ==========================================
# USER PROFILE VIEW & SETTINGS
# ==========================================

class UserProfileView(HTMXPartialMixin, HtmxMessageMixin, LoginRequiredMixin, UpdateView):
    model = User
    form_class = UserProfileForm
    template_name = 'admins/user_profile.html'
    success_url = reverse_lazy('users:marmot-profile')
    success_message = UserMessages.PROFILE_UPDATED

    def get_object(self, queryset=None):
        pk = self.kwargs.get('pk')
        if pk and (self.request.user.is_superuser or getattr(self.request.user, 'role', '') in ['admin', 'developer']):
            return User.objects.filter(pk=pk).first() or self.request.user
        return self.request.user

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request_user'] = self.request.user
        return kwargs

    def get_template_names(self):
        if self.request.headers.get('HX-Request'):
            target = self.request.headers.get('HX-Target')
            if target == 'user-profile-container':
                if self.request.GET.get('edit') == '1':
                    return ['admins/partials/user_profile_edit_content.html']
                return ['admins/partials/user_profile_showcase_content.html']
            return ['admins/partials/user_profile_page_content.html']
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user_obj = self.object or self.request.user
        is_edit = self.request.GET.get('edit') == '1' or bool(self.request.POST)

        user_role = getattr(self.request.user, 'role', '')
        is_admin = self.request.user.is_superuser or user_role in ['admin', 'developer', 'staff']
        context['base_template'] = 'admins/index.html' if is_admin else 'users/index.html'

        context['profile_user'] = user_obj
        context['page_title'] = "User Profile" if not is_edit else "Edit User Profile"
        context['is_edit'] = is_edit
        context['is_admin_or_dev'] = is_admin
        context['user_trading_accounts'] = user_obj.trading_accounts.filter(is_deleted=False).order_by('-is_default', 'id')
        context['active_trading_account'] = user_obj.get_active_trading_account(self.request)
        context['has_broker_credentials'] = bool(
            user_obj and (user_obj.broker or user_obj.broker_client_id or user_obj.api_key)
        )
        return context


class UserProfilePasswordChangeView(HtmxModalMixin, LoginRequiredMixin, FormView):
    """View for users and admins to change their own password via modal."""
    form_class = UserProfilePasswordChangeForm
    modal_template_name = 'admins/partials/user_password_change_modal.html'
    template_name = 'admins/partials/user_password_change_modal.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        user = form.save()
        update_session_auth_hash(self.request, user)

        response = HttpResponse()
        response['HX-Trigger'] = json.dumps({
            'closeGlobalModal': True,
            'showToast': {'message': "Your password has been changed successfully!", 'level': 'success'}
        })
        return response

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))