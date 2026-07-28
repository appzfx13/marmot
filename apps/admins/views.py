from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.urls import reverse_lazy
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    UpdateView,
)
from django.db.models import Q
from .permissions import AdminRequiredMixin

from apps.users.models import User, MemberRoleChoices, BrokerChoices, PLStatusChoices
from .forms import UserForm


class AdminMarmotTraderListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    model = User
    template_name = 'marmot/trader_list.html'
    context_object_name = 'traders'
    ordering = ['-created_at']
    paginate_by = 10  # Adjust as needed

    def get_queryset(self):
        queryset = super().get_queryset().filter(role=MemberRoleChoices.TRADERS)

        # 1. Search Query (Name, Username, Email)
        q = self.request.GET.get('q', '').strip()
        if q:
            queryset = queryset.filter(
                Q(name__icontains=q) |
                Q(username__icontains=q) |
                Q(email__icontains=q)
            )

        # 2. Broker Filter
        broker = self.request.GET.get('broker', '').strip()
        if broker:
            queryset = queryset.filter(broker=broker)

        # 3. Phone Number Filter
        phone_number = self.request.GET.get('phone_number', '').strip()
        if phone_number:
            queryset = queryset.filter(phone_number__icontains=phone_number)

        # 4. Trade Eligibility Filter
        trade_eligibility = self.request.GET.get('trade_eligibility', '').strip()
        if trade_eligibility in ['true', 'false']:
            queryset = queryset.filter(trade_eligibility=(trade_eligibility == 'true'))

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Context choices for filter dropdowns
        context['BrokerChoices'] = BrokerChoices
        context['MemberRoleChoices'] = MemberRoleChoices
        context['PLStatusChoices'] = PLStatusChoices

        # Preserve search filters across pagination links
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
        # Automatically assign the TRADERS role on creation
        form.instance.role = MemberRoleChoices.TRADERS
        return super().form_valid(form)


class AdminMarmotTraderUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    model = User
    form_class = UserForm
    template_name = 'marmot/trader_form.html'
    success_url = reverse_lazy('admins:marmot_trader_list')

    def get_queryset(self):
        # Restrict updates strictly to TRADERS
        return (
            super()
            .get_queryset()
            .filter(role=MemberRoleChoices.TRADERS)
        )


class AdminMarmotTraderDetailView(LoginRequiredMixin, AdminRequiredMixin, DetailView):
    model = User
    template_name = 'marmot/trader_detail.html'
    context_object_name = 'trader'

    def get_queryset(self):
        # Restrict detail view strictly to TRADERS
        return (
            super()
            .get_queryset()
            .filter(role=MemberRoleChoices.TRADERS)
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Fetch execution configuration if it exists
        context['exec_config'] = getattr(self.object, 'exec_config', None)
        return context


class AdminMarmotTraderDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    model = User
    template_name = 'marmot/trader_confirm_delete.html'
    success_url = reverse_lazy('admins:marmot_trader_list')

    def get_queryset(self):
        # Restrict deletion strictly to TRADERS
        return (
            super()
            .get_queryset()
            .filter(role=MemberRoleChoices.TRADERS)
        )