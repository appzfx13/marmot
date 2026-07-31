import os
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from apps.users.models import MemberRoleChoices


class Command(BaseCommand):
    help = 'Creates an admin superuser with admin role and custom attributes'

    def handle(self, *args, **options):
        User = get_user_model()

        # Read credentials from ENV
        username = os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin')
        email = os.environ.get('DJANGO_SUPERUSER_EMAIL', 'admin@example.com')
        password = os.environ.get('DJANGO_SUPERUSER_PASSWORD')
        phone = os.environ.get('DJANGO_SUPERUSER_PHONE', '+10000000000')

        if not username or not password:
            self.stdout.write(
                self.style.WARNING("DJANGO_SUPERUSER_USERNAME or DJANGO_SUPERUSER_PASSWORD not set.")
            )
            return

        # Get or Create the Auth User
        user, created = User.objects.get_or_create(username=username)

        if created:
            user.email = email
            user.set_password(password)
            user.is_superuser = True
            user.is_staff = True

            # Populate custom User fields
            user.name = username.capitalize()
            user.phone_number = phone
            user.role = getattr(MemberRoleChoices, 'ADMIN', 'ADMIN')
            user.is_email_verified = True
            user.is_mobile_verified = True
            user.save()

            self.stdout.write(self.style.SUCCESS(f"Superuser '{username}' created successfully."))
        else:
            self.stdout.write(self.style.SUCCESS(f"User '{username}' already exists."))