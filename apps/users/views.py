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
    template_name = 'marmot/login.html'
    partial_template_name = 'marmot/partials/login_form.html'
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
    template_name = 'marmot/dashboard.html'
    partial_template_name = 'marmot/partials/dashboard_content.html'

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