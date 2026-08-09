from django.contrib.auth.mixins import UserPassesTestMixin
from django.conf import settings
from apps.common.choices import MemberRoleChoices


class AdminRequiredMixin(UserPassesTestMixin):
    """
    Mixin to restrict view access exclusively to authenticated Admin users,
    staff members, or superusers.
    """
    def test_func(self):
        user = self.request.user
        if not user.is_authenticated:
            return False
            
        user_role = getattr(user, 'role', None)
        is_admin_role = user_role == getattr(MemberRoleChoices, 'ADMIN', 'admin')
        return user.is_superuser or user.is_staff or is_admin_role


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