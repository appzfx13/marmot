from typing import List, Union, Dict, Any, Optional
from datetime import datetime
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from apps.common.logger import Logger
from apps.common.constants import EmailTemplateConstants, EmailSubjectConstants
from apps.common.cache import get_site_settings


class EmailService:
    """Core SMTP email service supporting rich HTML templates, fallbacks, and structured logging."""

    @classmethod
    def send_email(
        cls,
        to_email: Union[str, List[str]],
        subject: str,
        template_name: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        plain_text_message: Optional[str] = None,
        from_email: Optional[str] = None,
        attachments: Optional[List[tuple]] = None,
        fail_silently: bool = False,
        process_tag: str = "dispatch"
    ) -> bool:
        """Sends an HTML/text email using Django's configured SMTP backend and logs the result."""
        logger = Logger(section="NOTIFICATIONS", app="notifications", log_type="email_audit", process=process_tag)
        recipients = [to_email] if isinstance(to_email, str) else list(to_email)
        recipients = [email.strip() for email in recipients if email and email.strip()]

        if not recipients:
            logger.warning("Email dispatch aborted: No valid recipient addresses provided.")
            return False

        sender = from_email or getattr(settings, 'DEFAULT_FROM_EMAIL', 'Marmot Trading <noreply@marmot.local>')
        ctx = context.copy() if context else {}
        ctx.setdefault('current_year', datetime.now().year)
        ctx.setdefault('site_settings', get_site_settings())
        ctx.setdefault('site_url', getattr(settings, 'SITE_URL', ''))

        html_content = None
        if template_name:
            try:
                html_content = render_to_string(template_name, ctx)
            except Exception as e:
                logger.error(f"Template rendering failed for '{template_name}': {str(e)}")
                if not fail_silently:
                    raise e

        body_text = plain_text_message
        if not body_text and html_content:
            body_text = strip_tags(html_content).strip()
        elif not body_text:
            body_text = subject

        try:
            msg = EmailMultiAlternatives(
                subject=subject,
                body=body_text,
                from_email=sender,
                to=recipients
            )

            if html_content:
                msg.attach_alternative(html_content, "text/html")

            if attachments:
                for attachment in attachments:
                    msg.attach(*attachment)

            sent_count = msg.send(fail_silently=fail_silently)
            success = sent_count > 0

            if success:
                logger.info(f"Email sent successfully to {recipients} | Subject: '{subject}'")
            else:
                logger.warning(f"Email dispatch returned 0 for recipients {recipients} | Subject: '{subject}'")
            return success

        except Exception as exc:
            logger.exception(f"SMTP error dispatching email to {recipients} | Subject: '{subject}' | Error: {str(exc)}")
            if not fail_silently:
                raise exc
            return False

    @classmethod
    def send_otp(
        cls,
        to_email: str,
        otp: Union[str, int],
        expiry_minutes: int = 10,
        request_details: Optional[Dict[str, Any]] = None,
        fail_silently: bool = True
    ) -> bool:
        """Dispatches an OTP verification code email."""
        context = {
            'otp': str(otp),
            'expiry_minutes': expiry_minutes,
            'request_details': request_details or {}
        }
        subject = EmailSubjectConstants.OTP_VERIFICATION.format(otp=otp)
        return cls.send_email(
            to_email=to_email,
            subject=subject,
            template_name=EmailTemplateConstants.OTP,
            context=context,
            fail_silently=fail_silently,
            process_tag="otp"
        )

    @classmethod
    def send_welcome(
        cls,
        user: Any,
        login_url: Optional[str] = None,
        fail_silently: bool = True
    ) -> bool:
        """Dispatches an onboarding welcome email."""
        if not getattr(user, 'email', None):
            return False
        context = {
            'user': user,
            'login_url': login_url
        }
        return cls.send_email(
            to_email=user.email,
            subject=EmailSubjectConstants.WELCOME,
            template_name=EmailTemplateConstants.WELCOME,
            context=context,
            fail_silently=fail_silently,
            process_tag="welcome"
        )

    @classmethod
    def send_password_reset(
        cls,
        user: Any,
        reset_url: str,
        fail_silently: bool = True
    ) -> bool:
        """Dispatches a password reset recovery email."""
        if not getattr(user, 'email', None):
            return False
        context = {
            'user': user,
            'reset_url': reset_url
        }
        return cls.send_email(
            to_email=user.email,
            subject=EmailSubjectConstants.PASSWORD_RESET,
            template_name=EmailTemplateConstants.PASSWORD_RESET,
            context=context,
            fail_silently=fail_silently,
            process_tag="password_reset"
        )

    @classmethod
    def send_activation(
        cls,
        user: Any,
        activation_url: str,
        fail_silently: bool = True
    ) -> bool:
        """Dispatches an account email verification link."""
        if not getattr(user, 'email', None):
            return False
        context = {
            'user': user,
            'activation_url': activation_url
        }
        return cls.send_email(
            to_email=user.email,
            subject=EmailSubjectConstants.ACCOUNT_ACTIVATION,
            template_name=EmailTemplateConstants.ACCOUNT_ACTIVATION,
            context=context,
            fail_silently=fail_silently,
            process_tag="activation"
        )

    @classmethod
    def send_trade_alert(
        cls,
        to_email: Union[str, List[str]],
        symbol: str,
        message: str,
        action_type: str = "EXECUTION",
        strategy: Optional[str] = None,
        price: Optional[Union[float, str]] = None,
        quantity: Optional[Union[int, str]] = None,
        order_id: Optional[str] = None,
        pnl: Optional[str] = None,
        is_profit: Optional[bool] = None,
        action_url: Optional[str] = None,
        fail_silently: bool = True
    ) -> bool:
        """Dispatches an algorithmic order execution or trade alert email."""
        context = {
            'title': f"Trade {action_type.title()}: {symbol}",
            'symbol': symbol,
            'message': message,
            'action_type': action_type.upper(),
            'strategy': strategy,
            'price': price,
            'quantity': quantity,
            'order_id': order_id,
            'pnl': pnl,
            'is_profit': is_profit,
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S IST"),
            'action_url': action_url
        }
        subject = EmailSubjectConstants.TRADE_ALERT.format(action=action_type.upper(), symbol=symbol)
        return cls.send_email(
            to_email=to_email,
            subject=subject,
            template_name=EmailTemplateConstants.TRADE_ALERT,
            context=context,
            fail_silently=fail_silently,
            process_tag="trade_alert"
        )

    @classmethod
    def send_notification(
        cls,
        to_email: Union[str, List[str]],
        title: str,
        message: str,
        badge_text: Optional[str] = None,
        data_items: Optional[Dict[str, Any]] = None,
        action_url: Optional[str] = None,
        action_label: Optional[str] = None,
        closing_note: Optional[str] = None,
        fail_silently: bool = True
    ) -> bool:
        """Dispatches a generic notification email."""
        context = {
            'title': title,
            'message': message,
            'badge_text': badge_text,
            'data_items': data_items or {},
            'action_url': action_url,
            'action_label': action_label,
            'closing_note': closing_note,
        }
        subject = EmailSubjectConstants.NOTIFICATION.format(title=title)
        return cls.send_email(
            to_email=to_email,
            subject=subject,
            template_name=EmailTemplateConstants.NOTIFICATION,
            context=context,
            fail_silently=fail_silently,
            process_tag="notification"
        )

    @classmethod
    def send_kill_switch_alert(
        cls,
        to_email: Union[str, List[str]],
        user: Any,
        reason: Optional[str] = None,
        squared_off_count: Optional[int] = None,
        cancelled_orders_count: Optional[int] = None,
        dashboard_url: Optional[str] = None,
        fail_silently: bool = True
    ) -> bool:
        """Dispatches an urgent emergency kill switch activation alert email."""
        username = getattr(user, 'username', str(user))
        context = {
            'user': user,
            'username': username,
            'reason': reason,
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S IST"),
            'squared_off_count': squared_off_count,
            'cancelled_orders_count': cancelled_orders_count,
            'dashboard_url': dashboard_url,
        }
        return cls.send_email(
            to_email=to_email,
            subject=EmailSubjectConstants.KILL_SWITCH_TRIGGERED,
            template_name=EmailTemplateConstants.KILL_SWITCH,
            context=context,
            fail_silently=fail_silently,
            process_tag="kill_switch"
        )


# Global Trigger Functions
def send_otp_email(to_email: str, otp: Union[str, int], expiry_minutes: int = 10, request_details: Optional[Dict[str, Any]] = None, fail_silently: bool = True) -> bool:
    """Convenience trigger to dispatch an OTP verification code."""
    return EmailService.send_otp(to_email, otp, expiry_minutes, request_details, fail_silently)


def send_welcome_email(user: Any, login_url: Optional[str] = None, fail_silently: bool = True) -> bool:
    """Convenience trigger to dispatch a welcome email."""
    return EmailService.send_welcome(user, login_url, fail_silently)


def send_password_reset_email(user: Any, reset_url: str, fail_silently: bool = True) -> bool:
    """Convenience trigger to dispatch a password recovery email."""
    return EmailService.send_password_reset(user, reset_url, fail_silently)


def send_notification_email(to_email: Union[str, List[str]], title: str, message: str, badge_text: Optional[str] = None, data_items: Optional[Dict[str, Any]] = None, action_url: Optional[str] = None, action_label: Optional[str] = None, closing_note: Optional[str] = None, fail_silently: bool = True) -> bool:
    """Convenience trigger to dispatch a notification email."""
    return EmailService.send_notification(to_email, title, message, badge_text, data_items, action_url, action_label, closing_note, fail_silently)


def send_trade_alert_email(to_email: Union[str, List[str]], symbol: str, message: str, action_type: str = "EXECUTION", strategy: Optional[str] = None, price: Optional[Union[float, str]] = None, quantity: Optional[Union[int, str]] = None, order_id: Optional[str] = None, pnl: Optional[str] = None, is_profit: Optional[bool] = None, action_url: Optional[str] = None, fail_silently: bool = True) -> bool:
    """Convenience trigger to dispatch a trade execution alert."""
    return EmailService.send_trade_alert(to_email, symbol, message, action_type, strategy, price, quantity, order_id, pnl, is_profit, action_url, fail_silently)


def send_kill_switch_alert_email(to_email: Union[str, List[str]], user: Any, reason: Optional[str] = None, squared_off_count: Optional[int] = None, cancelled_orders_count: Optional[int] = None, dashboard_url: Optional[str] = None, fail_silently: bool = True) -> bool:
    """Convenience trigger to dispatch an emergency kill switch alert."""
    return EmailService.send_kill_switch_alert(to_email, user, reason, squared_off_count, cancelled_orders_count, dashboard_url, fail_silently)
