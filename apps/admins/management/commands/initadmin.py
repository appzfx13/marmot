import os
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from apps.common.choices import MemberRoleChoices
from apps.common.utils import fetch_tunnel_url


class Command(BaseCommand):
    help = "Creates or updates foundational superusers (Admin & Developer) from environment variables."

    def handle(self, *args, **options):
        User = get_user_model()

        # Read base password from ENV (fallback for dev)
        base_password = os.environ.get('DJANGO_SUPERUSER_PASSWORD', 'Admin@12345')
        email_domain = os.environ.get('DJANGO_EMAIL_DOMAIN', 'example.com')

        # -------------------------------------------------------------
        # 1. Create Super Admins (Admin & Developer)
        # -------------------------------------------------------------
        super_users_data = [
            {
                'username': os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin'),
                'email': os.environ.get('DJANGO_SUPERUSER_EMAIL', f'admin@{email_domain}'),
                'phone_number': os.environ.get('DJANGO_SUPERUSER_PHONE', '+10000000001'),
                'role': MemberRoleChoices.ADMIN,
                'first_name': 'Super',
                'last_name': 'Admin',
            },
            {
                'username': os.environ.get('DJANGO_DEV_USERNAME', 'developer'),
                'email': os.environ.get('DJANGO_DEV_EMAIL', f'developer@{email_domain}'),
                'phone_number': os.environ.get('DJANGO_DEV_PHONE', '+10000000002'),
                'role': MemberRoleChoices.DEVELOPER,
                'first_name': 'Super',
                'last_name': 'Developer',
            },
        ]

        self.stdout.write("--- Setting up Superusers ---")
        for su_data in super_users_data:
            # FIX: Use _base_manager to check the raw database, ignoring soft-delete filters
            user, created = User._base_manager.get_or_create(username=su_data['username'])

            user.email = su_data['email']
            user.set_password(base_password)
            user.is_superuser = True
            user.is_staff = True
            user.is_active = True
            user.phone_number = su_data['phone_number']
            user.role = su_data['role']
            user.first_name = su_data['first_name']
            user.last_name = su_data['last_name']
            user.is_email_verified = True
            user.is_mobile_verified = True
            user.save()

            if created:
                self.stdout.write(self.style.SUCCESS(f"Superuser '{user.username}' ({user.role}) created."))
            else:
                self.stdout.write(self.style.SUCCESS(f"Superuser '{user.username}' ({user.role}) updated with ENV credentials."))

        self.stdout.write(self.style.SUCCESS("\nAdmin & Developer user initialization completed successfully!"))

        tunnel_url = fetch_tunnel_url()
        if tunnel_url:
            self.stdout.write(self.style.SUCCESS(f"CLOUDFLARE Tunnel URL: {tunnel_url}"))
        else:
            self.stdout.write(self.style.WARNING("CLOUDFLARE Tunnel URL: Not available or cloudflare tunnel offline."))