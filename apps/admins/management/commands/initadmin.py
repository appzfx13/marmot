import os
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from apps.users.models import User, TeamMember, MemberRoleChoices, MemberRoleChoices


class Command(BaseCommand):
    help = 'Creates an admin superuser along with User and TeamMember admin profiles if they do not exist'

    def handle(self, *args, **options):
        User = get_user_model()
        
        # Read credentials from ENV
        base_name = os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin')
        email = os.environ.get('DJANGO_SUPERUSER_EMAIL', 'admin@example.com')
        password = os.environ.get('DJANGO_SUPERUSER_PASSWORD')
        phone_number = os.environ.get('DJANGO_SUPERUSER_PHONE', '+10000000000')

        if not base_name or not password:
            self.stdout.write(self.style.WARNING(
                "DJANGO_SUPERUSER_USERNAME or DJANGO_SUPERUSER_PASSWORD not set. Skipping."
            ))
            return

        # 1. Ensure Auth Superuser exists
        user, created = User.objects.get_or_create(
            username=base_name,
            defaults={'email': email}
        )
        if created:
            user.set_password(password)
            user.is_superuser = True
            user.is_staff = True
            user.save()
            self.stdout.write(self.style.SUCCESS(
                f"Superuser '{base_name}' created successfully."
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"Superuser '{base_name}' already exists."
            ))

        # 2. Create or Update User entry with ADMIN role
        admin_role = getattr(MemberRoleChoices, 'ADMIN', 'ADMIN')
        
        # Lookup by user link or email
        marmot_user = User.objects.filter(user=user).first() or User.objects.filter(email=email).first()

        if not marmot_user:
            # Instantiating User with user link attached
            marmot_user = User(
                user=user,
                name=base_name.capitalize(),
                email=email,
                phone_number=phone_number,
                role=admin_role,
                is_email_verified=True,
                is_mobile_verified=True,
                description='System Administrator for Marmot Risk Controller',
                trade_eligibility=True,
                is_blocked=False,
            )
            marmot_user.save()  # Triggers prefix-based username generation
            self.stdout.write(self.style.SUCCESS(
                f"User created with ADMIN role and username '{marmot_user.username}'."
            ))
        else:
            updated = False
            if marmot_user.user != user:
                marmot_user.user = user
                updated = True
            if marmot_user.role != admin_role:
                marmot_user.role = admin_role
                updated = True
            if not marmot_user.is_email_verified or not marmot_user.is_mobile_verified:
                marmot_user.is_email_verified = True
                marmot_user.is_mobile_verified = True
                updated = True

            if updated:
                marmot_user.save()
                self.stdout.write(self.style.SUCCESS(
                    f"Updated User '{marmot_user.username}' with ADMIN role and verified status."
                ))
            else:
                self.stdout.write(self.style.SUCCESS(
                    f"User '{marmot_user.username}' already exists and is up to date."
                ))

        # 3. Create or Update TeamMember entry with ADMIN role
        admin_tm_role = getattr(MemberRoleChoices, 'ADMIN', 'ADMIN')
        team_member, tm_created = TeamMember.objects.get_or_create(
            user=user,
            defaults={
                'role': admin_tm_role,
                'is_active_developer': True,
            }
        )

        if not tm_created and team_member.role != admin_tm_role:
            team_member.role = admin_tm_role
            team_member.save()
            self.stdout.write(self.style.SUCCESS(
                f"Updated TeamMember '{base_name}' role to ADMIN."
            ))
        elif tm_created:
            self.stdout.write(self.style.SUCCESS(
                f"TeamMember profile for '{base_name}' created with ADMIN role."
            ))