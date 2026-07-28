from django.contrib.auth.mixins import UserPassesTestMixin
from users.models import MemberRoleChoices


class AdminRequiredMixin(UserPassesTestMixin):
    """
    Mixin to restrict view access exclusively to authenticated Admin users,
    staff members, or superusers.
    """
    def test_func(self):
        user = self.request.user
        if not user.is_authenticated:
            return False
            
        # Safely access role on MarmotUser profile via related_name ('marmot_profile')
        profile = getattr(user, 'marmot_profile', None)
        user_role = getattr(profile, 'role', None) if profile else getattr(user, 'role', None)

        is_admin_role = user_role == getattr(MemberRoleChoices, 'ADMIN', 'ADMIN')
        return user.is_superuser or user.is_staff or is_admin_role