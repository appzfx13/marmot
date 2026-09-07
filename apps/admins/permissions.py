from django.contrib.auth.mixins import UserPassesTestMixin
from django.conf import settings
from apps.common.choices import MemberRoleChoices


class AdminRequiredMixin(UserPassesTestMixin):
    """
    Mixin to restrict view access to authenticated Admin, Developer, Staff, or Superuser accounts.
    """
    def test_func(self):
        user = self.request.user
        if not user.is_authenticated:
            return False

        user_role = getattr(user, 'role', None)
        allowed_admin_roles = ['admin', 'developer', 'staff']
        return user.is_superuser or user.is_staff or user_role in allowed_admin_roles

    def handle_no_permission(self):
        from django.urls import reverse
        from django.http import HttpResponse
        from django.shortcuts import redirect

        login_url = reverse('admins:admin-login')
        if self.request.headers.get('HX-Request'):
            response = HttpResponse(status=200)
            response['HX-Redirect'] = login_url
            return response
        return redirect(login_url)


class DeveloperOrAdminRequiredMixin(UserPassesTestMixin):
    """
    Mixin to restrict postback log view access exclusively to Admin or Developer roles
    configured in settings.POSTBACK_VIEW_ROLES.
    """
    def test_func(self):
        user = self.request.user
        if not user.is_authenticated:
            return False
            
        if user.is_superuser:
            return True

        user_role = getattr(user, 'role', None)
        allowed_roles = getattr(settings, 'POSTBACK_VIEW_ROLES', ['admin', 'developer'])
        return user_role in allowed_roles