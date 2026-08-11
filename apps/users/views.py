import json
from django.contrib.auth import login as auth_login, logout as auth_logout, update_session_auth_hash
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import FormView, TemplateView, UpdateView

from apps.common.mixins import HtmxMessageMixin, HtmxModalMixin
from .forms import UserProfileForm, UserProfilePasswordChangeForm
from .mixins import HTMXPartialMixin, MarmotRoleRequiredMixin
from .models import User
from .permissions import is_user_authorized_for_dashboard
from .services import get_user_profile


class LoginView(HTMXPartialMixin, LoginView):
    template_name = 'registration/login.html'
    partial_template_name = 'admins/partials/login_form.html'
    redirect_authenticated_user = True

    def form_valid(self, form):
        try:
            auth_login(self.request, form.get_user())
            success_url = str(self.get_success_url())

            # HTMX response: return 204 with HX-Redirect header
            if self.request.headers.get('HX-Request'):
                response = HttpResponse(status=204)
                response['HX-Redirect'] = success_url
                return response

            return redirect(success_url)

        except Exception as e:
            form.add_error(None, f"An unexpected error occurred: {str(e)}")
            return self.form_invalid(form)

    def form_invalid(self, form):
        # Handle HTMX request: render ONLY the partial form with status code 422
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


class UserDashboardView(HTMXPartialMixin, MarmotRoleRequiredMixin, TemplateView):
    """Protected Marmot Dashboard View serving dashboard_content.html partial for HTMX."""
    template_name = 'users/dashboard.html'
    partial_template_name = 'users/partials/dashboard_content.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_tab'] = 'dashboard'
        context['marmot_profile'] = get_user_profile(self.request.user.username)
        context['total_traders'] = User.objects.filter(is_superuser=False).count()
        context['active_traders'] = User.objects.filter(is_superuser=False, trade_eligibility=True, is_blocked=False).count()
        return context


class UserJournalView(HTMXPartialMixin, MarmotRoleRequiredMixin, TemplateView):
    """View for user execution journal."""
    template_name = 'users/dashboard.html'
    partial_template_name = 'users/partials/journal_content.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_tab'] = 'journal'
        return context


class UserBacktestView(HTMXPartialMixin, MarmotRoleRequiredMixin, TemplateView):
    """View for user strategy backtesting."""
    template_name = 'users/dashboard.html'
    partial_template_name = 'users/partials/backtest_content.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_tab'] = 'backtest'
        return context


class UserSandboxSettingsView(HTMXPartialMixin, MarmotRoleRequiredMixin, TemplateView):
    """View for user sandbox & risk settings."""
    template_name = 'users/dashboard.html'
    partial_template_name = 'users/partials/sandbox_settings_content.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_tab'] = 'sandbox'
        return context


class UserKillSwitchView(HtmxModalMixin, LoginRequiredMixin, View):
    """View for user emergency kill switch trigger."""
    modal_template_name = 'users/partials/kill_switch_modal.html'
    template_name = 'users/partials/kill_switch_modal.html'

    def get(self, request, *args, **kwargs):
        return render(request, self.modal_template_name)

    def post(self, request, *args, **kwargs):
        user = request.user
        user.primary_freeze = True
        user.final_freeze = True
        user.save()

        response = HttpResponse()
        msg = f"EMERGENCY KILL SWITCH ACTIVATED for @{user.username}! All trade executions frozen."
        response['HX-Trigger'] = json.dumps({
            'closeGlobalModal': True,
            'showToast': {'message': msg, 'level': 'warning'}
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

        context['profile_user'] = user_obj
        context['page_title'] = "User Profile" if not is_edit else "Edit User Profile"
        context['is_edit'] = is_edit
        context['is_admin_or_dev'] = (
            self.request.user.is_superuser or 
            getattr(self.request.user, 'role', '') in ['admin', 'developer']
        )
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