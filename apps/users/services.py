from typing import Optional
from django.contrib.auth import get_user_model

User = get_user_model()

def get_user_profile(username: str) -> Optional[User]:
    """Safely fetch user profile data."""
    return User.objects.filter(username__iexact=username).first()