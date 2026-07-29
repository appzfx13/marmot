import logging
from typing import Optional, Dict, Any
from django.conf import settings
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

logger = logging.getLogger(__name__)


class TwilioService:
    """
    Service layer class for handling core Twilio API operations:
    - Standard SMS Dispatch
    - OTP Dispatch via Twilio Verify API
    - OTP Verification via Twilio Verify API
    """

    def __init__(self):
        # Fetch credentials from Django settings
        self.account_sid = getattr(settings, "TWILIO_ACCOUNT_SID", None)
        self.auth_token = getattr(settings, "TWILIO_AUTH_TOKEN", None)
        self.from_number = getattr(settings, "TWILIO_PHONE_NUMBER", None)
        self.verify_service_sid = getattr(settings, "TWILIO_VERIFY_SERVICE_SID", None)

        if not self.account_sid or not self.auth_token:
            logger.error("Twilio credentials (TWILIO_ACCOUNT_SID or TWILIO_AUTH_TOKEN) are missing in Django settings.")
            self.client = None
        else:
            self.client = Client(self.account_sid, self.auth_token)

    def _is_configured() -> bool:
        """Utility check to verify Twilio Client initialization."""
        return self.client is not None

    def send_sms(self, to_number: str, message_body: str) -> Dict[str, Any]:
        """
        Sends a standard transactional SMS message.
        
        :param to_number: Phone number in E.164 format (e.g., '+1234567890')
        :param message_body: Content of the SMS
        :return: Dict containing execution status and metadata/error response
        """
        if not self._is_configured():
            return {"success": False, "error": "Twilio client is not configured."}

        if not self.from_number:
            return {"success": False, "error": "TWILIO_PHONE_NUMBER missing from settings."}

        try:
            message = self.client.messages.create(
                body=message_body,
                from_=self.from_number,
                to=to_number
            )
            logger.info(f"SMS dispatched successfully to {to_number}. SID: {message.sid}")
            return {
                "success": True,
                "message_sid": message.sid,
                "status": message.status,
                "response": f"Message sent with SID {message.sid}"
            }

        except TwilioRestException as e:
            logger.error(f"Twilio REST Error during SMS send to {to_number}: {e.msg} (Code: {e.code})")
            return {
                "success": False,
                "error": e.msg,
                "code": e.code,
                "response": f"Twilio Error [{e.code}]: {e.msg}"
            }
        except Exception as e:
            logger.exception(f"Unexpected error while sending SMS to {to_number}")
            return {"success": False, "error": str(e), "response": str(e)}

    def dispatch_otp(self, to_number: str, channel: str = "sms") -> Dict[str, Any]:
        """
        Sends an OTP code using the Twilio Verify API service.
        
        :param to_number: Phone number in E.164 format
        :param channel: Delivery channel ('sms', 'call', or 'whatsapp')
        :return: Dict containing execution status and response details
        """
        if not self._is_configured():
            return {"success": False, "error": "Twilio client is not configured."}

        if not self.verify_service_sid:
            return {"success": False, "error": "TWILIO_VERIFY_SERVICE_SID is not configured."}

        try:
            verification = self.client.verify.v2.services(
                self.verify_service_sid
            ).verifications.create(to=to_number, channel=channel)

            logger.info(f"OTP dispatch initiated to {to_number} via {channel}. Status: {verification.status}")
            return {
                "success": True,
                "status": verification.status,
                "sid": verification.sid,
                "response": f"Verification status: {verification.status}"
            }

        except TwilioRestException as e:
            logger.error(f"Twilio Verify Error on OTP dispatch to {to_number}: {e.msg} (Code: {e.code})")
            return {
                "success": False,
                "error": e.msg,
                "code": e.code,
                "response": f"Twilio Verify Error [{e.code}]: {e.msg}"
            }
        except Exception as e:
            logger.exception(f"Unexpected error during OTP dispatch to {to_number}")
            return {"success": False, "error": str(e), "response": str(e)}

    def verify_otp(self, to_number: str, code: str) -> Dict[str, Any]:
        """
        Verifies an OTP code submitted by the user via Twilio Verify API.
        
        :param to_number: Phone number in E.164 format
        :param code: 6-digit verification code string
        :return: Dict containing validation result status
        """
        if not self._is_configured():
            return {"success": False, "error": "Twilio client is not configured."}

        if not self.verify_service_sid:
            return {"success": False, "error": "TWILIO_VERIFY_SERVICE_SID is not configured."}

        try:
            verification_check = self.client.verify.v2.services(
                self.verify_service_sid
            ).verification_checks.create(to=to_number, code=code)

            is_approved = verification_check.status == "approved"
            
            logger.info(f"OTP Verification for {to_number} result: {verification_check.status}")
            return {
                "success": is_approved,
                "status": verification_check.status,
                "valid": is_approved,
                "response": f"OTP Verification Check: {verification_check.status.upper()}"
            }

        except TwilioRestException as e:
            logger.error(f"Twilio Verify Check Error for {to_number}: {e.msg} (Code: {e.code})")
            return {
                "success": False,
                "error": e.msg,
                "code": e.code,
                "response": f"Twilio Check Error [{e.code}]: {e.msg}"
            }
        except Exception as e:
            logger.exception(f"Unexpected error during OTP verification for {to_number}")
            return {"success": False, "error": str(e), "response": str(e)}