# MARMOT 
from django.contrib.auth.views import LoginView
from django.urls import reverse_lazy
from django.views.generic import TemplateView

from .mixins import MarmotRoleRequiredMixin
from .models import User, TeamMember, MemberRoleChoices

class MarmotLoginView(LoginView):
    template_name = 'marmot/login.html'
    redirect_authenticated_user = True

    def get_success_url(self):
        user = self.request.user
        allowed_roles = [
            MemberRoleChoices.ADMIN,
            MemberRoleChoices.TRADERS,
        ]
        allowed_values = [
            role.value if hasattr(role, 'value') else role
            for role in allowed_roles
        ]

        # 1. Superusers pass automatically
        if user.is_superuser:
            return reverse_lazy('users:marmot-dashboard')

        # 2. Check TeamMember model
        if hasattr(user, 'team_member') and user.team_member:
            if user.team_member.role in allowed_values:
                return reverse_lazy('users:marmot-dashboard')

        # 3. Check User model (matching by username or full name)
        marmot_user = User.objects.filter(
            name__iexact=user.username
        ).first()
        if marmot_user and marmot_user.role in allowed_values:
            return reverse_lazy('users:marmot-dashboard')

        # 4. Check Django Groups fallback
        if user.groups.filter(name__in=allowed_values).exists():
            return reverse_lazy('users:marmot-dashboard')

        # Fallback redirect if unauthorized role
        return reverse_lazy('users:marmot-login')



class MarmotDashboardView(MarmotRoleRequiredMixin, TemplateView):
    template_name = 'marmot/dashboard.html'
    allowed_roles = [
        MemberRoleChoices.ADMIN,
        MemberRoleChoices.TRADERS,
    ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Retrieve current user's User risk/trading metrics
        context['marmot_profile'] = User.objects.filter(
            name__iexact=self.request.user.username
        ).first()

        return context


