from django.contrib.auth.mixins import UserPassesTestMixin
from django.shortcuts import redirect
from .permissions import is_user_authorized_for_dashboard


class HTMXPartialMixin:
    """
    Renders partial template for HTMX dynamic requests and the full 
    template for direct browser page reloads/visits.
    """
    partial_template_name = None

    def get_template_names(self):
        if self.request.headers.get('HX-Request') and not self.request.headers.get('HX-Boosted'):
            if self.partial_template_name:
                return [self.partial_template_name]
        return [self.template_name]


class MarmotRoleRequiredMixin(UserPassesTestMixin):
    """
    Django View Mixin to restrict access based on dashboard roles.
    """
    def test_func(self):
        return is_user_authorized_for_dashboard(self.request.user)

    def handle_no_permission(self):
        return redirect('users:marmot-login')


