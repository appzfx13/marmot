import io
import json
import logging
import os
import uuid
import zipfile
from django.conf import settings
from django.contrib import messages

logger = logging.getLogger(__name__)
from django.contrib.auth import login as auth_login, logout as auth_logout, update_session_auth_hash
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView
from django.http import FileResponse, HttpResponse, HttpResponseForbidden, Http404
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import FormView, TemplateView, UpdateView

from apps.backtest.models import BacktestTask
from apps.common.choices import BrokerChoices
from apps.common.mixins import HtmxMessageMixin, HtmxModalMixin
from apps.market.models import MarketBackupTask
from apps.trade_config.models import TradeExecConfig, UserTradingAccount, BrokerMaster
from apps.trade_core.brokers import BrokerFactory
from .forms import UserProfileForm, UserProfilePasswordChangeForm, UserBacktestTaskForm, UserMarketBackupTaskForm
from .mixins import HTMXPartialMixin, MarmotRoleRequiredMixin
from .models import User
from .permissions import is_user_authorized_for_dashboard
from .services import get_user_profile


class LoginView(HTMXPartialMixin, LoginView):
    template_name = 'registration/login.html'
    partial_template_name = 'admins/partials/login_form.html'
    redirect_authenticated_user = True

    def form_valid(self, form):
        auth_login(self.request, form.get_user())
        success_url = self.get_success_url()

        if self.request.headers.get('HX-Request'):
            response = HttpResponse()
            response['HX-Redirect'] = str(success_url)
            return response
        return redirect(success_url)

    def form_invalid(self, form):
        if self.request.headers.get('HX-Request'):
            return render(
                self.request,
                self.partial_template_name,
                self.get_context_data(form=form),
                status=422
            )
        return super().form_invalid(form)

    def get_success_url(self):
        if is_user_authorized_for_dashboard(self.request.user):
            user_role = getattr(self.request.user, 'role', '')
            if self.request.user.is_superuser or user_role in ['admin', 'developer', 'staff']:
                return reverse_lazy('admins:admin-dashboard')
            return reverse_lazy('users:marmot-dashboard')
        return reverse_lazy('users:marmot-login')


def populate_account_context(context, user, request):
    """Helper function to populate active trading account context across user views."""
    active_acc = user.get_active_trading_account(request)
    accounts = list(user.trading_accounts.filter(is_active=True).order_by('-is_default', 'account_type', 'account_name'))
    
    context['active_trading_account'] = active_acc
    context['user_trading_accounts'] = accounts
    context['watching_on'] = active_acc.account_type if active_acc else 'SANDBOX'
    return active_acc


class UserDashboardView(HTMXPartialMixin, MarmotRoleRequiredMixin, TemplateView):
    """Protected Marmot Dashboard View serving dashboard_content.html partial for HTMX."""
    template_name = 'users/dashboard.html'
    partial_template_name = 'users/partials/dashboard_content.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        active_acc = populate_account_context(context, user, self.request)

        context['active_tab'] = 'dashboard'
        context['marmot_profile'] = get_user_profile(user.username)
        context['total_traders'] = User.objects.filter(is_superuser=False).count()
        context['active_traders'] = User.objects.filter(is_superuser=False, trade_eligibility=True, is_blocked=False).count()
        context['strategy_configs'] = TradeExecConfig.objects.filter(
            admins_user=user,
            account_type=active_acc.account_type if active_acc else 'SANDBOX',
            is_deleted=False
        )
        return context


class UserJournalView(HTMXPartialMixin, MarmotRoleRequiredMixin, TemplateView):
    """View for user execution journal."""
    template_name = 'users/dashboard.html'
    partial_template_name = 'users/partials/journal_content.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        populate_account_context(context, user, self.request)
        context['active_tab'] = 'journal'
        return context


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
    """View for user market backups."""
    template_name = 'users/dashboard.html'
    partial_template_name = 'users/partials/backup_content.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_tab'] = 'backup'
        user_backups = MarketBackupTask.objects.filter(is_deleted=False, created_by=self.request.user).order_by('-id')
        context['backup_tasks'] = user_backups
        return context


class UserBackupCreateView(HtmxModalMixin, LoginRequiredMixin, FormView):
    """Modal view for user to request options data backup."""
    form_class = UserMarketBackupTaskForm
    modal_template_name = 'users/partials/user_backup_create_modal.html'
    template_name = 'users/partials/user_backup_create_modal.html'

    def form_valid(self, form):
        backup = form.save(commit=False)
        backup.created_by = self.request.user
        backup.status = 'CREATED'
        backup.save()

        response = HttpResponse(status=204)
        msg = f"Market backup request #{backup.id} created successfully!"
        response['HX-Trigger'] = json.dumps({
            'closeGlobalModal': True,
            'showToast': {'message': msg, 'level': 'success'},
            'reloadBackupList': True
        })
        return response

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))


class UserBackupDownloadView(LoginRequiredMixin, View):
    """Secure file download view for user's generated backup parquet files."""
    def get(self, request, pk, *args, **kwargs):
        backup = MarketBackupTask.objects.filter(pk=pk, is_deleted=False).first()
        if not backup or (backup.created_by and backup.created_by != request.user and not request.user.is_superuser):
            return HttpResponseForbidden("You do not have access to download this backup dataset.")

        user_id = str(backup.created_by.id if getattr(backup, 'created_by', None) else 1)
        backup_id = str(backup.id)
        index_name = backup.index_name.lower()

        candidate_paths = [
            backup.parquet_file_path,
            os.path.join(settings.BASE_DIR, 'backup', user_id, backup_id),
            os.path.join('/app', 'backup', user_id, backup_id),
            os.path.join(settings.BASE_DIR, 'go-app', 'data', 'users', user_id, f"{index_name}_options"),
        ]

        target_path = None
        for p in candidate_paths:
            if p and os.path.exists(p):
                target_path = p
                break

        if not target_path:
            raise Http404("Backup data directory or file not found on disk.")

        zip_buffer = io.BytesIO()
        zip_filename = f"{index_name}_backup_task_{backup.id}.zip"

        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            if os.path.isdir(target_path):
                for root, _, files in os.walk(target_path):
                    for file in files:
                        full_path = os.path.join(root, file)
                        rel_path = os.path.relpath(full_path, target_path)
                        zip_file.write(full_path, arcname=rel_path)
            else:
                zip_file.write(target_path, arcname=os.path.basename(target_path))

        zip_buffer.seek(0)
        return FileResponse(zip_buffer, as_attachment=True, filename=zip_filename)


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
                client_id = request.POST.get('broker_client_id', '').strip() or f"CLIENT_{uuid.uuid4().hex[:6].upper()}"
                api_key = request.POST.get('api_key', '').strip()
                app_id = request.POST.get('app_id', '').strip()

                account = UserTradingAccount.objects.create(
                    user=user,
                    broker=broker,
                    account_name=account_name,
                    account_type='LIVE',
                    broker_client_id=client_id,
                    api_key=api_key,
                    app_id=app_id,
                    is_default=is_default,
                    is_active=True,
                    is_configured=bool(client_id and api_key)
                )

                # Perform API Auth Hit if credentials provided
                if api_key:
                    try:
                        adapter = BrokerFactory.get_adapter(account)
                        auth_res = adapter.test_connection()
                        account.account_summary = auth_res
                        account.is_configured = (
                            auth_res.get('success') is True or 
                            auth_res.get('connected') is True or 
                            str(auth_res.get('status', '')).upper() in ['SUCCESS', 'CONNECTED', 'OK']
                        )
                        account.save(update_fields=['is_configured', 'account_summary'])
                    except Exception as e:
                        logger.error(f"Error testing broker connection for {account_name}: {e}")

                if is_default or not user.trading_accounts.filter(is_default=True).exists():
                    user.trading_accounts.exclude(id=account.id).update(is_default=False)
                    account.is_default = True
                    account.save(update_fields=['is_default'])

                request.session['active_account_id'] = account.id
                msg = f"Live Account '{account_name}' ({broker.name}) created and configured successfully!"
                messages.success(request, msg)
                level = 'success'

        except Exception as ex:
            logger.error(f"Error creating trading account: {ex}")
            msg = f"Failed to create account: {str(ex)}"
            messages.error(request, msg)
            level = 'error'

        if request.headers.get('HX-Request'):
            trigger_dict = {'showToast': {'message': msg, 'level': level}}
            if level == 'success':
                trigger_dict['closeGlobalModal'] = True
                trigger_dict['reloadPage'] = True

            status_code = 204 if level == 'success' else 200
            response = HttpResponse(status=status_code)
            response['HX-Trigger'] = json.dumps(trigger_dict)
            return response
        else:
            redirect_url = request.META.get('HTTP_REFERER') or reverse('users:marmot-profile')
            return redirect(redirect_url)


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

        response = HttpResponse()
        response['HX-Trigger'] = json.dumps({
            'showToast': {'message': msg, 'level': level},
            'reloadPage': True
        })
        return response


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

        response = HttpResponse()
        response['HX-Trigger'] = json.dumps({
            'showToast': {'message': msg, 'level': level},
            'reloadPage': True
        })
        return response


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

        response = HttpResponse()
        response['HX-Trigger'] = json.dumps({
            'showToast': {'message': msg, 'level': level},
            'reloadPage': True
        })
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
    success_message = "Profile settings updated successfully!"

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
            if self.request.GET.get('edit') == '1':
                return ['admins/partials/user_profile_edit_content.html']
            return ['admins/partials/user_profile_showcase_content.html']
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