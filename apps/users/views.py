from django.contrib.auth import login as auth_login
from django.contrib.auth.views import LoginView
from django.http import HttpResponse
from django.urls import reverse_lazy
from django.views.generic import TemplateView

from .mixins import MarmotRoleRequiredMixin
from .models import User, TeamMember, MemberRoleChoices


class HTMXPartialMixin:
    """
    Renders a partial template for HTMX dynamic requests and the full 
    template for direct browser page reloads/visits.
    """
    partial_template_name = None

    def get_template_names(self):
        if self.request.headers.get('HX-Request') and not self.request.headers.get('HX-Boosted'):
            if self.partial_template_name:
                return [self.partial_template_name]
        return [self.template_name]


class MarmotLoginView(HTMXPartialMixin, LoginView):
    template_name = 'marmot/login.html'
    partial_template_name = 'marmot/partials/login_form.html'
    redirect_authenticated_user = True

    def form_valid(self, form):
        # 1. Log the user in so request.user is populated properly
        auth_login(self.request, form.get_user())
        
        # 2. Get success URL now that request.user is authenticated
        success_url = str(self.get_success_url())

        # 3. Trigger HTMX client-side redirect on successful login
        if self.request.headers.get('HX-Request'):
            response = HttpResponse(status=204)
            response['HX-Redirect'] = success_url
            return response

        return super().form_valid(form)

    def form_invalid(self, form):
        response = super().form_invalid(form)
        if self.request.headers.get('HX-Request'):
            # Return HTTP 422 Unprocessable Entity so HTMX triggers swap event for form errors
            response.status_code = 422
        return response

    def get_success_url(self):
        user = self.request.user
        allowed_roles = [MemberRoleChoices.ADMIN, MemberRoleChoices.TRADERS]
        allowed_values = [
            role.value if hasattr(role, 'value') else role for role in allowed_roles
        ]

        if user.is_superuser:
            return reverse_lazy('users:marmot-dashboard')

        if user.role in allowed_values:
            return reverse_lazy('users:marmot-dashboard')

        marmot_user = User.objects.filter(username__iexact=user.username).first()
        if marmot_user and getattr(marmot_user, 'role', None) in allowed_values:
            return reverse_lazy('users:marmot-dashboard')

        if user.groups.filter(name__in=allowed_values).exists():
            return reverse_lazy('users:marmot-dashboard')

        return reverse_lazy('users:marmot-login')


class MarmotDashboardView(HTMXPartialMixin, MarmotRoleRequiredMixin, TemplateView):
    template_name = 'marmot/dashboard.html'
    partial_template_name = 'marmot/partials/dashboard_content.html'
    allowed_roles = [
        MemberRoleChoices.ADMIN,
        MemberRoleChoices.TRADERS,
    ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['marmot_profile'] = User.objects.filter(
            username__iexact=self.request.user.username
        ).first()
        return context