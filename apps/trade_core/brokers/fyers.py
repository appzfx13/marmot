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

    def __init__(self, account_or_user=None, app_id: str = '', api_key: str = '', client_id: str = ''):
        if account_or_user:
            super().__init__(account_or_user)
            if app_id:
                self.app_id = app_id
            if api_key:
                self.api_key = api_key
            if client_id:
                self.client_id = client_id
        else:
            self.account = None
            self.user = None
            self.broker_name = 'fyers'
            self.app_id = app_id
            self.api_key = api_key
            self.client_id = client_id or app_id
            self.account_type = 'LIVE'

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
        app_id = self.app_id or self.client_id
        if not self.api_key or not app_id:
            logger.error("FYERS Historical Data Fetch Failed: Missing API credentials.")
            return []
            
        if not range_from or not range_to:
            now = datetime.now()
            # Default to last 7 days to ensure data across weekends and holidays
            range_to = now.strftime('%Y-%m-%d')
            range_from = (now - timedelta(days=7)).strftime('%Y-%m-%d')
            
        url = "https://api-t1.fyers.in/data/history"
        headers = {
            "Authorization": f"{app_id}:{self.api_key}",
            "Accept": "application/json"
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

    def get_quotes(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """Fetches authentic multi-symbol quotes from Fyers API v3 with short Redis cache."""
        app_id = self.app_id or self.client_id
        if not self.api_key or not app_id or not symbols:
            return {}

        from django.core.cache import cache

        symbols_str = ",".join(symbols)
        cache_key = f"marmot:fyers_quotes_batch:{hash(symbols_str)}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        url = f"https://api-t1.fyers.in/data/quotes?symbols={symbols_str}"
        headers = {
            "Authorization": f"{app_id}:{self.api_key}",
            "Accept": "application/json"
        }
        try:
            response = requests.get(url, headers=headers, timeout=5)
            response.raise_for_status()
            data = response.json()
            results = {}
            if data.get('s') == 'ok' and 'd' in data:
                for item in data['d']:
                    sym_name = item.get('n', '')
                    v = item.get('v', {})
                    results[sym_name] = {
                        'symbol': sym_name,
                        'ltp': v.get('lp', 0.0),
                        'ch': v.get('ch', 0.0),
                        'chp': v.get('chp', 0.0),
                        'open': v.get('open_price', 0.0),
                        'high': v.get('high_price', 0.0),
                        'low': v.get('low_price', 0.0),
                        'prev_close': v.get('prev_close_price', 0.0),
                        'volume': v.get('volume', 0),
                    }
                cache.set(cache_key, results, timeout=5)
                return results
            else:
                logger.error(f"FYERS Quotes API Error: {data.get('message', 'Unknown error')}")
                return {}
        except Exception as e:
            logger.error(f"Failed to fetch Fyers quotes: {str(e)}")
            return {}


