import secrets
import time
from typing import Optional, Tuple, Dict, Any
from django.contrib.auth import get_user_model
from apps.common.logger import Logger
from apps.notifications.services import send_otp_email, send_welcome_email

User = get_user_model()


def get_user_profile(username: str) -> Optional[User]:
    """Safely fetch user profile data."""
    return User.objects.filter(username__iexact=username).first()


def generate_and_send_email_otp(
    user_or_email: Any,
    request: Any,
    purpose: str = "signup_activation"
) -> Tuple[bool, str]:
    """Generates a secure 6-digit OTP, saves in session, and sends via email."""
    logger = Logger(section="USERS", app="users", log_type="auth_audit", process="otp_dispatch")
    
    user = None
    if isinstance(user_or_email, str):
        email = user_or_email.strip().lower()
        user = User.objects.filter(email__iexact=email).first()
    else:
        user = user_or_email
        email = user.email.strip().lower()

    if not email:
        return False, "No valid email address found."

    otp = str(secrets.randbelow(900000) + 100000)
    now_ts = int(time.time())

    # Store OTP session payload
    request.session['auth_otp_code'] = otp
    request.session['auth_otp_email'] = email
    request.session['auth_otp_user_id'] = user.id if user else None
    request.session['auth_otp_created_at'] = now_ts
    request.session['auth_otp_purpose'] = purpose
    request.session['auth_otp_expiry_minutes'] = 10
    request.session.modified = True

    client_ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', 'Unknown'))
    user_agent = request.META.get('HTTP_USER_AGENT', 'Web Browser')[:40]

    request_details = {
        'Purpose': 'Account Activation' if purpose == 'signup_activation' else 'Email Sign-In (SSO)',
        'IP Address': client_ip.split(',')[0].strip() if ',' in client_ip else client_ip,
        'Device': user_agent
    }

    try:
        sent = send_otp_email(
            to_email=email,
            otp=otp,
            expiry_minutes=10,
            request_details=request_details,
            fail_silently=False
        )
        if sent:
            logger.info(f"OTP successfully dispatched to {email} for {purpose}")
            return True, f"A 6-digit verification code has been sent to {email}."
        else:
            logger.warning(f"Failed to dispatch OTP to {email}")
            return False, "Could not send verification email. Please try again."
    except Exception as exc:
        logger.exception(f"Error sending OTP to {email}: {str(exc)}")
        return False, "Error dispatching verification email. Please try again later."


def verify_email_otp(entered_otp: str, request: Any) -> Tuple[bool, Optional[User], str]:
    """Validates the entered OTP code against session and activates the user account."""
    logger = Logger(section="USERS", app="users", log_type="auth_audit", process="otp_verification")
    
    saved_otp = request.session.get('auth_otp_code')
    saved_email = request.session.get('auth_otp_email')
    saved_user_id = request.session.get('auth_otp_user_id')
    created_at = request.session.get('auth_otp_created_at', 0)
    purpose = request.session.get('auth_otp_purpose', 'signup_activation')
    expiry_minutes = request.session.get('auth_otp_expiry_minutes', 10)

    if not saved_otp or not saved_email:
        return False, None, "No pending verification session found. Please request a new code."

    now_ts = int(time.time())
    if (now_ts - created_at) > (expiry_minutes * 60):
        return False, None, "This verification code has expired. Please request a new one."

    entered_clean = "".join(filter(str.isdigit, str(entered_otp))).strip()
    if entered_clean != str(saved_otp).strip():
        logger.warning(f"Invalid OTP attempt for {saved_email}")
        return False, None, "Invalid verification code. Please check and try again."

    # OTP is valid! Resolve user
    user = None
    if saved_user_id:
        user = User.objects.filter(id=saved_user_id).first()
    if not user and saved_email:
        user = User.objects.filter(email__iexact=saved_email).first()

    if user:
        was_unverified = not user.is_email_verified or not user.is_active
        user.is_email_verified = True
        user.is_active = True
        user.save(update_fields=['is_email_verified', 'is_active', 'updated_at'])
        user.backend = 'django.contrib.auth.backends.ModelBackend'

        if was_unverified and purpose == 'signup_activation':
            try:
                login_url = request.build_absolute_uri('/users/login/')
                send_welcome_email(user=user, login_url=login_url, fail_silently=True)
            except Exception:
                pass

        logger.info(f"User {user.username} ({user.email}) verified and activated successfully via OTP.")

    # Clear OTP session
    for key in ['auth_otp_code', 'auth_otp_email', 'auth_otp_user_id', 'auth_otp_created_at', 'auth_otp_purpose']:
        request.session.pop(key, None)
    request.session.modified = True

    return True, user, "Email verified successfully!"