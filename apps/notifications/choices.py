from django.db import models


class GatewayServiceChoices(models.TextChoices):
    TWILIO_SMS = "TWILIO", "Twilio SMS"
    GO_RIVER = "GO_RIVER", "Go River Worker"
    LOCAL_DB = "LOCAL_DB", "Local Database"


class TestLogStatusChoices(models.TextChoices):
    PENDING = "PENDING", "Pending"
    SUCCESS = "SUCCESS", "Success"
    FAILED = "FAILED", "Failed"


class TestLogEventChoices(models.TextChoices):
    ADMIN_TEST_OTP_DISPATCH = "ADMIN_TEST_OTP_DISPATCH", "Admin Test OTP Dispatch"
    ADMIN_TEST_OTP_VERIFY = "ADMIN_TEST_OTP_VERIFY", "Admin Test OTP Verify"