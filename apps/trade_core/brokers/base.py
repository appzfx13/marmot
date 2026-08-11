from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class BaseBrokerAdapter(ABC):
    """
    Abstract Base Class for Plug-and-Play Broker Execution Adapters.
    Standardizes trade execution, position tracking, and API connection contracts.
    """

    def __init__(self, account_or_user):
        if hasattr(account_or_user, 'user'):
            self.account = account_or_user
            self.user = account_or_user.user
            self.broker_name = account_or_user.broker.code if account_or_user.broker else 'unknown'
            self.client_id = account_or_user.broker_client_id or ''
            self.api_key = account_or_user.api_key or ''
            self.app_id = account_or_user.app_id or ''
            self.account_type = account_or_user.account_type or 'SANDBOX'
        else:
            self.user = account_or_user
            self.account = getattr(account_or_user, 'get_active_trading_account', lambda: None)()
            if self.account and self.account.broker:
                self.broker_name = self.account.broker.code
                self.client_id = self.account.broker_client_id or ''
                self.api_key = self.account.api_key or ''
                self.app_id = self.account.app_id or ''
                self.account_type = self.account.account_type or 'SANDBOX'
            else:
                self.broker_name = 'sandbox'
                self.client_id = ''
                self.api_key = ''
                self.app_id = ''
                self.account_type = 'SANDBOX'

    @abstractmethod
    def test_connection(self) -> Dict[str, Any]:
        """Test connectivity and validate API key / client ID credentials."""
        pass

    @abstractmethod
    def place_order(
        self, 
        symbol: str, 
        quantity: int, 
        side: str, 
        order_type: str = 'MARKET', 
        price: float = 0.0, 
        stop_loss: float = 0.0,
        account_type: str = 'SANDBOX'
    ) -> Dict[str, Any]:
        """Place an order in LIVE or SANDBOX account mode."""
        pass

    @abstractmethod
    def cancel_order(self, order_id: str, account_type: str = 'SANDBOX') -> Dict[str, Any]:
        """Cancel an open order."""
        pass

    @abstractmethod
    def get_positions(self, account_type: str = 'SANDBOX') -> Dict[str, Any]:
        """Retrieve current open positions and live PnL telemetry."""
        pass

    @abstractmethod
    def calculate_estimated_brokerage(self, quantity: int, price: float, side: str) -> float:
        """Calculate estimated brokerage, STT, and exchange taxes."""
        pass

    @abstractmethod
    def emergency_kill_switch(self) -> Dict[str, Any]:
        """Emergency freeze all positions and cancel pending orders."""
        pass
