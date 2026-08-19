from allauth.socialaccount.signals import pre_social_login, social_account_added
from django.dispatch import receiver
from apps.common.choices import MemberRoleChoices
from apps.users.models import User


@receiver(pre_social_login)
def link_existing_user_on_social_login(sender, request, sociallogin, **kwargs):
    """
    If a user already exists with the social email, connect their account automatically.
    """
    if sociallogin.is_existing:
        return

    email = sociallogin.account.extra_data.get('email')
    if not email:
        return

    existing_user = User.objects.filter(email__iexact=email).first()
    if existing_user:
        existing_user.is_email_verified = True
        existing_user.is_active = True
        existing_user.save(update_fields=['is_email_verified', 'is_active', 'updated_at'])
        sociallogin.connect(request, existing_user)


@receiver(social_account_added)
def setup_new_social_user(sender, request, sociallogin, **kwargs):
    """
    Ensure newly created SSO users have verified email, active status,
    TRADERS role, and a default sandbox trading account initialized.
    """
    user = sociallogin.user
    if user and user.pk:
        updated_fields = []
        if not user.is_email_verified:
            user.is_email_verified = True
            updated_fields.append('is_email_verified')
        if not user.is_active:
            user.is_active = True
            updated_fields.append('is_active')
        if not user.role:
            user.role = MemberRoleChoices.TRADERS
            updated_fields.append('role')
        if updated_fields:
            user.save(update_fields=updated_fields)
        # Ensure default sandbox trading account exists
        user.get_active_trading_account()
