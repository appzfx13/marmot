from rest_framework.permissions import BasePermission
from django.contrib.auth import get_user_model
from .models import MemberRoleChoices

User = get_user_model()
ALLOWED_ROLES = [MemberRoleChoices.ADMIN, MemberRoleChoices.TRADERS]


def is_user_authorized_for_dashboard(user) -> bool:
    """Core authorization check for Marmot dashboard access."""
    if not user or not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    allowed_values = [
        role.value if hasattr(role, 'value') else role for role in ALLOWED_ROLES
    ]

    # Check model role attribute
    if getattr(user, 'role', None) in allowed_values:
        return True

    # Check database user
    marmot_user = User.objects.filter(username__iexact=user.username).first()
    if marmot_user and getattr(marmot_user, 'role', None) in allowed_values:
        return True

    # Check Django groups
    return user.groups.filter(name__in=allowed_values).exists()


class IsDashboardAuthorized(BasePermission):
    """
    DRF Permission class for REST API endpoints.
    """
    message = "You do not have permission to access the dashboard."

    def has_permission(self, request, view):
        return is_user_authorized_for_dashboard(request.user)