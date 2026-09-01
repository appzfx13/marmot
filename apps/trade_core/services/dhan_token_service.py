import logging
import requests
import redis
from django.conf import settings

logger = logging.getLogger(__name__)

DHAN_GENERATE_CONSENT_URL = "https://auth.dhan.co/app/generate-consent"
DHAN_LOGIN_URL = "https://auth.dhan.co/login/consentApp-login"
DHAN_CONSUME_CONSENT_URL = "https://auth.dhan.co/app/consumeApp-consent"
DHAN_GENERATE_TOTP_TOKEN_URL = "https://auth.dhan.co/app/generateAccessToken"
DHAN_RENEW_TOKEN_URL = "https://api.dhan.co/v2/RenewToken"

_TOKEN_TTL_SECONDS = 82800  # 23 hours (Dhan access tokens expire in 24h)
_redis_client = None


def _get_redis():
    """Lazy Redis client — reuses a single connection."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis_client


def generate_access_token_via_totp(client_id: str, pin: str, totp: str) -> dict:
    """
    DhanHQ v2 Endpoint: POST https://auth.dhan.co/app/generateAccessToken?dhanClientId={dhanClientId}&pin={pin}&totp={totp}
    Generates an access token instantly using Dhan Client ID, 6-digit Dhan PIN, and 6-digit TOTP code.
    Caches accessToken in Redis with 23h TTL and returns response dictionary.
    """
    if not client_id or not pin or not totp:
        raise ValueError("client_id, pin, and totp are required to generate Dhan token.")

    url = f"{DHAN_GENERATE_TOTP_TOKEN_URL}?dhanClientId={client_id}&pin={pin}&totp={totp}"
    headers = {"Accept": "application/json"}

    try:
        resp = requests.post(url, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        access_token = data.get("accessToken") or data.get("access_token")
        if not access_token:
            raise ValueError(f"No accessToken returned from generateAccessToken: {data}")

        cache_key = f"dhan_token:{client_id}"
        _get_redis().setex(cache_key, _TOKEN_TTL_SECONDS, access_token)
        logger.info("✅ Dhan PIN+TOTP accessToken generated and cached for client_id=%s", client_id)
        return {
            "accessToken": access_token,
            "expiryTime": data.get("expiryTime", ""),
            "dhanClientName": data.get("dhanClientName", ""),
            "dhanClientUcc": data.get("dhanClientUcc", ""),
            "status": "success",
        }
    except requests.RequestException as e:
        logger.error("Dhan generateAccessToken failed for client_id=%s: %s", client_id, e)
        raise ValueError(f"Dhan TOTP token generation failed: {e}") from e


def renew_access_token(client_id: str, access_token: str) -> str:
    """
    DhanHQ v2 Endpoint: POST https://api.dhan.co/v2/RenewToken
    Headers: access-token: {access_token}, dhanClientId: {client_id}
    Renews an active access token for another 24 hours.
    """
    if not client_id or not access_token:
        raise ValueError("client_id and access_token are required to renew token.")

    url = DHAN_RENEW_TOKEN_URL
    headers = {
        "access-token": access_token,
        "dhanClientId": client_id,
        "Accept": "application/json"
    }

    try:
        resp = requests.post(url, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json() if resp.content else {}
        new_token = (
            (data.get("data") if isinstance(data.get("data"), dict) else {}).get("accessToken")
            or (data.get("data") if isinstance(data.get("data"), dict) else {}).get("access_token")
            or data.get("accessToken")
            or data.get("access_token")
            or access_token
        )

        cache_key = f"dhan_token:{client_id}"
        _get_redis().setex(cache_key, _TOKEN_TTL_SECONDS, new_token)
        logger.info("✅ Dhan accessToken renewed successfully for client_id=%s", client_id)
        return new_token
    except requests.RequestException as e:
        logger.error("Dhan RenewToken failed for client_id=%s: %s", client_id, e)
        raise ValueError(f"Dhan token renewal failed: {e}") from e


def generate_consent_login_url(client_id: str, api_key: str, api_secret: str) -> dict:
    """
    Step 1: POST https://auth.dhan.co/app/generate-consent?client_id={dhanClientId}
    Headers: app_id: {API key}, app_secret: {API secret}
    Returns: {"consentAppId": "...", "login_url": "https://auth.dhan.co/login/consentApp-login?consentAppId=..."}
    """
    if not client_id or not api_key or not api_secret:
        raise ValueError("client_id, api_key (app_id), and api_secret (app_secret) are required for Dhan consent generation.")

    url = f"{DHAN_GENERATE_CONSENT_URL}?client_id={client_id}"
    headers = {
        "app_id": api_key,
        "app_secret": api_secret,
        "Accept": "application/json"
    }

    try:
        resp = requests.post(url, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        consent_app_id = data.get("consentAppId")
        if not consent_app_id:
            raise ValueError(f"Dhan consent generation failed. Response: {data}")

        login_url = f"{DHAN_LOGIN_URL}?consentAppId={consent_app_id}"
        logger.info("Dhan consent generated successfully: consentAppId=%s for client_id=%s", consent_app_id, client_id)
        return {
            "consentAppId": consent_app_id,
            "login_url": login_url,
            "status": data.get("status", "success")
        }
    except requests.RequestException as e:
        logger.error("Dhan generate-consent request error for client_id=%s: %s", client_id, e)
        raise ValueError(f"Dhan generate-consent failed: {e}") from e


def consume_consent_token(token_id: str, client_id: str, api_key: str, api_secret: str) -> str:
    """
    Step 3: POST https://auth.dhan.co/app/consumeApp-consent?tokenId={Token ID}
    Headers: app_id: {API key}, app_secret: {API secret}
    Extracts accessToken, caches in Redis with 23h TTL, and returns the accessToken.
    """
    if not token_id:
        raise ValueError("tokenId is required to consume Dhan consent.")

    url = f"{DHAN_CONSUME_CONSENT_URL}?tokenId={token_id}"
    headers = {
        "app_id": api_key,
        "app_secret": api_secret,
        "Accept": "application/json"
    }

    try:
        resp = requests.post(url, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        access_token = data.get("accessToken") or data.get("access_token")
        if not access_token:
            raise ValueError(f"No accessToken returned from consumeApp-consent: {data}")

        # Cache in Redis for 23 hours
        cache_key = f"dhan_token:{client_id}"
        _get_redis().setex(cache_key, _TOKEN_TTL_SECONDS, access_token)
        logger.info("✅ Dhan accessToken acquired and cached for client_id=%s (len=%d)", client_id, len(access_token))
        return access_token
    except requests.RequestException as e:
        logger.error("Dhan consumeApp-consent failed for client_id=%s: %s", client_id, e)
        raise ValueError(f"Dhan consumeApp-consent failed: {e}") from e


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN Dhan Client
# Credentials source: settings.DHAN_CLIENT_ID / DHAN_API_KEY / DHAN_API_SECRET
# Purpose: Market data backup & ingestion (Admin-only features)
# ─────────────────────────────────────────────────────────────────────────────

class AdminDhanClient:
    """
    Dhan API client for Admin backup/ingestion operations.
    Credentials sourced exclusively from Django settings (master .env).
    """

    @classmethod
    def generate_login_url(cls) -> dict:
        """Generates consent and returns the Dhan browser login URL for admin."""
        return generate_consent_login_url(
            client_id=getattr(settings, 'DHAN_CLIENT_ID', ''),
            api_key=getattr(settings, 'DHAN_API_KEY', ''),
            api_secret=getattr(settings, 'DHAN_API_SECRET', ''),
        )

    @classmethod
    def consume_token(cls, token_id: str) -> str:
        """Consumes tokenId received from Dhan login redirect and caches accessToken."""
        return consume_consent_token(
            token_id=token_id,
            client_id=getattr(settings, 'DHAN_CLIENT_ID', ''),
            api_key=getattr(settings, 'DHAN_API_KEY', ''),
            api_secret=getattr(settings, 'DHAN_API_SECRET', ''),
        )

    @classmethod
    def get_access_token(cls) -> str:
        """
        Returns the active Dhan access token:
        1. User Input / Redis cache (dhan_token:{DHAN_CLIENT_ID}) — highest priority
        2. Static DHAN_ACCESS_TOKEN directly from .env (settings.DHAN_ACCESS_TOKEN)
        3. Fallback to DHAN_API_KEY in settings
        """
        client_id = getattr(settings, 'DHAN_CLIENT_ID', '')
        if client_id:
            cached = _get_redis().get(f"dhan_token:{client_id}")
            if cached:
                return cached

        env_token = (getattr(settings, 'DHAN_ACCESS_TOKEN', '') or '').strip()
        if env_token:
            return env_token

        # Fallback to direct API key in settings if set
        token = (getattr(settings, 'DHAN_API_KEY', '') or '').strip()
        return token


    @classmethod
    def get_client_id(cls) -> str:
        """Returns the admin Dhan client_id from settings."""
        return getattr(settings, 'DHAN_CLIENT_ID', '')

    @classmethod
    def invalidate_token(cls):
        """Forces access token refresh on next call."""
        client_id = getattr(settings, 'DHAN_CLIENT_ID', '')
        if client_id:
            _get_redis().delete(f"dhan_token:{client_id}")


# ─────────────────────────────────────────────────────────────────────────────
# USER Dhan Client
# Credentials source: UserTradingAccount (broker_client_id, api_key, app_id)
# Purpose: Live trade execution, sandbox runs, backtest operations
# ─────────────────────────────────────────────────────────────────────────────

class UserDhanClient:
    """
    Dhan API client for user-specific trading operations.
    Credentials sourced from the user's active UserTradingAccount record.
    """

    def __init__(self, account):
        """
        account: UserTradingAccount instance with broker_client_id, api_key, app_id.
        """
        self.account = account
        self.client_id = getattr(account, 'broker_client_id', '') or ''
        self.api_key = getattr(account, 'api_key', '') or ''
        self.api_secret = getattr(account, 'app_id', '') or ''

    def generate_login_url(self) -> dict:
        """Generates consent and returns the Dhan browser login URL for this user."""
        return generate_consent_login_url(
            client_id=self.client_id,
            api_key=self.api_key,
            api_secret=self.api_secret,
        )

    def generate_totp_login_url(self) -> str:
        """Returns direct TOTP 2FA web authorization redirect URL for Dhan."""
        return "https://web.dhan.co"

    def generate_access_token_via_totp(self, pin: str, totp: str) -> dict:
        """Generates access token instantly via Dhan PIN & TOTP 2FA code."""
        return generate_access_token_via_totp(client_id=self.client_id, pin=pin, totp=totp)

    def renew_access_token(self, access_token: str = None) -> str:
        """Renews active access token for another 24 hours."""
        token_to_renew = access_token or self.get_access_token()
        return renew_access_token(client_id=self.client_id, access_token=token_to_renew)

    def consume_token(self, token_id: str) -> str:
        """Consumes tokenId received from Dhan login redirect and caches accessToken."""
        return consume_consent_token(
            token_id=token_id,
            client_id=self.client_id,
            api_key=self.api_key,
            api_secret=self.api_secret,
        )

    def get_access_token(self) -> str:
        """
        Returns the active Dhan access token for this user:
        1. Checks Redis cache (dhan_token:{broker_client_id})
        2. Falls back to static account.api_key
        """
        if self.client_id:
            cached = _get_redis().get(f"dhan_token:{self.client_id}")
            if cached:
                return cached
        return self.api_key

    def invalidate_token(self):
        """Forces access token refresh for this user on next call."""
        if self.client_id:
            _get_redis().delete(f"dhan_token:{self.client_id}")


# ─────────────────────────────────────────────────────────────────────────────
# Backward-compatible module-level shortcuts
# ─────────────────────────────────────────────────────────────────────────────

def get_admin_dhan_token() -> str:
    """Convenience wrapper → AdminDhanClient.get_access_token()."""
    return AdminDhanClient.get_access_token()


def get_or_refresh_dhan_token(client_id: str, api_key: str, api_secret: str) -> str:
    """Convenience wrapper for checking/retrieving access token."""
    if client_id:
        cached = _get_redis().get(f"dhan_token:{client_id}")
        if cached:
            return cached
    return api_key


def invalidate_dhan_token(client_id: str):
    """Forces token refresh for any client_id."""
    if client_id:
        _get_redis().delete(f"dhan_token:{client_id}")

