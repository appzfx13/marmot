from .base import BaseBrokerAdapter
from .dhan import DhanBrokerAdapter
from .fyers import FyersBrokerAdapter

class BrokerFactory:
    """
    Plug-and-Play Broker Factory.
    Dynamically resolves active broker adapter instance based on UserTradingAccount or User.
    """

    _adapters = {
        'dhan': DhanBrokerAdapter,
        'fyers': FyersBrokerAdapter,
        'sandbox': DhanBrokerAdapter,
    }

    @classmethod
    def get_adapter(cls, account_or_user) -> BaseBrokerAdapter:
        broker_code = 'dhan'
        if hasattr(account_or_user, 'broker') and account_or_user.broker:
            broker_code = getattr(account_or_user.broker, 'code', 'dhan').lower()
        elif hasattr(account_or_user, 'get_active_trading_account'):
            active = account_or_user.get_active_trading_account()
            if active and active.broker:
                broker_code = active.broker.code.lower()

        adapter_cls = cls._adapters.get(broker_code, DhanBrokerAdapter)
        return adapter_cls(account_or_user)

    @classmethod
    def get_admin_backup_adapter(cls) -> DhanBrokerAdapter:
        """Returns a DhanBrokerAdapter pre-loaded with admin backup credentials from settings."""
        client_id, api_key, api_secret = DhanBrokerAdapter.get_admin_dhan_credentials()

        class _AdminCredHolder:
            """Minimal credential holder used to seed a DhanBrokerAdapter for admin backup."""
            class broker:
                code = 'dhan'
            broker_client_id = client_id
            api_key = api_key
            app_id = api_secret
            account_type = 'LIVE'
            user = None

        return DhanBrokerAdapter(_AdminCredHolder())

    @classmethod
    def register_adapter(cls, broker_code: str, adapter_cls):
        """Plugin mechanism to register future broker adapters (e.g. Zerodha, AngelOne, etc.)."""
        cls._adapters[broker_code.lower()] = adapter_cls
