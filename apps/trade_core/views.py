import logging
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views import View
from apps.trade_config.models import UserTradingAccount
from .services.dhan_token_service import AdminDhanClient, UserDhanClient

logger = logging.getLogger(__name__)


class DhanAdminConsentLoginView(LoginRequiredMixin, UserPassesTestMixin, View):
    """
    Initiates DhanHQ App Consent login for Admin/Staff.
    Generates consentAppId via POST https://auth.dhan.co/app/generate-consent
    and redirects the browser to the Dhan login page.
    """
    def test_func(self):
        user = self.request.user
        return user.is_authenticated and (user.is_superuser or user.is_staff or getattr(user, 'role', '') in ['admin', 'developer'])

    def get(self, request, *args, **kwargs):
        try:
            result = AdminDhanClient.generate_login_url()
            request.session['dhan_consent_type'] = 'admin'
            return redirect(result['login_url'])
        except Exception as e:
            logger.error("Admin Dhan consent generation failed: %s", e)
            messages.error(request, f"Failed to generate Dhan login link: {e}")
            return redirect('/admins/')


class DhanUserConsentLoginView(LoginRequiredMixin, View):
    """
    Initiates DhanHQ App Consent login for a user's trading account.
    """
    def get(self, request, account_id=None, *args, **kwargs):
        account = None
        if account_id:
            account = UserTradingAccount.objects.filter(id=account_id, user=request.user).first()
        if not account:
            account = UserTradingAccount.objects.filter(user=request.user, is_active=True).first()

        if not account:
            messages.error(request, "No active Dhan trading account found.")
            return redirect('/users/accounts/')

        try:
            client = UserDhanClient(account)
            result = client.generate_login_url()
            request.session['dhan_consent_type'] = 'user'
            request.session['dhan_consent_account_id'] = account.id
            return redirect(result['login_url'])
        except Exception as e:
            logger.error("User Dhan consent generation failed for account #%s: %s", getattr(account, 'id', 'unknown'), e)
            messages.error(request, f"Failed to generate Dhan login link: {e}")
            return redirect('/users/accounts/')


class DhanConsentCallbackView(View):
    """
    DhanHQ Consent Redirect Callback Endpoint.
    Receives ?tokenId=... from DhanHQ browser login redirect.
    Consumes the tokenId to exchange for an accessToken and caches it in Redis (23h TTL).
    """
    def get(self, request, *args, **kwargs):
        token_id = request.GET.get('tokenId') or request.GET.get('token_id')
        if not token_id:
            return JsonResponse({"status": "error", "message": "No tokenId provided in callback."}, status=400)

        consent_type = request.session.get('dhan_consent_type', 'admin')
        account_id = request.session.get('dhan_consent_account_id')

        try:
            if consent_type == 'user' and account_id:
                account = UserTradingAccount.objects.filter(id=account_id).first()
                if not account:
                    raise ValueError(f"Trading account #{account_id} not found.")
                client = UserDhanClient(account)
                access_token = client.consume_token(token_id)
                msg = f"Dhan authentication successful for account {account.account_name} ({account.broker_client_id})! Token is active for 24 hours."
                if request.user.is_authenticated:
                    messages.success(request, msg)
                    return redirect('/users/accounts/')
            else:
                access_token = AdminDhanClient.consume_token(token_id)
                msg = "Admin Dhan authentication successful! Master token is active for 24 hours for market backups."
                if request.user.is_authenticated:
                    messages.success(request, msg)
                    return redirect('/admins/')

            return JsonResponse({
                "status": "success",
                "message": msg,
                "token_len": len(access_token),
                "token_preview": access_token[:12] + "..." if len(access_token) > 12 else access_token
            }, status=200)

        except Exception as e:
            logger.error("Dhan consent callback error: %s", e)
            if request.user.is_authenticated:
                messages.error(request, f"Dhan token activation failed: {e}")
                return redirect('/admins/' if consent_type == 'admin' else '/users/accounts/')
            return JsonResponse({"status": "error", "message": str(e)}, status=500)
