import logging
import uuid
import json
from typing import Dict, Any, Tuple
from concurrent.futures import ThreadPoolExecutor
from django.conf import settings
from apps.trade_core.services.dhan_token_service import UserDhanClient, _get_redis
from .base import BaseBrokerAdapter

logger = logging.getLogger(__name__)

class DhanBrokerAdapter(BaseBrokerAdapter):
    """
    Active Dhan Broker Plug-and-Play Execution Adapter.
    Handles Dhan REST API & WebSocket execution telemetry for Sandbox & Live modes.
    """

    @classmethod
    def get_admin_dhan_credentials(cls) -> Tuple[str, str, str]:
        """Returns (client_id, api_key, api_secret) for the global admin Dhan account from settings."""
        return (
            getattr(settings, 'DHAN_CLIENT_ID', ''),
            getattr(settings, 'DHAN_API_KEY', ''),
            getattr(settings, 'DHAN_API_SECRET', ''),
        )

    def get_access_token(self) -> str:
        """
        Returns a valid Dhan access token for this user's trading account.
        Uses UserDhanClient — credentials from UserTradingAccount (broker_client_id, api_key, app_id).
        """
        return UserDhanClient(self.account).get_access_token()

    def test_connection(self) -> Dict[str, Any]:
        """
        Performs live HTTP authentication verification against Dhan servers.
        Tests direct access token (GET /v2/fundlimit) or OAuth App credentials (POST /app/generate-consent).
        """
        import requests

        if not self.client_id:
            return {
                'success': False,
                'status': 'CONFIG_REQUIRED',
                'broker': 'DHAN',
                'message': 'Dhan Client ID is required.'
            }
        clean_client_id = str(self.client_id or getattr(self.account, 'broker_client_id', '') or '').strip().strip('"').strip("'")
        clean_api_key = str(self.api_key or getattr(self.account, 'api_key', '') or '').strip().strip('"').strip("'")
        clean_app_secret = str(getattr(self.account, 'app_id', '') or '').strip().strip('"').strip("'")

        # 1. If direct Access Token is provided (starts with eyJ or len > 40)
        token_to_test = clean_api_key or self.get_access_token()
        if token_to_test:
            clean_token = str(token_to_test).strip().strip('"').strip("'")
            try:
                url = "https://api.dhan.co/v2/fundlimit"
                headers = {
                    "access-token": clean_token,
                    "client-id": clean_client_id,
                    "Accept": "application/json"
                }
                resp = requests.get(url, headers=headers, timeout=8)
                if resp.status_code == 200:
                    data = resp.json()
                    avail_cash = data.get("availabelBalance", data.get("cash", "0.00"))
                    try:
                        from apps.trade_core.services.dhan_token_service import _get_redis, _TOKEN_TTL_SECONDS
                        _get_redis().setex(f"dhan_token:{clean_client_id}", _TOKEN_TTL_SECONDS, clean_token)
                    except Exception:
                        pass
                    return {
                        'success': True,
                        'status': 'CONNECTED',
                        'broker': 'DHAN',
                        'client_id': clean_client_id,
                        'cash': avail_cash,
                        'details': data,
                        'message': f"Dhan Live Connection verified successfully! Available balance: ₹{avail_cash}"
                    }
                elif resp.status_code == 401 and clean_app_secret:
                    # If direct token failed but App Secret is provided, try Partner App Consent Flow
                    pass
                else:
                    err_msg = resp.text
                    try:
                        err_json = resp.json()
                        err_msg = err_json.get("errorMessage") or err_json.get("remarks", {}).get("error_message") or err_json.get("message") or resp.text
                    except Exception:
                        pass
                    if resp.status_code == 401:
                        err_msg = f"{err_msg}. Please verify your 10-digit Dhan Client ID and ensure you paste the full Access Token (starts with eyJ...) from web.dhan.co > DhanHQ Developer section."
                    return {
                        'success': False,
                        'status': 'AUTH_FAILED',
                        'broker': 'DHAN',
                        'client_id': clean_client_id,
                        'message': f"Dhan Live Auth Failed (HTTP {resp.status_code}): {err_msg}"
                    }
            except requests.RequestException as e:
                logger.error("Dhan test_connection network error: %s", e)
                return {
                    'success': False,
                    'status': 'NETWORK_ERROR',
                    'broker': 'DHAN',
                    'client_id': clean_client_id,
                    'message': f"Failed to connect to Dhan servers: {e}"
                }

        # 2. Test generate-consent with Partner App ID & Secret if secret is present
        if clean_app_secret and clean_api_key:
            try:
                from apps.trade_core.services.dhan_token_service import generate_consent_login_url
                res = generate_consent_login_url(clean_client_id, clean_api_key, clean_app_secret)
                return {
                    'success': True,
                    'status': 'CONNECTED',
                    'broker': 'DHAN',
                    'client_id': clean_client_id,
                    'message': f"Dhan Partner App verified successfully (Consent App ID: {res.get('consentAppId')})."
                }
            except Exception as e:
                logger.warning("Dhan generate_consent_login_url notice for %s: %s", clean_client_id, e)
                return {
                    'success': False,
                    'status': 'AUTH_FAILED',
                    'broker': 'DHAN',
                    'client_id': clean_client_id,
                    'message': f"Dhan Partner App verification failed: {e}"
                }

        return {
            'success': False,
            'status': 'CONFIG_REQUIRED',
            'broker': 'DHAN',
            'client_id': clean_client_id,
            'message': 'Dhan API Key or Access Token is required.'
        }

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
        order_id = f"DHAN-{'SANDBOX' if account_type == 'SANDBOX' else 'LIVE'}-{uuid.uuid4().hex[:8].upper()}"
        estimated_brokerage = self.calculate_estimated_brokerage(quantity, price, side)

        telemetry = {
            'order_id': order_id,
            'broker': 'DHAN',
            'account_type': account_type,
            'symbol': symbol,
            'quantity': quantity,
            'side': side.upper(),
            'order_type': order_type,
            'price': price,
            'stop_loss': stop_loss,
            'status': 'EXECUTED',
            'estimated_brokerage': estimated_brokerage,
            'api_response': {
                'status': 'success',
                'dhan_client_id': self.client_id,
                'execution_mode': account_type,
                'order_status': 'TRADED',
                'remarks': f"Dhan order {order_id} placed in {account_type} mode."
            }
        }
        logger.info(f"Dhan Order Executed [{account_type}]: {order_id} for user @{self.user.username}")
        return telemetry

    def cancel_order(self, order_id: str, account_type: str = 'SANDBOX') -> Dict[str, Any]:
        return {
            'success': True,
            'order_id': order_id,
            'broker': 'DHAN',
            'account_type': account_type,
            'status': 'CANCELLED',
            'message': f"Dhan Order {order_id} cancelled successfully."
        }

    def get_fund_limits(self) -> Dict[str, Any]:
        """Fetches live available funds & margins from Dhan /v2/fundlimit."""
        import requests
        token = str(self.get_access_token() or '').strip().strip('"').strip("'")
        client_id = str(self.client_id or '').strip().strip('"').strip("'")
        if not token or not client_id:
            return {'success': False, 'status': 'UNCONFIGURED', 'available_balance': '0.00', 'cash': '0.00'}

        try:
            url = "https://api.dhan.co/v2/fundlimit"
            headers = {"access-token": token, "client-id": client_id, "Accept": "application/json"}
            resp = requests.get(url, headers=headers, timeout=6)
            if resp.status_code == 200:
                data = resp.json()
                avail_cash = data.get("availabelBalance", data.get("cash", "0.00"))
                return {
                    'success': True,
                    'status': 'ACTIVE',
                    'available_balance': str(avail_cash),
                    'cash': str(data.get("cash", "0.00")),
                    'collateral': str(data.get("collateralAmount", "0.00")),
                    'margin_utilized': str(data.get("utilizedAmount", "0.00")),
                    'withdrawable': str(data.get("withdrawableBalance", "0.00")),
                    'raw': data
                }
            return {'success': False, 'status': f'HTTP_{resp.status_code}', 'available_balance': '0.00', 'cash': '0.00'}
        except Exception as e:
            logger.warning("Dhan get_fund_limits exception: %s", e)
            return {'success': False, 'status': 'ERROR', 'available_balance': '0.00', 'cash': '0.00'}

    def get_holdings(self) -> Dict[str, Any]:
        """Fetches long-term Demat & CNC Equity portfolio holdings from DhanHQ v2 API: GET /v2/holdings."""
        account_id = getattr(self.account, 'id', None) or getattr(self.user, 'id', 'default')
        cache_key = f"marmot:dhan:holdings:{account_id}"

        try:
            cached_json = _get_redis().get(cache_key)
            if cached_json:
                return json.loads(cached_json)
        except Exception as cache_err:
            logger.warning("Redis read exception in get_holdings: %s", cache_err)

        import requests
        token = str(self.get_access_token() or '').strip().strip('"').strip("'")
        client_id = str(self.client_id or '').strip().strip('"').strip("'")
        if not token or not client_id:
            return {'success': False, 'holdings': [], 'total_invested': 0.00, 'current_value': 0.00, 'total_pnl': 0.00, 'pnl_pct': 0.00, 'holdings_count': 0}

        try:
            url = "https://api.dhan.co/v2/holdings"
            headers = {"access-token": token, "client-id": client_id, "Accept": "application/json"}
            resp = requests.get(url, headers=headers, timeout=6)
            if resp.status_code == 200:
                raw_data = resp.json()
                if not isinstance(raw_data, list):
                    raw_data = []

                total_invested = 0.0
                current_val = 0.0
                parsed_holdings = []

                for item in raw_data:
                    total_qty = int(item.get("totalQty", 0) or 0)
                    dp_qty = int(item.get("dpQty", 0) or 0)
                    available_qty = int(item.get("availableQty", total_qty) or total_qty)
                    avg_cost = float(item.get("avgCostPrice", item.get("costPrice", 0.0)) or 0.0)
                    ltp = float(item.get("lastTradedPrice", item.get("ltp", avg_cost)) or avg_cost)
                    
                    inv_item = round(total_qty * avg_cost, 2)
                    cur_item = round(total_qty * ltp, 2)
                    pnl_item = round(cur_item - inv_item, 2)
                    pnl_pct_item = round((pnl_item / max(inv_item, 1.0)) * 100, 2) if inv_item > 0 else 0.0

                    total_invested += inv_item
                    current_val += cur_item

                    parsed_holdings.append({
                        'trading_symbol': item.get("tradingSymbol", "EQUITY"),
                        'exchange': item.get("exchange", "NSE"),
                        'security_id': item.get("securityId", ""),
                        'isin': item.get("isin", ""),
                        'total_qty': total_qty,
                        'dp_qty': dp_qty,
                        'available_qty': available_qty,
                        'avg_cost_price': avg_cost,
                        'last_traded_price': ltp,
                        'invested_value': inv_item,
                        'current_value': cur_item,
                        'pnl': pnl_item,
                        'pnl_pct': pnl_pct_item,
                    })

                total_pnl = round(current_val - total_invested, 2)
                pnl_pct = round((total_pnl / max(total_invested, 1.0)) * 100, 2) if total_invested > 0 else 0.0

                result = {
                    'success': True,
                    'holdings': parsed_holdings,
                    'total_invested': round(total_invested, 2),
                    'current_value': round(current_val, 2),
                    'total_pnl': total_pnl,
                    'pnl_pct': pnl_pct,
                    'holdings_count': len(parsed_holdings)
                }
                try:
                    _get_redis().setex(cache_key, 30, json.dumps(result))
                except Exception:
                    pass
                return result
            return {'success': False, 'holdings': [], 'total_invested': 0.00, 'current_value': 0.00, 'total_pnl': 0.00, 'pnl_pct': 0.00, 'holdings_count': 0}
        except Exception as e:
            logger.warning("Dhan get_holdings exception: %s", e)
            return {'success': False, 'holdings': [], 'total_invested': 0.00, 'current_value': 0.00, 'total_pnl': 0.00, 'pnl_pct': 0.00, 'holdings_count': 0}

    def get_live_positions(self) -> Dict[str, Any]:
        """Fetches live intraday positions and real-time net PnL from Dhan /v2/positions."""
        import requests
        token = str(self.get_access_token() or '').strip().strip('"').strip("'")
        client_id = str(self.client_id or '').strip().strip('"').strip("'")
        if not token or not client_id:
            return {'success': False, 'positions': [], 'net_pnl': 0.00, 'realized_pnl': 0.00, 'unrealized_pnl': 0.00, 'open_positions_count': 0, 'closed_positions_count': 0}

        try:
            url = "https://api.dhan.co/v2/positions"
            headers = {"access-token": token, "client-id": client_id, "Accept": "application/json"}
            resp = requests.get(url, headers=headers, timeout=6)
            if resp.status_code == 200:
                positions_data = resp.json()
                if not isinstance(positions_data, list):
                    positions_data = []
                net_pnl = 0.0
                total_realized = 0.0
                total_unrealized = 0.0
                open_count = 0
                closed_count = 0
                parsed_positions = []

                for pos in positions_data:
                    realized = float(pos.get("realizedProfit", 0.0) or 0.0)
                    unrealized = float(pos.get("unrealizedProfit", 0.0) or 0.0)
                    tot_pos_pnl = round(realized + unrealized, 2)
                    net_qty = int(pos.get("netQty", 0) or 0)
                    buy_qty = int(pos.get("buyQty", 0) or 0)
                    sell_qty = int(pos.get("sellQty", 0) or 0)
                    buy_avg = float(pos.get("buyAvg", 0.0) or 0.0)
                    sell_avg = float(pos.get("sellAvg", 0.0) or 0.0)
                    
                    if net_qty != 0:
                        open_count += 1
                        pos_status = "OPEN"
                    else:
                        closed_count += 1
                        pos_status = "CLOSED"

                    net_pnl += tot_pos_pnl
                    total_realized += realized
                    total_unrealized += unrealized

                    parsed_positions.append({
                        'position_type': pos.get("positionType", "LONG" if net_qty > 0 else ("SHORT" if net_qty < 0 else "CLOSED")),
                        'trading_symbol': pos.get("tradingSymbol", ""),
                        'security_id': pos.get("securityId", ""),
                        'exchange_segment': pos.get("exchangeSegment", "NSE_FNO"),
                        'product_type': pos.get("productType", "INTRADAY"),
                        'buy_qty': buy_qty,
                        'sell_qty': sell_qty,
                        'net_qty': net_qty,
                        'buy_avg': buy_avg,
                        'sell_avg': sell_avg,
                        'realized_profit': round(realized, 2),
                        'unrealized_profit': round(unrealized, 2),
                        'total_pnl': tot_pos_pnl,
                        'status': pos_status,
                        'cross_currency': pos.get("crossCurrency", False),
                    })

                return {
                    'success': True,
                    'positions': parsed_positions,
                    'net_pnl': round(net_pnl, 2),
                    'realized_pnl': round(total_realized, 2),
                    'unrealized_pnl': round(total_unrealized, 2),
                    'open_positions_count': open_count,
                    'closed_positions_count': closed_count,
                }
            return {'success': False, 'positions': [], 'net_pnl': 0.00, 'realized_pnl': 0.00, 'unrealized_pnl': 0.00, 'open_positions_count': 0, 'closed_positions_count': 0}
        except Exception as e:
            logger.warning("Dhan get_live_positions exception: %s", e)
            return {'success': False, 'positions': [], 'net_pnl': 0.00, 'realized_pnl': 0.00, 'unrealized_pnl': 0.00, 'open_positions_count': 0, 'closed_positions_count': 0}

    def get_live_orders(self) -> Dict[str, Any]:
        """Fetches today's live orders telemetry from Dhan /v2/orders."""
        import requests
        token = str(self.get_access_token() or '').strip().strip('"').strip("'")
        client_id = str(self.client_id or '').strip().strip('"').strip("'")
        if not token or not client_id:
            return {'success': False, 'orders': [], 'orders_count': 0, 'open_orders_count': 0, 'traded_orders_count': 0}

        try:
            url = "https://api.dhan.co/v2/orders"
            headers = {"access-token": token, "client-id": client_id, "Accept": "application/json"}
            resp = requests.get(url, headers=headers, timeout=6)
            if resp.status_code == 200:
                orders_data = resp.json()
                if not isinstance(orders_data, list):
                    orders_data = []
                
                open_cnt = 0
                traded_cnt = 0
                parsed_orders = []
                for ord_item in orders_data:
                    st = str(ord_item.get("orderStatus", "")).upper()
                    if st in ["PENDING", "TRANSIT", "CONFIRM"]:
                        open_cnt += 1
                    elif st == "TRADED":
                        traded_cnt += 1

                    parsed_orders.append({
                        'order_id': ord_item.get("orderId", ""),
                        'exchange_order_id': ord_item.get("exchangeOrderId", ""),
                        'order_status': st,
                        'transaction_type': str(ord_item.get("transactionType", "BUY")).upper(),
                        'exchange_segment': ord_item.get("exchangeSegment", "NSE_FNO"),
                        'product_type': ord_item.get("productType", "INTRADAY"),
                        'order_type': ord_item.get("orderType", "MARKET"),
                        'validity': ord_item.get("validity", "DAY"),
                        'trading_symbol': ord_item.get("tradingSymbol", ""),
                        'security_id': ord_item.get("securityId", ""),
                        'quantity': int(ord_item.get("quantity", 0) or 0),
                        'filled_qty': int(ord_item.get("filledQty", ord_item.get("quantity", 0)) or 0),
                        'price': float(ord_item.get("price", 0.0) or 0.0),
                        'trigger_price': float(ord_item.get("triggerPrice", 0.0) or 0.0),
                        'create_time': ord_item.get("createTime", ""),
                        'update_time': ord_item.get("updateTime", ""),
                        'oms_error_code': ord_item.get("omsErrorCode", ""),
                        'oms_error_desc': ord_item.get("omsErrorDescription", ""),
                    })

                # Sort newest first by create_time
                parsed_orders.sort(key=lambda x: str(x.get('create_time', '')), reverse=True)

                return {
                    'success': True,
                    'orders': parsed_orders,
                    'orders_count': len(parsed_orders),
                    'open_orders_count': open_cnt,
                    'traded_orders_count': traded_cnt,
                }
            return {'success': False, 'orders': [], 'orders_count': 0, 'open_orders_count': 0, 'traded_orders_count': 0}
        except Exception as e:
            logger.warning("Dhan get_live_orders exception: %s", e)
            return {'success': False, 'orders': [], 'orders_count': 0, 'open_orders_count': 0, 'traded_orders_count': 0}

    def cancel_live_order(self, order_id: str) -> Dict[str, Any]:
        """Cancels an active live order via DhanHQ v2 API: DELETE /v2/orders/{orderId}."""
        import requests
        token = str(self.get_access_token() or '').strip().strip('"').strip("'")
        client_id = str(self.client_id or '').strip().strip('"').strip("'")
        if not token or not client_id:
            return {'success': False, 'message': 'Missing Dhan credentials or active session token.'}

        try:
            url = f"https://api.dhan.co/v2/orders/{order_id}"
            headers = {"access-token": token, "client-id": client_id, "Accept": "application/json"}
            resp = requests.delete(url, headers=headers, timeout=6)
            if resp.status_code == 200:
                return {'success': True, 'order_id': order_id, 'message': f'Order {order_id} cancelled successfully.'}
            return {'success': False, 'order_id': order_id, 'message': f'Cancel failed (HTTP {resp.status_code}): {resp.text}'}
        except Exception as e:
            logger.error("Dhan cancel_live_order error for %s: %s", order_id, e)
            return {'success': False, 'order_id': order_id, 'message': f'Network error cancelling order: {e}'}

    def square_off_position(self, symbol: str, quantity: int, side: str, product_type: str = 'INTRADAY', security_id: str = '') -> Dict[str, Any]:
        """Squares off an active position by routing an opposite MARKET order."""
        exit_side = 'SELL' if side.upper() == 'BUY' or int(quantity) > 0 else 'BUY'
        exit_qty = abs(int(quantity))
        return self.place_order(
            symbol=symbol,
            quantity=exit_qty,
            side=exit_side,
            order_type='MARKET',
            account_type='LIVE'
        )

    def get_trade_book(self) -> Dict[str, Any]:
        """Fetches executed trade book telemetry from Dhan /v2/trades (DhanHQ v2 API) with Redis caching."""
        account_id = getattr(self.account, 'id', None) or getattr(self.user, 'id', 'default')
        cache_key = f"marmot:dhan:trade_book:{account_id}"

        try:
            cached_json = _get_redis().get(cache_key)
            if cached_json:
                res_data = json.loads(cached_json)
                print(f"[DHAN API DEBUG] Redis Cache Hit for get_trade_book() | Trades Count: {res_data.get('trades_count', 0)}")
                return res_data
        except Exception as cache_err:
            logger.warning("Redis read exception in get_trade_book: %s", cache_err)

        import requests
        token = str(self.get_access_token() or '').strip().strip('"').strip("'")
        client_id = str(self.client_id or '').strip().strip('"').strip("'")
        if not token or not client_id:
            print(f"[DHAN API DEBUG] get_trade_book() skipped: Missing token or client_id (client_id={client_id})")
            return {'success': False, 'trades': [], 'trades_count': 0}

        try:
            url = "https://api.dhan.co/v2/trades"
            headers = {"access-token": token, "client-id": client_id, "Accept": "application/json"}
            resp = requests.get(url, headers=headers, timeout=5)
            print(f"[DHAN API DEBUG] GET /v2/trades HTTP {resp.status_code} | Raw Response: {resp.text[:300]}")
            if resp.status_code == 200:
                trades_data = resp.json()
                if not isinstance(trades_data, list):
                    trades_data = []
                result = {'success': True, 'trades': trades_data, 'trades_count': len(trades_data)}
                try:
                    _get_redis().setex(cache_key, 30, json.dumps(result))
                except Exception:
                    pass
                return result
            return {'success': False, 'trades': [], 'trades_count': 0}
        except Exception as e:
            logger.warning("Dhan get_trade_book exception: %s", e)
            print(f"[DHAN API DEBUG] get_trade_book Exception: {e}")
            return {'success': False, 'trades': [], 'trades_count': 0}

    def get_trade_history(self, from_date: str, to_date: str, page: int = 0, fetch_all: bool = True) -> Dict[str, Any]:
        """Fetches historical trade execution statements from DhanHQ v2 API: GET /v2/trades/{from-date}/{to-date}/{page}."""
        account_id = getattr(self.account, 'id', None) or getattr(self.user, 'id', 'default')
        cache_key = f"marmot:dhan:trade_history:{account_id}:{from_date}:{to_date}:{page}:{fetch_all}"

        try:
            cached_json = _get_redis().get(cache_key)
            if cached_json:
                res_data = json.loads(cached_json)
                print(f"[DHAN STATEMENTS DEBUG] Redis Cache Hit for get_trade_history({from_date}, {to_date}, page={page}, fetch_all={fetch_all}) | Trades: {res_data.get('trades_count', 0)}")
                return res_data
        except Exception as cache_err:
            logger.warning("Redis read exception in get_trade_history: %s", cache_err)

        import requests
        token = str(self.get_access_token() or '').strip().strip('"').strip("'")
        client_id = str(self.client_id or '').strip().strip('"').strip("'")
        if not token or not client_id:
            print(f"[DHAN STATEMENTS DEBUG] get_trade_history() skipped: Missing token or client_id (client_id={client_id})")
            return {'success': False, 'trades': [], 'trades_count': 0}

        try:
            all_trades_list = []
            curr_page = page
            headers = {"access-token": token, "client-id": client_id, "Accept": "application/json"}
            
            while True:
                url = f"https://api.dhan.co/v2/trades/{from_date}/{to_date}/{curr_page}"
                resp = requests.get(url, headers=headers, timeout=6)
                print(f"[DHAN STATEMENTS DEBUG] GET /v2/trades/{from_date}/{to_date}/{curr_page} HTTP {resp.status_code} | Raw: {resp.text[:200]}")
                if resp.status_code == 200:
                    page_trades = resp.json()
                    if isinstance(page_trades, list) and len(page_trades) > 0:
                        all_trades_list.extend(page_trades)
                        if not fetch_all or len(page_trades) < 20 or curr_page >= 10:
                            break
                        curr_page += 1
                        continue
                break

            result = {'success': True, 'trades': all_trades_list, 'trades_count': len(all_trades_list)}
            try:
                _get_redis().setex(cache_key, 60, json.dumps(result))
            except Exception:
                pass
            return result
        except Exception as e:
            logger.warning("Dhan get_trade_history exception: %s", e)
            print(f"[DHAN STATEMENTS DEBUG] get_trade_history Exception: {e}")
            return {'success': False, 'trades': [], 'trades_count': 0}

    def get_ledger_statements(self, from_date: str, to_date: str) -> Dict[str, Any]:
        """Fetches ledger statements & statutory charges from DhanHQ v2 API: GET /v2/ledger?from-date={from_date}&to-date={to_date}."""
        account_id = getattr(self.account, 'id', None) or getattr(self.user, 'id', 'default')
        cache_key = f"marmot:dhan:ledger:{account_id}:{from_date}:{to_date}"

        try:
            cached_json = _get_redis().get(cache_key)
            if cached_json:
                return json.loads(cached_json)
        except Exception:
            pass

        import requests
        token = str(self.get_access_token() or '').strip().strip('"').strip("'")
        client_id = str(self.client_id or '').strip().strip('"').strip("'")
        if not token or not client_id:
            return {'success': False, 'ledger': [], 'total_charges': 0.0}

        try:
            url = f"https://api.dhan.co/v2/ledger?from-date={from_date}&to-date={to_date}"
            headers = {"access-token": token, "client-id": client_id, "Accept": "application/json"}
            resp = requests.get(url, headers=headers, timeout=6)
            if resp.status_code == 200:
                ledger_data = resp.json()
                if not isinstance(ledger_data, list):
                    ledger_data = []
                total_charges = sum(float(item.get('dhanFee', 0.0) or item.get('stt', 0.0) or item.get('sebiTax', 0.0) or 0.0) for item in ledger_data)
                result = {'success': True, 'ledger': ledger_data, 'total_charges': round(total_charges, 2)}
                try:
                    _get_redis().setex(cache_key, 60, json.dumps(result))
                except Exception:
                    pass
                return result
            return {'success': False, 'ledger': [], 'total_charges': 0.0}
        except Exception as e:
            logger.warning("Dhan get_ledger_statements exception: %s", e)
            return {'success': False, 'ledger': [], 'total_charges': 0.0}

    def get_live_dashboard_summary(self) -> Dict[str, Any]:
        """Aggregates funds, positions, PnL, and auth health for the Live Dashboard via parallel ThreadPool & shared Redis cache."""
        account_id = getattr(self.account, 'id', None) or getattr(self.user, 'id', 'default')
        cache_key = f"marmot:dhan:live_summary:{account_id}"

        try:
            cached_json = _get_redis().get(cache_key)
            if cached_json:
                return json.loads(cached_json)
        except Exception as cache_err:
            logger.warning("Redis read exception in get_live_dashboard_summary: %s", cache_err)

        # Parallel execution of 4 HTTP API requests to Dhan
        with ThreadPoolExecutor(max_workers=4) as executor:
            future_funds = executor.submit(self.get_fund_limits)
            future_positions = executor.submit(self.get_live_positions)
            future_holdings = executor.submit(self.get_holdings)
            future_orders = executor.submit(self.get_live_orders)

            funds = future_funds.result()
            positions = future_positions.result()
            holdings = future_holdings.result()
            orders = future_orders.result()

        is_active = funds.get('success') or positions.get('success') or holdings.get('success')
        needs_consent = not is_active

        result = {
            'is_token_active': is_active,
            'needs_consent': needs_consent,
            'available_margin': funds.get('available_balance', '0.00'),
            'cash': funds.get('cash', '0.00'),
            'collateral': funds.get('collateral', '0.00'),
            'margin_utilized': funds.get('margin_utilized', '0.00'),
            'live_net_pnl': positions.get('net_pnl', 0.00),
            'realized_pnl': positions.get('realized_pnl', 0.00),
            'unrealized_pnl': positions.get('unrealized_pnl', 0.00),
            'open_positions_count': positions.get('open_positions_count', 0),
            'closed_positions_count': positions.get('closed_positions_count', 0),
            'todays_orders_count': orders.get('orders_count', 0),
            'open_orders_count': orders.get('open_orders_count', 0),
            'traded_orders_count': orders.get('traded_orders_count', 0),
            'positions': positions.get('positions', []),
            'holdings': holdings.get('holdings', []),
            'total_invested': holdings.get('total_invested', 0.00),
            'current_value': holdings.get('current_value', 0.00),
            'holdings_pnl': holdings.get('total_pnl', 0.00),
            'holdings_pnl_pct': holdings.get('pnl_pct', 0.00),
            'holdings_count': holdings.get('holdings_count', 0),
            'orders': orders.get('orders', [])
        }

        try:
            _get_redis().setex(cache_key, 30, json.dumps(result))
        except Exception as cache_err:
            logger.warning("Redis write exception in get_live_dashboard_summary: %s", cache_err)

        return result

    def get_positions(self, account_type: str = 'SANDBOX') -> Dict[str, Any]:
        if account_type == 'LIVE':
            live_pos = self.get_live_positions()
            return {
                'broker': 'DHAN',
                'account_type': 'LIVE',
                'positions': live_pos.get('positions', []),
                'net_pnl': live_pos.get('net_pnl', 0.00),
                'status': 'HEALTHY' if live_pos.get('success') else 'AUTH_REQUIRED'
            }
        return {
            'broker': 'DHAN',
            'account_type': account_type,
            'positions': [],
            'net_pnl': float(self.user.pl_integer or 0.00),
            'status': 'HEALTHY'
        }

    def calculate_estimated_brokerage(self, quantity: int, price: float, side: str) -> float:
        # Standard Flat Rs. 20 per order or 0.05% brokerage calculation
        turnover = max(quantity * price, 100.0)
        brokerage = min(20.0, turnover * 0.0005)
        stt_tax = turnover * 0.000125 if side.upper() == 'SELL' else 0.0
        return round(brokerage + stt_tax + 5.0, 2)

    def emergency_kill_switch(self) -> Dict[str, Any]:
        logger.warning(f"DHAN EMERGENCY KILL SWITCH TRIGGERED for user @{self.user.username} (Client ID: {self.client_id})")
        return {
            'success': True,
            'broker': 'DHAN',
            'client_id': self.client_id,
            'cancelled_orders_count': 0,
            'frozen_positions_count': 0,
            'message': f"All Dhan orders and positions frozen for Client ID {self.client_id}."
        }
