import os
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from apps.common.choices import MemberRoleChoices
from apps.common.utils import fetch_ngrok_url


class Command(BaseCommand):
    help = "Creates superusers (Admin & Developer) and sample dummy users for all roles."

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

        # -------------------------------------------------------------
        # 2. Create Dummy Users for Each Role
        # -------------------------------------------------------------
        self.stdout.write("\n--- Creating Dummy Users per Role ---")

        for role_choice in MemberRoleChoices.choices:
            role_key = role_choice[0]  # e.g., 'admin', 'staff', 'developer', etc.
            role_label = role_choice[1]

            created_count = 0
            for i in range(1, 100):
                username = f"test_{role_key}_{i:02d}"  # e.g., test_traders_01
                phone = f"+190000{list(MemberRoleChoices.values).index(role_key)}{i:02d}"

                # FIX: Use _base_manager here as well to cleanly skip existing/soft-deleted users
                user, created = User._base_manager.get_or_create(username=username)
                
                if created:
                    user.email = f"{username}@{email_domain}"
                    user.set_password("TestPassword123!")
                    user.phone_number = phone
                    user.role = role_key
                    user.first_name = f"Sample{role_label}"
                    user.last_name = f"User{i}"
                    user.is_email_verified = True
                    user.is_mobile_verified = True
                    user.description = f"Dummy user for {role_label} testing."
                    user.save()
                    created_count += 1

            self.stdout.write(
                self.style.SUCCESS(f"Processed {role_label}: {created_count} new users created.")
            )

        self.stdout.write(self.style.SUCCESS("\nUser initialization completed successfully!"))

        ngrok_url = fetch_ngrok_url()
        if ngrok_url:
            self.stdout.write(self.style.SUCCESS(f"NGROK Tunnel URL: {ngrok_url}"))
        else:
            self.stdout.write(self.style.WARNING("NGROK Tunnel URL: Not available or ngrok service offline."))