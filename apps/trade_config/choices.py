from django.db import models

class RiskTypeChoices(models.TextChoices):
    PERCENTAGE = "percentage", "Percentage (%)"
    FIXED_AMOUNT = "fixed_amount", "Fixed Amount (₹/$)"
    POINTS = "points", "Points"