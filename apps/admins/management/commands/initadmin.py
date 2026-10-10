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

        # -------------------------------------------------------------
        # 2. Seed Exactly 3 Sample Traders & Prune Excess Dummy Users
        # -------------------------------------------------------------
        self.stdout.write("\n--- Setting up Sample Traders (3 Users) ---")
        allowed_test_usernames = [f"test_traders_{i:02d}" for i in range(1, 4)]

        # Prune existing excess test accounts
        pruned_count = User._base_manager.filter(username__startswith='test_').exclude(username__in=allowed_test_usernames).delete()[0]
        if pruned_count > 0:
            self.stdout.write(self.style.WARNING(f"Pruned {pruned_count} obsolete legacy test users."))

        # Create or update 3 sample traders
        for i, username in enumerate(allowed_test_usernames, start=1):
            user, created = User._base_manager.get_or_create(username=username)
            user.email = f"{username}@{email_domain}"
            user.set_password("TestPassword123!")
            user.phone_number = f"+19000040{i}"
            user.role = MemberRoleChoices.TRADERS
            user.first_name = "Sample Trader"
            user.last_name = f"{i:02d}"
            user.is_email_verified = True
            user.is_mobile_verified = True
            user.is_active = True
            user.trade_eligibility = True
            user.description = f"Sample active trader profile {i:02d}."
            user.save()

            if created:
                self.stdout.write(self.style.SUCCESS(f"Sample Trader '{user.username}' created."))
            else:
                self.stdout.write(self.style.SUCCESS(f"Sample Trader '{user.username}' updated."))

        tunnel_url = fetch_tunnel_url()
        if tunnel_url:
            self.stdout.write(self.style.SUCCESS(f"\nCLOUDFLARE Tunnel URL: {tunnel_url}"))
        else:
            self.stdout.write(self.style.WARNING("\nCLOUDFLARE Tunnel URL: Not available or cloudflare tunnel offline."))