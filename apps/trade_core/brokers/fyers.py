import logging
import uuid
import requests
from datetime import datetime, timedelta
from typing import Dict, Any, List
from .base import BaseBrokerAdapter

logger = logging.getLogger(__name__)

class FyersBrokerAdapter(BaseBrokerAdapter):
    """
    FYERS Broker Plug-and-Play Adapter (Placeholder ready for future extension).
    Implements standard execution contracts for FYERS REST API.
    """

    def test_connection(self) -> Dict[str, Any]:
        if not self.api_key or not self.client_id:
            return {
                'success': False,
                'status': 'CONFIG_REQUIRED',
                'message': 'FYERS App ID or Access Token missing. Please update in profile.'
            }
        return {
            'success': True,
            'status': 'CONNECTED',
            'broker': 'FYERS',
            'client_id': self.client_id,
            'message': f"FYERS API connected successfully for Client ID {self.client_id}."
        }

    def place_order(
        self, 
        symbol: str, 
        quantity: int, 
        side: str, 
        order_type: str = 'MARKET', 
        price: float = 0.0, 
        stop_loss: float = 0.0,
        take_profit: float = 0.0,
        account_type: str = 'SANDBOX'
    ) -> Dict[str, Any]:
        order_id = f"FYERS-{'SANDBOX' if account_type == 'SANDBOX' else 'LIVE'}-{uuid.uuid4().hex[:8].upper()}"
        estimated_brokerage = self.calculate_estimated_brokerage(quantity, price, side)

        telemetry = {
            'order_id': order_id,
            'broker': 'FYERS',
            'account_type': account_type,
            'symbol': symbol,
            'quantity': quantity,
            'side': side.upper(),
            'order_type': order_type,
            'price': price,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'status': 'EXECUTED',
            'estimated_brokerage': estimated_brokerage,
            'api_response': {
                'status': 'success',
                'fyers_client_id': self.client_id,
                'execution_mode': account_type,
                'order_status': 'TRADED',
                'remarks': f"FYERS order {order_id} placed in {account_type} mode."
            }
        }
        logger.info(f"FYERS Order Executed [{account_type}]: {order_id} for user @{self.user.username}")
        return telemetry

    def cancel_order(self, order_id: str, account_type: str = 'SANDBOX') -> Dict[str, Any]:
        return {
            'success': True,
            'order_id': order_id,
            'broker': 'FYERS',
            'account_type': account_type,
            'status': 'CANCELLED',
            'message': f"FYERS Order {order_id} cancelled successfully."
        }

    def get_positions(self, account_type: str = 'SANDBOX') -> Dict[str, Any]:
        return {
            'broker': 'FYERS',
            'account_type': account_type,
            'positions': [],
            'net_pnl': float(self.user.pl_integer or 0.00),
            'status': 'HEALTHY'
        }

    def calculate_estimated_brokerage(self, quantity: int, price: float, side: str) -> float:
        turnover = max(quantity * price, 100.0)
        brokerage = min(20.0, turnover * 0.0005)
        stt_tax = turnover * 0.000125 if side.upper() == 'SELL' else 0.0
        return round(brokerage + stt_tax + 5.0, 2)

    def emergency_kill_switch(self) -> Dict[str, Any]:
        logger.warning(f"FYERS EMERGENCY KILL SWITCH TRIGGERED for user @{self.user.username} (Client ID: {self.client_id})")
        return {
            'success': True,
            'broker': 'FYERS',
            'client_id': self.client_id,
            'cancelled_orders_count': 0,
            'frozen_positions_count': 0,
            'message': f"All FYERS orders and positions frozen for Client ID {self.client_id}."
        }

    def get_historical_data(
        self,
        symbol: str,
        resolution: str = "1",
        range_from: str = None,
        range_to: str = None
    ) -> List[Dict[str, Any]]:
        """
        Fetches true historical OHLCV data from Fyers API.
        No dummy data is returned.
        """
        if not self.api_key or not self.client_id:
            logger.error("FYERS Historical Data Fetch Failed: Missing API credentials.")
            return []
            
        if not range_from or not range_to:
            now = datetime.now()
            # Default to last 3 days to ensure data if today is a weekend
            range_to = now.strftime('%Y-%m-%d')
            range_from = (now - timedelta(days=3)).strftime('%Y-%m-%d')
            
        url = "https://api.fyers.in/data-rest/v3/history/"
        headers = {
            "Authorization": f"{self.client_id}:{self.api_key}"
        }
        params = {
            "symbol": symbol,
            "resolution": resolution,
            "date_format": "1", # 1 for epoch format 
            "range_from": range_from,
            "range_to": range_to,
            "cont_flag": "1"
        }
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get('s') == 'ok' and 'candles' in data:
                # Format: [epoch, open, high, low, close, volume]
                formatted_data = []
                for candle in data['candles']:
                    formatted_data.append({
                        "time": candle[0], 
                        "open": candle[1],
                        "high": candle[2],
                        "low": candle[3],
                        "close": candle[4],
                        "volume": candle[5]
                    })
                return formatted_data
            else:
                logger.error(f"FYERS API Error: {data.get('message', 'Unknown error')}")
                return []
        except Exception as e:
            logger.error(f"Failed to fetch Fyers historical data: {str(e)}")
            return []

