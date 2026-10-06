import json
import logging
from decimal import Decimal
from typing import Dict, Any, Optional

from django.db import transaction

from apps.market.services import redis_client
from apps.users.models import User
from apps.trade_config.models import TradeExecConfig, UserTradingAccount
from apps.trade_core.brokers.factory import BrokerFactory

logger = logging.getLogger(__name__)


class AccountGuardianService:
    """High-speed Two-Level Account Guardian for drawdown protection & circuit breaking."""

    @classmethod
    def get_redis_client(cls):
        return redis_client

    @classmethod
    def sync_user_risk_to_redis(cls, user: User) -> None:
        """Caches user risk thresholds and freeze flags into Redis for ultra-low latency Go worker lookups."""
        try:
            r = cls.get_redis_client()
            if not r:
                return

            config = TradeExecConfig.objects.filter(
                admins_user=user,
                is_active=True,
                is_deleted=False
            ).first()

            l1_limit = float(config.primary_loss_limit) if config and config.primary_loss_limit else 1000.0
            l2_limit = float(config.final_loss_limit) if config and config.final_loss_limit else 2000.0
            profit_limit = float(config.max_profit_limit) if config and config.max_profit_limit else 0.0

            payload = {
                "user_id": user.id,
                "username": user.username,
                "max_loss_status": bool(config.max_loss_status) if config else False,
                "primary_loss_limit": l1_limit,
                "final_loss_limit": l2_limit,
                "max_profit_limit": profit_limit,
                "primary_freeze": bool(user.primary_freeze),
                "final_freeze": bool(user.final_freeze),
                "trade_eligibility": bool(user.trade_eligibility),
                "is_blocked": bool(user.is_blocked),
            }

            key = f"marmot:risk:{user.id}"
            r.set(key, json.dumps(payload), ex=86400)
            logger.info("🛡️ [Account Guardian] Cached risk limits for @%s (L1: ₹%.2f | L2: ₹%.2f)", user.username, l1_limit, l2_limit)
        except Exception as e:
            logger.error("❌ [Account Guardian] Error caching risk limits in Redis: %s", e)

    @classmethod
    def trigger_primary_freeze(cls, user: User, current_loss: float = 0.0, reason: str = "") -> Dict[str, Any]:
        """Triggers Level 1 Warning Freeze: cancels open orders and activates Dhan Kill Switch."""
        if user.final_freeze:
            return {"success": False, "message": "User is already in Level 2 Hard Freeze."}

        logger.warning("⚠️ [Account Guardian] TRIGGERING LEVEL 1 WARNING FREEZE for @%s (Loss: ₹%.2f)", user.username, current_loss)
        
        with transaction.atomic():
            user.primary_freeze = True
            user.save(update_fields=['primary_freeze'])

        # Activate Dhan API Kill Switch & cancel pending orders
        trading_accounts = list(user.trading_accounts.filter(is_active=True))
        cancelled_orders = 0
        if trading_accounts:
            for acc in trading_accounts:
                try:
                    adapter = BrokerFactory.get_adapter(acc)
                    res = adapter.emergency_kill_switch()
                    cancelled_orders += res.get('cancelled_orders_count', 0)
                except Exception as e:
                    logger.error("Broker kill switch error for %s: %s", acc.account_name, e)

        cls.sync_user_risk_to_redis(user)

        # Notify via Redis PubSub
        try:
            r = cls.get_redis_client()
            if r:
                r.publish("marmot:guardian:events", json.dumps({
                    "event": "PRIMARY_FREEZE_TRIGGERED",
                    "user_id": user.id,
                    "username": user.username,
                    "current_loss": current_loss,
                    "reason": reason or f"Level 1 loss threshold breached (-₹{current_loss:.2f})",
                }))
        except Exception:
            pass

        return {
            "success": True,
            "level": 1,
            "status": "WARNING_FREEZE_ACTIVE",
            "message": f"Level 1 Warning Freeze activated (-₹{current_loss:.2f}). Dhan orders halted. One-click unlock available.",
            "cancelled_orders": cancelled_orders,
        }

    @classmethod
    def unlock_primary_freeze(cls, user: User) -> Dict[str, Any]:
        """Unlocks Level 1 Warning Freeze: deactivates Dhan Kill Switch and restores normal trading arm."""
        if user.final_freeze:
            return {
                "success": False,
                "message": "Permanent Day Lock Active (Level 2 Breached). Account cannot be unlocked until next day."
            }

        logger.info("🔓 [Account Guardian] UNLOCKING LEVEL 1 FREEZE for @%s", user.username)

        # Call Dhan Deactivate Kill Switch API
        trading_accounts = list(user.trading_accounts.filter(is_active=True))
        deactivated_count = 0
        broker_errors = []

        if trading_accounts:
            for acc in trading_accounts:
                try:
                    adapter = BrokerFactory.get_adapter(acc)
                    if hasattr(adapter, 'deactivate_kill_switch'):
                        res = adapter.deactivate_kill_switch()
                        if res.get('success'):
                            deactivated_count += 1
                        else:
                            broker_errors.append(res.get('message', ''))
                except Exception as e:
                    broker_errors.append(str(e))
        else:
            try:
                adapter = BrokerFactory.get_adapter(user)
                if hasattr(adapter, 'deactivate_kill_switch'):
                    res = adapter.deactivate_kill_switch()
                    if res.get('success'):
                        deactivated_count += 1
            except Exception as e:
                broker_errors.append(str(e))

        with transaction.atomic():
            user.primary_freeze = False
            user.trade_eligibility = True
            user.save(update_fields=['primary_freeze', 'trade_eligibility'])

        cls.sync_user_risk_to_redis(user)

        # Notify via Redis PubSub
        try:
            r = cls.get_redis_client()
            if r:
                r.publish("marmot:guardian:events", json.dumps({
                    "event": "PRIMARY_FREEZE_UNLOCKED",
                    "user_id": user.id,
                    "username": user.username,
                }))
        except Exception:
            pass

        return {
            "success": True,
            "level": 1,
            "status": "NORMAL_ARM_RESTORED",
            "message": "Dhan Kill Switch deactivated. Trading resumed successfully.",
            "deactivated_brokers": deactivated_count,
            "errors": broker_errors,
        }

    @classmethod
    def trigger_final_freeze(cls, user: User, current_loss: float = 0.0, reason: str = "") -> Dict[str, Any]:
        """Triggers Level 2 Hard Day Freeze: squares off positions, cancels orders, locks account for the WHOLE DAY."""
        logger.critical("🛑 [Account Guardian] TRIGGERING LEVEL 2 HARD DAY FREEZE for @%s (Loss: ₹%.2f)", user.username, current_loss)

        with transaction.atomic():
            user.primary_freeze = True
            user.final_freeze = True
            user.trade_eligibility = False
            user.is_blocked = True
            user.save(update_fields=[
                'primary_freeze', 'final_freeze', 'trade_eligibility', 'is_blocked'
            ])

        # Activate broker kill switch across all accounts, square off positions
        trading_accounts = list(user.trading_accounts.filter(is_active=True))
        squared_positions = 0
        cancelled_orders = 0

        if trading_accounts:
            for acc in trading_accounts:
                try:
                    adapter = BrokerFactory.get_adapter(acc)
                    res = adapter.emergency_kill_switch()
                    cancelled_orders += res.get('cancelled_orders_count', 0)
                    squared_positions += res.get('frozen_positions_count', 0)
                except Exception as e:
                    logger.error("Broker kill switch error for %s: %s", acc.account_name, e)

        cls.sync_user_risk_to_redis(user)

        # Notify via Redis PubSub
        try:
            r = cls.get_redis_client()
            if r:
                r.publish("marmot:guardian:events", json.dumps({
                    "event": "FINAL_FREEZE_TRIGGERED",
                    "user_id": user.id,
                    "username": user.username,
                    "current_loss": current_loss,
                    "reason": reason or f"Level 2 Hard Day Loss threshold breached (-₹{current_loss:.2f})",
                }))
        except Exception:
            pass

        return {
            "success": True,
            "level": 2,
            "status": "HARD_DAY_FREEZE_LOCKED",
            "message": f"Level 2 Hard Day Freeze activated (-₹{current_loss:.2f}). Account locked for the whole day. Positions squared off.",
            "cancelled_orders": cancelled_orders,
            "squared_positions": squared_positions,
        }

    @classmethod
    def evaluate_pnl(cls, user: User, pnl: float) -> Dict[str, Any]:
        """Evaluates live session PnL against 2-tier guardian limits and applies appropriate circuit breaker."""
        if user.final_freeze:
            return {"status": "ALREADY_HARD_FROZEN", "action_taken": None}

        config = TradeExecConfig.objects.filter(
            admins_user=user,
            is_active=True,
            is_deleted=False
        ).first()

        if not config or not config.max_loss_status:
            return {"status": "GUARDIAN_DISABLED", "action_taken": None, "pnl": pnl}

        l1_limit = float(config.primary_loss_limit) if config.primary_loss_limit else 1000.0
        l2_limit = float(config.final_loss_limit) if config.final_loss_limit else 2000.0

        loss = abs(pnl) if pnl < 0 else 0.0

        if pnl <= -l2_limit:
            return cls.trigger_final_freeze(user, current_loss=loss)
        elif pnl <= -l1_limit and not user.primary_freeze:
            return cls.trigger_primary_freeze(user, current_loss=loss)

        return {"status": "NORMAL", "action_taken": None, "pnl": pnl}
