
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
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    TemplateView,
    UpdateView,
)
from django.conf import settings
from django_filters.views import FilterView

from apps.users.models import User, MemberRoleChoices, BrokerChoices, PLStatusChoices
from apps.users.mixins import HTMXPartialMixin
from apps.trade_config.models import TradeExecConfig
from apps.common.mixins import HtmxMessageMixin, HtmxModalMixin
from apps.admins.constants import Messages
from apps.admins.filters import TradeExecConfigFilter
from .permissions import AdminRequiredMixin
from .forms import TradeExecConfigForm, UserForm


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
        return reverse_lazy('admins:admin-dashboard')


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

class AdminMarmotTraderListView(HTMXPartialMixin, LoginRequiredMixin, AdminRequiredMixin, ListView):
    model = User
    template_name = 'marmot/trader_list.html'
    partial_template_name = 'marmot/partials/trader_table.html'
    context_object_name = 'traders'
    paginate_by = settings.PAGINATION_COUNT

    def get_queryset(self):
        queryset = super().get_queryset().filter(role=MemberRoleChoices.MEMBER, is_deleted=False)

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


class AdminMarmotTraderCreateView(HtmxMessageMixin, LoginRequiredMixin, AdminRequiredMixin, CreateView):
    model = User
    form_class = UserForm
    template_name = 'marmot/trader_form.html'
    success_url = reverse_lazy('admins:marmot_trader_list')
    success_message = Messages.TRADER_CREATED

    def form_valid(self, form):
        form.instance.role = MemberRoleChoices.TRADERS
        return super().form_valid(form)


class AdminMarmotTraderUpdateView(HtmxMessageMixin, LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    model = User
    form_class = UserForm
    template_name = 'marmot/trader_form.html'
    success_url = reverse_lazy('admins:marmot_trader_list')
    success_message = Messages.TRADER_UPDATED

    def get_queryset(self):
        return super().get_queryset().filter(role=MemberRoleChoices.TRADERS)


class AdminMarmotTraderDetailView(LoginRequiredMixin, AdminRequiredMixin, DetailView):
    model = User
    template_name = 'marmot/trader_detail.html'
    context_object_name = 'trader'

    def get_queryset(self):
        return super().get_queryset().filter(role=MemberRoleChoices.TRADERS)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['exec_config'] = TradeExecConfig.objects.filter(
            admins_user=self.object
        ).first()
        return context



class AdminMarmotTraderDeleteView(HtmxModalMixin, HtmxMessageMixin, LoginRequiredMixin, AdminRequiredMixin, DeleteView):
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