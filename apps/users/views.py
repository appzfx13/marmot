from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib.auth.views import LoginView
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import TemplateView

from .mixins import HTMXPartialMixin, MarmotRoleRequiredMixin
from .permissions import is_user_authorized_for_dashboard
from .services import get_user_profile


class LoginView(HTMXPartialMixin, LoginView):
    template_name = 'admins/login.html'
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
            return reverse_lazy('users:marmot-dashboard')
        return reverse_lazy('users:marmot-login')


class UserDashboardView(HTMXPartialMixin, MarmotRoleRequiredMixin, TemplateView):
    """
    Protected Marmot Dashboard View. Uses MarmotRoleRequiredMixin to 
    ensure only authorized roles can access.
    """
    template_name = 'admins/dashboard.html'
    partial_template_name = 'admins/partials/dashboard_content.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['marmot_profile'] = get_user_profile(self.request.user.username)
        return context


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

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import UpdateView
from apps.common.mixins import HtmxMessageMixin
from .models import User
from .forms import UserProfileForm

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