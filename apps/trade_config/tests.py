from decimal import Decimal
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.common.choices import CapitalReferenceChoices, MarketTypeChoices, MaxLossTypeChoices
from apps.trade_config.forms import TradeExecConfigForm
from apps.trade_config.models import TradeExecConfig
from apps.users.models import User


class TradeExecConfigRiskModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="risk_trader",
            email="risk_trader@example.com",
            password="SecurePassword123!",
        )

    def test_amount_based_max_loss_valid(self):
        config = TradeExecConfig(
            name="Amount Risk Config",
            admins_user=self.user,
            market_type=MarketTypeChoices.INDEX_FO,
            max_loss_status=True,
            max_loss_type=MaxLossTypeChoices.AMOUNT,
            max_loss_limit=Decimal("5000.00"),
        )
        config.full_clean()
        config.save()
        self.assertEqual(config.max_loss_type, MaxLossTypeChoices.AMOUNT)
        self.assertEqual(config.max_loss_limit, Decimal("5000.00"))

    def test_amount_based_max_loss_invalid_when_missing(self):
        config = TradeExecConfig(
            name="Invalid Amount Config",
            admins_user=self.user,
            market_type=MarketTypeChoices.INDEX_FO,
            max_loss_status=True,
            max_loss_type=MaxLossTypeChoices.AMOUNT,
            max_loss_limit=None,
        )
        with self.assertRaises(ValidationError) as ctx:
            config.full_clean()
        self.assertIn("max_loss_limit", ctx.exception.message_dict)

    def test_percentage_based_max_loss_opening_balance_valid(self):
        config = TradeExecConfig(
            name="Opening Balance % Risk Config",
            admins_user=self.user,
            market_type=MarketTypeChoices.INDEX_FO,
            max_loss_status=True,
            max_loss_type=MaxLossTypeChoices.PERCENTAGE,
            max_loss_percentage=Decimal("2.50"),
            max_loss_reference=CapitalReferenceChoices.OPENING_BALANCE,
        )
        config.full_clean()
        config.save()
        self.assertEqual(config.max_loss_type, MaxLossTypeChoices.PERCENTAGE)
        self.assertEqual(config.max_loss_percentage, Decimal("2.50"))
        self.assertEqual(config.max_loss_reference, CapitalReferenceChoices.OPENING_BALANCE)

    def test_percentage_based_max_loss_available_capital_valid(self):
        config = TradeExecConfig(
            name="Available Capital % Risk Config",
            admins_user=self.user,
            market_type=MarketTypeChoices.INDEX_FO,
            max_loss_status=True,
            max_loss_type=MaxLossTypeChoices.PERCENTAGE,
            max_loss_percentage=Decimal("3.00"),
            max_loss_reference=CapitalReferenceChoices.AVAILABLE_CAPITAL,
        )
        config.full_clean()
        config.save()
        self.assertEqual(config.max_loss_reference, CapitalReferenceChoices.AVAILABLE_CAPITAL)

    def test_percentage_based_max_loss_invalid_when_missing_percentage(self):
        config = TradeExecConfig(
            name="Invalid % Config",
            admins_user=self.user,
            market_type=MarketTypeChoices.INDEX_FO,
            max_loss_status=True,
            max_loss_type=MaxLossTypeChoices.PERCENTAGE,
            max_loss_percentage=None,
            max_loss_reference=CapitalReferenceChoices.OPENING_BALANCE,
        )
        with self.assertRaises(ValidationError) as ctx:
            config.full_clean()
        self.assertIn("max_loss_percentage", ctx.exception.message_dict)


class TradeExecConfigFormTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="form_trader",
            email="form_trader@example.com",
            password="SecurePassword123!",
        )

    def test_form_amount_mode_valid(self):
        form_data = {
            "name": "Live Amount Config",
            "admins_user": self.user.pk,
            "market_type": MarketTypeChoices.INDEX_FO,
            "is_active": True,
            "max_loss_status": True,
            "max_loss_type": MaxLossTypeChoices.AMOUNT,
            "max_loss_limit": "4000.00",
        }
        form = TradeExecConfigForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        self.assertEqual(saved.max_loss_limit, Decimal("4000.00"))

    def test_form_percentage_mode_valid(self):
        form_data = {
            "name": "Live Percentage Config",
            "admins_user": self.user.pk,
            "market_type": MarketTypeChoices.INDEX_FO,
            "is_active": True,
            "max_loss_status": True,
            "max_loss_type": MaxLossTypeChoices.PERCENTAGE,
            "max_loss_percentage": "2.00",
            "max_loss_reference": CapitalReferenceChoices.OPENING_BALANCE,
        }
        form = TradeExecConfigForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        self.assertEqual(saved.max_loss_percentage, Decimal("2.00"))
        self.assertEqual(saved.max_loss_reference, CapitalReferenceChoices.OPENING_BALANCE)

    def test_form_percentage_mode_missing_percentage_fails(self):
        form_data = {
            "name": "Live Percentage Config Invalid",
            "admins_user": self.user.pk,
            "market_type": MarketTypeChoices.INDEX_FO,
            "is_active": True,
            "max_loss_status": True,
            "max_loss_type": MaxLossTypeChoices.PERCENTAGE,
            "max_loss_percentage": "",
            "max_loss_reference": CapitalReferenceChoices.OPENING_BALANCE,
        }
        form = TradeExecConfigForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn("max_loss_percentage", form.errors)
