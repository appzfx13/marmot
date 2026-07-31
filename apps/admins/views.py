from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib.auth.views import LoginView
from django.contrib.auth.mixins import LoginRequiredMixin
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
from django.db.models import Q

from apps.users.models import User, MemberRoleChoices, BrokerChoices, PLStatusChoices
from apps.users.mixins import HTMXPartialMixin
from .permissions import AdminRequiredMixin
from .forms import UserForm


# ==========================================
# AUTH & DASHBOARD VIEWS
# ==========================================

class AdminLoginView(HTMXPartialMixin, LoginView):
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
        login_url = str(reverse_lazy('admins:admin-login'))

        if request.headers.get('HX-Request'):
            response = HttpResponse(status=204)
            response['HX-Redirect'] = login_url
            return response

        return redirect(login_url)


# ==========================================
# TRADER MANAGEMENT VIEWS
# ==========================================

class AdminMarmotTraderListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    model = User
    template_name = 'marmot/trader_list.html'
    context_object_name = 'traders'
    paginate_by = 10

    def get_queryset(self):
        queryset = super().get_queryset().filter(role=MemberRoleChoices.TRADERS)

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

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['BrokerChoices'] = BrokerChoices
        context['MemberRoleChoices'] = MemberRoleChoices
        context['PLStatusChoices'] = PLStatusChoices

        query_params = self.request.GET.copy()
        query_params.pop('page', None)
        context['current_filters'] = query_params.urlencode()

        return context


class AdminMarmotTraderCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    model = User
    form_class = UserForm
    template_name = 'marmot/trader_form.html'
    success_url = reverse_lazy('admins:marmot_trader_list')

    def form_valid(self, form):
        form.instance.role = MemberRoleChoices.TRADERS
        return super().form_valid(form)


class AdminMarmotTraderUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    model = User
    form_class = UserForm
    template_name = 'marmot/trader_form.html'
    success_url = reverse_lazy('admins:marmot_trader_list')

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
        context['exec_config'] = getattr(self.object, 'exec_config', None)
        return context


class AdminMarmotTraderDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    model = User
    template_name = 'marmot/trader_confirm_delete.html'
    success_url = reverse_lazy('admins:marmot_trader_list')

    def get_queryset(self):
        return super().get_queryset().filter(role=MemberRoleChoices.TRADERS)