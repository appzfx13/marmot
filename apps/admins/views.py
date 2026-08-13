
from django.shortcuts import render, redirect
from django.contrib import messages
from django.views.generic import DeleteView
from django.urls import reverse_lazy
import json



from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib.auth.views import LoginView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    FormView,
    ListView,
    TemplateView,
    UpdateView,
)
from django.conf import settings
from django_filters.views import FilterView

from apps.users.models import User, MemberRoleChoices, BrokerChoices, PLStatusChoices
from apps.users.mixins import HTMXPartialMixin
from apps.trade_config.models import TradeExecConfig, BrokerMaster
from apps.common.mixins import HtmxMessageMixin, HtmxModalMixin
from apps.admins.constants import Messages
from apps.admins.filters import TradeExecConfigFilter
from .permissions import AdminRequiredMixin
from .forms import TradeExecConfigForm, UserForm, AdminTraderPasswordResetForm, BrokerMasterForm


# ==========================================
# AUTH & DASHBOARD VIEWS
# ==========================================

class AdminLoginView(HTMXPartialMixin, HtmxMessageMixin, LoginView):
    template_name = 'admins/login.html'
    partial_template_name = 'admins/partials/login_form.html'
    redirect_authenticated_user = True

    def form_valid(self, form):
        try:
            auth_login(self.request, form.get_user())
            success_url = str(self.get_success_url())
            if self.request.headers.get('HX-Request'):
                response = HttpResponse(status=204)
                response['HX-Redirect'] = success_url
                return response
            return redirect(success_url)

        except Exception as e:
            form.add_error(None, f"An unexpected error occurred: {str(e)}")
            return self.form_invalid(form)

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
        user_role = getattr(self.request.user, 'role', '')
        if self.request.user.is_superuser or user_role in ['admin', 'developer', 'staff']:
            return reverse_lazy('admins:admin-dashboard')
        return reverse_lazy('users:marmot-dashboard')


class AdminDashboardView(HTMXPartialMixin, LoginRequiredMixin, AdminRequiredMixin, TemplateView):
    """
    Protected Admin Dashboard View.
    """
    template_name = 'admins/dashboard.html'
    partial_template_name = 'admins/partials/dashboard_content.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['total_traders'] = User.objects.filter(role=MemberRoleChoices.TRADERS).count()
        context['active_traders'] = User.objects.filter(
            role=MemberRoleChoices.TRADERS, trade_eligibility=True
        ).count()
        return context


class AdminLogoutView(View):
    """
    Logs out the admin user with HTMX client-side redirect support.
    """
    def post(self, request, *args, **kwargs):
        auth_logout(request)
        messages.info(request, Messages.LOGOUT_SUCCESS)
        login_url = str(reverse_lazy('admins:admin-login'))

        if request.headers.get('HX-Request'):
            response = HttpResponse(status=204)
            response['HX-Redirect'] = login_url
            return response

        return redirect(login_url)


# ==========================================
# TRADER MANAGEMENT VIEWS
# ==========================================

class AdminTraderListView(HTMXPartialMixin, LoginRequiredMixin, AdminRequiredMixin, ListView):
    model = User
    template_name = 'admins/trader_list.html'
    partial_template_name = 'admins/partials/trader_table.html'
    context_object_name = 'traders'
    paginate_by = settings.PAGINATION_COUNT

    def get_queryset(self):
        queryset = super().get_queryset().filter(role=MemberRoleChoices.TRADERS, is_deleted=False)

        # --- Search & Filters ---
        q = self.request.GET.get('q', '').strip()
        if q:
            queryset = queryset.filter(
                Q(first_name__icontains=q) |
                Q(username__icontains=q) |
                Q(email__icontains=q)
            )

        broker = self.request.GET.get('broker', '').strip()
        if broker:
            queryset = queryset.filter(broker=broker)

        phone_number = self.request.GET.get('phone_number', '').strip()
        if phone_number:
            queryset = queryset.filter(phone_number__icontains=phone_number)

        trade_eligibility = self.request.GET.get('trade_eligibility', '').strip()
        if trade_eligibility in ['true', 'false']:
            queryset = queryset.filter(trade_eligibility=(trade_eligibility == 'true'))

        # --- Sorting ---
        sort = self.request.GET.get('sort', 'username').strip()
        allowed_sort_fields = ['username', '-username', 'first_name', '-first_name', 'created_at', '-created_at']
        
        if sort in allowed_sort_fields:
            queryset = queryset.order_by(sort)
        else:
            queryset = queryset.order_by('username')  # Default fallback sorting

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['BrokerChoices'] = BrokerChoices
        context['MemberRoleChoices'] = MemberRoleChoices
        context['PLStatusChoices'] = PLStatusChoices

        # Preserve sort parameter state in context
        context['current_sort'] = self.request.GET.get('sort', 'username').strip()

        # Preserve search and filter parameters for HTMX pagination and sorting links
        query_params = self.request.GET.copy()
        query_params.pop('page', None)
        query_params.pop('sort', None)  # Prevent duplicate sort params in current_filters string
        context['current_filters'] = query_params.urlencode()

        return context


class AdminTraderCreateView(HtmxMessageMixin, LoginRequiredMixin, AdminRequiredMixin, CreateView):
    model = User
    form_class = UserForm
    template_name = 'admins/trader_form.html'
    success_url = reverse_lazy('admins:trader_list')
    success_message = Messages.TRADER_CREATED

    def form_valid(self, form):
        form.instance.role = MemberRoleChoices.TRADERS
        return super().form_valid(form)


class AdminTraderUpdateView(HtmxMessageMixin, LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    model = User
    form_class = UserForm
    template_name = 'admins/trader_form.html'
    success_url = reverse_lazy('admins:trader_list')
    success_message = Messages.TRADER_UPDATED

    def get_queryset(self):
        return super().get_queryset().filter(role=MemberRoleChoices.TRADERS)


class AdminTraderDetailView(LoginRequiredMixin, AdminRequiredMixin, DetailView):
    model = User
    template_name = 'admins/trader_detail.html'
    context_object_name = 'trader'

    def get_queryset(self):
        return super().get_queryset().filter(role=MemberRoleChoices.TRADERS)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        trader = self.object
        context['profile_user'] = trader
        context['exec_config'] = TradeExecConfig.objects.filter(admins_user=trader).first()
        context['user_trading_accounts'] = trader.trading_accounts.filter(is_deleted=False).order_by('-is_default', 'id')
        context['active_trading_account'] = trader.get_active_trading_account(self.request)
        context['is_admin_or_dev'] = True
        return context



class AdminTraderDeleteView(HtmxModalMixin, HtmxMessageMixin, LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    model = User
    modal_template_name = 'admins/partials/confirm_delete.html'
    template_name = 'admins/partials/confirm_delete.html'
    success_message = "Trader deleted successfully."

    def get_queryset(self):
        return super().get_queryset().filter(role=MemberRoleChoices.TRADERS, is_deleted=False)

    def post(self, request, *args, **kwargs):
        # 1. Soft delete logic
        self.object = self.get_object()
        self.object.is_deleted = True
        self.object.save()

        # 2. Return an empty response (HTMX doesn't need HTML if we just want to trigger events)
        response = HttpResponse()
        
        # 3. Add a trigger to tell the frontend to close the modal, show toast, and reload the table!
        response['HX-Trigger'] = json.dumps({
            'closeGlobalModal': True, 
            'showToast': {'message': str(self.success_message), 'level': 'success'},
            'reloadTraderTable': True  # <-- NEW TRIGGER added here
        })
        return response


class AdminTraderPasswordResetView(HtmxModalMixin, LoginRequiredMixin, AdminRequiredMixin, FormView):
    """View for admins to reset a trader's password with confirmation modal."""
    form_class = AdminTraderPasswordResetForm
    modal_template_name = 'admins/partials/admin_trader_password_modal.html'
    template_name = 'admins/partials/admin_trader_password_modal.html'

    def get_trader(self):
        return get_object_or_404(User, pk=self.kwargs.get('pk'), role=MemberRoleChoices.TRADERS, is_deleted=False)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['trader'] = self.get_trader()
        return context

    def form_valid(self, form):
        trader = self.get_trader()
        new_password = form.cleaned_data['new_password']
        trader.set_password(new_password)
        trader.save()

        response = HttpResponse()
        msg = f"Password for trader '{trader.username}' updated successfully!"
        response['HX-Trigger'] = json.dumps({
            'closeGlobalModal': True,
            'showToast': {'message': msg, 'level': 'success'},
            'reloadTraderTable': True
        })
        return response

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))


# ==========================================
# TRADE EXECUTION CONFIGURATION VIEWS
# ==========================================
# Update the view definition
class AdminTradeExecConfigListView(HTMXPartialMixin, LoginRequiredMixin, AdminRequiredMixin, FilterView):
    model = TradeExecConfig
    filterset_class = TradeExecConfigFilter
    template_name = 'admins/trade_exec_config_list.html'
    partial_template_name = 'admins/partials/trade_exec_config_table_partial.html'
    context_object_name = 'configs'
    paginate_by = settings.PAGINATION_COUNT

    def get_queryset(self):
        return super().get_queryset().select_related('admins_user')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        query_params = self.request.GET.copy()
        if 'page' in query_params:
            del query_params['page']
        context['current_filters'] = query_params.urlencode()
        return context


class AdminTradeExecConfigDetailView(LoginRequiredMixin, AdminRequiredMixin, DetailView):
    model = TradeExecConfig
    template_name = 'admins/trade_exec_config_detail.html'
    context_object_name = 'config'


class AdminTradeExecConfigCreateView(HtmxMessageMixin, LoginRequiredMixin, AdminRequiredMixin, CreateView):
    model = TradeExecConfig
    form_class = TradeExecConfigForm
    template_name = 'admins/trade_exec_config_form.html'
    success_url = reverse_lazy('admins:trade_exec_config_list')
    success_message = Messages.CONFIG_CREATED


class AdminTradeExecConfigUpdateView(HtmxMessageMixin, LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    model = TradeExecConfig
    form_class = TradeExecConfigForm
    template_name = 'admins/trade_exec_config_form.html'
    success_url = reverse_lazy('admins:trade_exec_config_list')
    success_message = Messages.CONFIG_UPDATED


class AdminTradeExecConfigDeleteView(HtmxModalMixin, HtmxMessageMixin, LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    model = TradeExecConfig
    # Use the reusable global delete confirmation modal template
    modal_template_name = 'admins/partials/confirm_delete.html'
    template_name = 'admins/partials/confirm_delete.html' 
    success_url = reverse_lazy('admins:trade_exec_config_list')
    success_message = Messages.CONFIG_DELETED

    def post(self, request, *args, **kwargs):
        # 1. Fetch and delete the object (use self.object.is_deleted = True if you use soft deletes for configs)
        self.object = self.get_object()
        self.object.delete()

        # 2. Return an empty response (no need to render HTML)
        response = HttpResponse()
        
        # 3. Trigger the frontend events
        response['HX-Trigger'] = json.dumps({
            'closeGlobalModal': True, 
            'showToast': {'message': str(self.success_message), 'level': 'success'},
            'reloadConfigTable': True  # <-- Triggers the table reload on the list page
        })
        return response


# ==========================================
# POSTBACK & WEBHOOK AUDIT LOG VIEWS
# ==========================================

from apps.common.models import PostbackLog
from apps.admins.permissions import DeveloperOrAdminRequiredMixin

class PostbackLogListView(HTMXPartialMixin, LoginRequiredMixin, DeveloperOrAdminRequiredMixin, ListView):
    model = PostbackLog
    template_name = 'admins/postback_list.html'
    partial_template_name = 'admins/partials/postback_list_content.html'
    context_object_name = 'postbacks'
    paginate_by = 10

    def get_queryset(self):
        queryset = PostbackLog.objects.filter(is_deleted=False).select_related('user')

        # Filter by Search Query (Order ID, Symbol, Status, Broker, Dhan Client ID)
        q = self.request.GET.get('q')
        if q:
            queryset = queryset.filter(
                Q(order_id__icontains=q) |
                Q(dhan_client_id__icontains=q) |
                Q(symbol__icontains=q) |
                Q(order_status__icontains=q) |
                Q(broker__icontains=q) |
                Q(user__username__icontains=q)
            )

        # Filter by User
        user_id = self.request.GET.get('user_id')
        if user_id:
            queryset = queryset.filter(user_id=user_id)

        # Filter by Date Range
        start_date = self.request.GET.get('start_date')
        end_date = self.request.GET.get('end_date')
        if start_date:
            queryset = queryset.filter(created_at__date__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__date__lte=end_date)

        return queryset.order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = "Postback & Webhook Audit Logs"
        context['users_list'] = User.objects.filter(is_active=True).order_by('username')
        context['current_q'] = self.request.GET.get('q', '')
        context['current_user_id'] = self.request.GET.get('user_id', '')
        context['current_start_date'] = self.request.GET.get('start_date', '')
        context['current_end_date'] = self.request.GET.get('end_date', '')
        return context


class PostbackLogDetailView(LoginRequiredMixin, DeveloperOrAdminRequiredMixin, DetailView):
    model = PostbackLog
    template_name = 'admins/partials/postback_detail_modal.html'
    context_object_name = 'postback'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['formatted_payload'] = json.dumps(self.object.payload, indent=2)
        return context


# ==========================================
# BROKER MASTER MANAGEMENT VIEWS
# ==========================================

class AdminBrokerMasterListView(HTMXPartialMixin, AdminRequiredMixin, ListView):
    """View to list all Master Brokers configured in the system."""
    model = BrokerMaster
    template_name = 'admins/broker_master_list.html'
    partial_template_name = 'admins/partials/broker_master_list_content.html'
    context_object_name = 'brokers'
    paginate_by = 10

    def get_queryset(self):
        if not BrokerMaster.objects.filter(is_deleted=False).exists():
            BrokerMaster.objects.get_or_create(code='dhan', defaults={'name': 'DHAN', 'api_base_url': 'https://api.dhan.co', 'description': 'Dhan Broker API Gateway'})
            BrokerMaster.objects.get_or_create(code='fyers', defaults={'name': 'FYERS', 'api_base_url': 'https://api-v2.fyers.in', 'description': 'Fyers Broker API Gateway'})
            BrokerMaster.objects.get_or_create(code='sandbox', defaults={'name': 'SANDBOX', 'description': 'Default Paper Trading Broker Platform'})

        qs = BrokerMaster.objects.filter(is_deleted=False).order_by('name')
        search_query = self.request.GET.get('q', '').strip()
        if search_query:
            qs = qs.filter(Q(name__icontains=search_query) | Q(code__icontains=search_query))
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_tab'] = 'broker_master'
        context['total_brokers'] = BrokerMaster.objects.filter(is_deleted=False).count()
        context['active_brokers_count'] = BrokerMaster.objects.filter(is_deleted=False, is_active=True).count()
        return context


class AdminBrokerMasterCreateModalView(HtmxModalMixin, AdminRequiredMixin, View):
    """Render modal for creating new master broker."""
    modal_template_name = 'admins/partials/broker_master_modal.html'
    template_name = 'admins/partials/broker_master_modal.html'

    def get(self, request, *args, **kwargs):
        form = BrokerMasterForm()
        return render(request, self.modal_template_name, {'form': form, 'is_edit': False})


class AdminBrokerMasterSaveView(AdminRequiredMixin, View):
    """Handle creating or updating a Master Broker."""
    def post(self, request, pk=None, *args, **kwargs):
        broker = get_object_or_404(BrokerMaster, pk=pk, is_deleted=False) if pk else None
        form = BrokerMasterForm(request.POST, instance=broker)

        if form.is_valid():
            broker_obj = form.save()
            action_txt = "updated" if pk else "created"
            msg = f"Master Broker '{broker_obj.name}' ({broker_obj.code}) {action_txt} successfully!"
            messages.success(request, msg)

            response = HttpResponse()
            response['HX-Trigger'] = json.dumps({
                'closeGlobalModal': True,
                'showToast': {'message': msg, 'level': 'success'},
                'reloadPage': True
            })
            return response
        else:
            msg = f"Failed to save broker: {form.errors.as_text()}"
            messages.error(request, msg)
            response = HttpResponse()
            response['HX-Trigger'] = json.dumps({'showToast': {'message': msg, 'level': 'error'}})
            return response


class AdminBrokerMasterUpdateModalView(HtmxModalMixin, AdminRequiredMixin, View):
    """Render modal for editing master broker."""
    modal_template_name = 'admins/partials/broker_master_modal.html'
    template_name = 'admins/partials/broker_master_modal.html'

    def get(self, request, pk, *args, **kwargs):
        broker = get_object_or_404(BrokerMaster, pk=pk, is_deleted=False)
        form = BrokerMasterForm(instance=broker)
        return render(request, self.modal_template_name, {'form': form, 'broker': broker, 'is_edit': True})


class AdminBrokerMasterDeleteModalView(HtmxModalMixin, AdminRequiredMixin, View):
    """Render delete confirmation modal for master broker."""
    modal_template_name = 'admins/partials/broker_master_delete_modal.html'
    template_name = 'admins/partials/broker_master_delete_modal.html'

    def get(self, request, pk, *args, **kwargs):
        broker = get_object_or_404(BrokerMaster, pk=pk, is_deleted=False)
        return render(request, self.modal_template_name, {'broker': broker})


class AdminBrokerMasterDeleteView(AdminRequiredMixin, View):
    """Soft delete a master broker."""
    def post(self, request, pk, *args, **kwargs):
        broker = get_object_or_404(BrokerMaster, pk=pk, is_deleted=False)
        name = broker.name
        broker.is_deleted = True
        broker.is_active = False
        broker.save(update_fields=['is_deleted', 'is_active'])

        msg = f"Master Broker '{name}' soft-deleted successfully!"
        messages.success(request, msg)

        response = HttpResponse()
        response['HX-Trigger'] = json.dumps({
            'closeGlobalModal': True,
            'showToast': {'message': msg, 'level': 'success'},
            'reloadPage': True
        })
        return response


# ==========================================
# BULK DELETE CBV VIEWS
# ==========================================

class AdminTraderBulkDeleteView(LoginRequiredMixin, AdminRequiredMixin, View):
    """CBV for bulk soft-deletion of traders via HTMX."""
    def get(self, request, *args, **kwargs):
        ids_raw = request.GET.get('ids', '')
        ids_list = [i.strip() for i in ids_raw.split(',') if i.strip().isdigit()]
        count = len(ids_list)
        context = {
            'count': count,
            'ids_str': ','.join(ids_list),
            'item_name': 'trader' if count == 1 else 'traders',
            'post_url': reverse_lazy('admins:trader_bulk_delete'),
        }
        return render(request, 'admins/partials/confirm_bulk_delete.html', context)

    def post(self, request, *args, **kwargs):
        ids_raw = request.POST.get('ids', '')
        ids_list = [int(i.strip()) for i in ids_raw.split(',') if i.strip().isdigit()]
        if ids_list:
            qs = User.objects.filter(id__in=ids_list, role=MemberRoleChoices.TRADERS, is_deleted=False)
            count = qs.count()
            qs.update(is_deleted=True)
            msg = f"Successfully deleted {count} trader{'s' if count != 1 else ''}."
        else:
            msg = "No valid traders selected."
            count = 0

        response = HttpResponse()
        response['HX-Trigger'] = json.dumps({
            'closeGlobalModal': True,
            'showToast': {'message': msg, 'level': 'success' if count > 0 else 'warning'},
            'reloadTraderTable': True
        })
        return response


class AdminTradeExecConfigBulkDeleteView(LoginRequiredMixin, AdminRequiredMixin, View):
    """CBV for bulk deletion of trade configurations via HTMX."""
    def get(self, request, *args, **kwargs):
        ids_raw = request.GET.get('ids', '')
        ids_list = [i.strip() for i in ids_raw.split(',') if i.strip().isdigit()]
        count = len(ids_list)
        context = {
            'count': count,
            'ids_str': ','.join(ids_list),
            'item_name': 'configuration' if count == 1 else 'configurations',
            'post_url': reverse_lazy('admins:trade_exec_config_bulk_delete'),
        }
        return render(request, 'admins/partials/confirm_bulk_delete.html', context)

    def post(self, request, *args, **kwargs):
        ids_raw = request.POST.get('ids', '')
        ids_list = [int(i.strip()) for i in ids_raw.split(',') if i.strip().isdigit()]
        if ids_list:
            qs = TradeExecConfig.objects.filter(id__in=ids_list, is_deleted=False)
            count = qs.count()
            qs.update(is_deleted=True)
            msg = f"Successfully deleted {count} configuration{'s' if count != 1 else ''}."
        else:
            msg = "No valid configurations selected."
            count = 0

        response = HttpResponse()
        response['HX-Trigger'] = json.dumps({
            'closeGlobalModal': True,
            'showToast': {'message': msg, 'level': 'success' if count > 0 else 'warning'},
            'reloadConfigTable': True
        })
        return response


class PostbackLogBulkDeleteView(LoginRequiredMixin, DeveloperOrAdminRequiredMixin, View):
    """CBV for bulk soft-deletion of postback audit logs via HTMX."""
    def get(self, request, *args, **kwargs):
        ids_raw = request.GET.get('ids', '')
        ids_list = [i.strip() for i in ids_raw.split(',') if i.strip().isdigit()]
        count = len(ids_list)
        context = {
            'count': count,
            'ids_str': ','.join(ids_list),
            'item_name': 'postback log' if count == 1 else 'postback logs',
            'post_url': reverse_lazy('admins:postback_bulk_delete'),
        }
        return render(request, 'admins/partials/confirm_bulk_delete.html', context)

    def post(self, request, *args, **kwargs):
        ids_raw = request.POST.get('ids', '')
        ids_list = [int(i.strip()) for i in ids_raw.split(',') if i.strip().isdigit()]
        if ids_list:
            qs = PostbackLog.objects.filter(id__in=ids_list, is_deleted=False)
            count = qs.count()
            qs.update(is_deleted=True)
            msg = f"Successfully deleted {count} postback log{'s' if count != 1 else ''}."
        else:
            msg = "No valid postback logs selected."
            count = 0

        response = HttpResponse()
        response['HX-Trigger'] = json.dumps({
            'closeGlobalModal': True,
            'showToast': {'message': msg, 'level': 'success' if count > 0 else 'warning'},
            'reloadPostbackTable': True
        })
        return response


class AdminBrokerMasterBulkDeleteView(LoginRequiredMixin, AdminRequiredMixin, View):
    """CBV for bulk soft-deletion of master brokers via HTMX."""
    def get(self, request, *args, **kwargs):
        ids_raw = request.GET.get('ids', '')
        ids_list = [i.strip() for i in ids_raw.split(',') if i.strip().isdigit()]
        count = len(ids_list)
        context = {
            'count': count,
            'ids_str': ','.join(ids_list),
            'item_name': 'master broker' if count == 1 else 'master brokers',
            'post_url': reverse_lazy('admins:broker-master-bulk-delete'),
        }
        return render(request, 'admins/partials/confirm_bulk_delete.html', context)

    def post(self, request, *args, **kwargs):
        ids_raw = request.POST.get('ids', '')
        ids_list = [int(i.strip()) for i in ids_raw.split(',') if i.strip().isdigit()]
        if ids_list:
            qs = BrokerMaster.objects.filter(id__in=ids_list, is_deleted=False)
            count = qs.count()
            qs.update(is_deleted=True, is_active=False)
            msg = f"Successfully deleted {count} master broker{'s' if count != 1 else ''}."
        else:
            msg = "No valid master brokers selected."
            count = 0

        response = HttpResponse()
        response['HX-Trigger'] = json.dumps({
            'closeGlobalModal': True,
            'showToast': {'message': msg, 'level': 'success' if count > 0 else 'warning'},
            'reloadBrokerMasterTable': True
        })
        return response