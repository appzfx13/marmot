import os
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from apps.users.models import TeamMember, MemberRoleChoices

class Command(BaseCommand):
    help = 'Creates an admin superuser along with TeamMember profile'

    def handle(self, *args, **options):
        User = get_user_model()
        
        # Read credentials from ENV
        username = os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin')
        email = os.environ.get('DJANGO_SUPERUSER_EMAIL', 'admin@example.com')
        password = os.environ.get('DJANGO_SUPERUSER_PASSWORD')
        phone = os.environ.get('DJANGO_SUPERUSER_PHONE', '+10000000000')

        if not username or not password:
            self.stdout.write(self.style.WARNING("DJANGO_SUPERUSER_USERNAME or DJANGO_SUPERUSER_PASSWORD not set."))
            return

        # 1. Get or Create the Auth User
        user, created = User.objects.get_or_create(username=username)
        
        if created:
            user.email = email
            user.set_password(password)
            user.is_superuser = True
            user.is_staff = True
            
            # Populate your custom fields directly on the user instance
            user.name = username.capitalize()
            user.phone_number = phone
            user.role = getattr(MemberRoleChoices, 'ADMIN', 'ADMIN')
            user.is_email_verified = True
            user.is_mobile_verified = True
            user.save()
            self.stdout.write(self.style.SUCCESS(f"Superuser '{username}' created."))
        else:
            self.stdout.write(self.style.SUCCESS(f"User '{username}' already exists."))

        # 2. Create or Update TeamMember (This is the only separate profile model you have)
        admin_tm_role = getattr(MemberRoleChoices, 'ADMIN', 'ADMIN')
        team_member, tm_created = TeamMember.objects.get_or_create(
            user=user,
            defaults={'role': admin_tm_role, 'is_active_developer': True}
        )

        if tm_created:
            self.stdout.write(self.style.SUCCESS(f"TeamMember profile for '{username}' created."))
        else:
            self.stdout.write(self.style.SUCCESS(f"TeamMember profile for '{username}' already exists."))