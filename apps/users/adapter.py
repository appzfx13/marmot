import logging
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.urls import reverse_lazy

logger = logging.getLogger(__name__)


class MarmotSocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Custom social account adapter to log authentication errors with full context.
    """

    def on_authentication_error(self, request, provider, error=None, exception=None, extra_context=None):
        error_msg = f"[SSO Error] Provider: {getattr(provider, 'id', provider)} | Error: {error} | Exception: {exception}"
        print(f"\n======================================================\n{error_msg}\n======================================================\n", flush=True)
        logger.error(error_msg, exc_info=exception)
        if exception:
            messages.error(request, f"Social login failed: {str(exception)}")
        else:
            messages.error(request, f"Social login failed: {error}")
        return super().on_authentication_error(request, provider, error=error, exception=exception, extra_context=extra_context)
