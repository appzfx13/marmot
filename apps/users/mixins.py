from django.contrib.auth.mixins import UserPassesTestMixin
from .models import User, TeamMember, MemberRoleChoices


class MarmotRoleRequiredMixin(UserPassesTestMixin):
    allowed_roles = [
        MemberRoleChoices.ADMIN,
        MemberRoleChoices.TRADERS,
    ]

    def test_func(self):
        user = self.request.user
        if not user.is_authenticated:
            return False

        if user.is_superuser:
            return True

        allowed_values = [
            role.value if hasattr(role, 'value') else role
            for role in self.allowed_roles
        ]

        # 1. Check TeamMember profile linked to auth user
        if hasattr(user, 'team_member') and user.team_member:
            if user.team_member.role in allowed_values:
                return True

        # 2. Check User record matching user's username or email
        marmot_user = User.objects.filter(
            name__iexact=user.username
        ).first()
        if marmot_user and marmot_user.role in allowed_values:
            return True

        # 3. Check Django Groups as fallback
        return user.groups.filter(name__in=allowed_values).exists()