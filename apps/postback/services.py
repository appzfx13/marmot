import logging
from django.contrib.auth import get_user_model
from apps.common.models import PostbackLog

logger = logging.getLogger(__name__)
User = get_user_model()


class DhanPostbackParser:
    """Parser specifically tailored for DhanHQ API v2 Webhook Postback notifications."""
    @staticmethod
    def parse(payload):
        client_id = (
            payload.get('dhanClientId') or 
            payload.get('clientId') or 
            payload.get('client_id')
        )
        order_id = payload.get('orderId') or payload.get('order_id')
        symbol = payload.get('tradingSymbol') or payload.get('symbol') or payload.get('securityId')
        order_status = payload.get('orderStatus') or payload.get('status')
        transaction_type = payload.get('transactionType') or payload.get('txn_type')
        quantity = payload.get('quantity') or payload.get('qty', 0)
        price = payload.get('price') or payload.get('tradedPrice', 0.0)
        leg_name = payload.get('legName') or payload.get('leg_name')
        rejection_reason = payload.get('rejectionReason') or payload.get('rejection_reason') or payload.get('reason')
        exit_reason = None
        if leg_name in ('SL_HIT', 'TP_HIT'):
            exit_reason = leg_name
        elif rejection_reason and 'SL_HIT' in str(rejection_reason):
            exit_reason = 'SL_HIT'
        elif rejection_reason and 'TP_HIT' in str(rejection_reason):
            exit_reason = 'TP_HIT'

        return {
            'broker': 'DHAN',
            'client_id': str(client_id) if client_id else None,
            'order_id': str(order_id) if order_id else None,
            'symbol': str(symbol) if symbol else None,
            'order_status': str(order_status).upper() if order_status else None,
            'transaction_type': str(transaction_type).upper() if transaction_type else None,
            'quantity': int(quantity) if quantity else 0,
            'price': float(price) if price else 0.0,
            'leg_name': str(leg_name) if leg_name else None,
            'exit_reason': exit_reason,
            'rejection_reason': str(rejection_reason) if rejection_reason else None,
        }


class FyersPostbackParser:
    """Parser specifically tailored for FYERS Webhook Postback notifications."""
    @staticmethod
    def parse(payload):
        client_id = payload.get('fyToken') or payload.get('client_id') or payload.get('id')
        order_id = payload.get('id') or payload.get('order_id')
        symbol = payload.get('symbol')
        order_status = payload.get('status')
        transaction_type = payload.get('txn_type') or payload.get('transaction_type')
        quantity = payload.get('qty', 0)
        price = payload.get('tradedPrice', 0.0)

        return {
            'broker': 'FYERS',
            'client_id': str(client_id) if client_id else None,
            'order_id': str(order_id) if order_id else None,
            'symbol': str(symbol) if symbol else None,
            'order_status': str(order_status).upper() if order_status else None,
            'transaction_type': str(transaction_type).upper() if transaction_type else None,
            'quantity': int(quantity) if quantity else 0,
            'price': float(price) if price else 0.0,
        }


class GenericBrokerPostbackParser:
    """Fallback parser for any generic broker postback payload."""
    @staticmethod
    def parse(payload, default_broker='DHAN'):
        client_id = (
            payload.get('dhanClientId') or 
            payload.get('clientId') or 
            payload.get('client_id') or 
            payload.get('user_id')
        )
        order_id = payload.get('orderId') or payload.get('order_id') or payload.get('id')
        symbol = payload.get('tradingSymbol') or payload.get('symbol')
        order_status = payload.get('orderStatus') or payload.get('status') or payload.get('order_status')
        transaction_type = payload.get('transactionType') or payload.get('txn_type') or payload.get('transaction_type')
        quantity = payload.get('quantity') or payload.get('qty', 0)
        price = payload.get('price') or payload.get('tradedPrice', 0.0)
        broker_name = payload.get('broker', default_broker).upper()

        return {
            'broker': broker_name,
            'client_id': str(client_id) if client_id else None,
            'order_id': str(order_id) if order_id else None,
            'symbol': str(symbol) if symbol else None,
            'order_status': str(order_status).upper() if order_status else None,
            'transaction_type': str(transaction_type).upper() if transaction_type else None,
            'quantity': int(quantity) if quantity else 0,
            'price': float(price) if price else 0.0,
        }


PARSERS = {
    'dhan': DhanPostbackParser,
    'fyers': FyersPostbackParser,
}


class PostbackService:
    """Central processing service for receiving, parsing, auto-resolving users, and logging postbacks."""

    @classmethod
    def process_postback(cls, payload, user_id=None, broker_hint='dhan', ip_address=None):
        broker_hint = str(broker_hint).lower()
        parser_cls = PARSERS.get(broker_hint, GenericBrokerPostbackParser)
        parsed = parser_cls.parse(payload)

        # User Resolution Logic
        target_user = None
        if user_id:
            target_user = User.objects.filter(pk=user_id).first()

        client_id = parsed.get('client_id')
        if not target_user and client_id:
            # 1. Match User via linked UserTradingAccount
            target_user = User.objects.filter(trading_accounts__broker_client_id=client_id).first()
            # 2. Match User by username
            if not target_user:
                target_user = User.objects.filter(username=client_id).first()

        # Record Postback Log in Database
        log = PostbackLog.objects.create(
            user=target_user,
            broker=parsed.get('broker', broker_hint.upper()),
            broker_client_id=client_id,
            order_id=parsed.get('order_id'),
            symbol=parsed.get('symbol'),
            order_status=parsed.get('order_status'),
            transaction_type=parsed.get('transaction_type'),
            quantity=parsed.get('quantity', 0),
            price=parsed.get('price', 0.0),
            payload=payload,
            ip_address=ip_address
        )

        exit_reason = parsed.get('exit_reason')
        if target_user and exit_reason:
            try:
                from apps.trade_config.models import TradeExecConfig
                active_configs = TradeExecConfig.objects.filter(admins_user=target_user, is_active=True, is_deleted=False)
                for config in active_configs:
                    remarks = f"Order #{log.order_id} ({log.symbol}) exited via {exit_reason} at {log.price}."
                    config.execution_remarks = remarks
                    if not isinstance(config.api_response_log, dict):
                        config.api_response_log = {}
                    config.api_response_log['last_exit_trigger'] = exit_reason
                    config.api_response_log['last_exit_order_id'] = log.order_id
                    config.api_response_log['last_exit_price'] = log.price
                    config.save(update_fields=['execution_remarks', 'api_response_log', 'updated_at'])
            except Exception as e:
                logger.warning(f"Failed to update TradeExecConfig on postback: {e}")

        try:
            import json
            import redis
            from django.conf import settings
            r = redis.Redis.from_url(settings.REDIS_URL)
            event_payload = json.dumps({
                'type': 'broker_order_postback',
                'order_id': log.order_id,
                'symbol': log.symbol,
                'status': log.order_status,
                'transaction_type': log.transaction_type,
                'price': log.price,
                'quantity': log.quantity,
                'leg_name': parsed.get('leg_name', ''),
                'exit_reason': exit_reason or '',
            })
            r.publish('marmot:broker:order_events', event_payload)
        except Exception:
            pass

        logger.info(f"Postback recorded: #{log.id} | Broker: {log.broker} | Order: {log.order_id} | Exit: {exit_reason} | User: {target_user}")
        return log


class MockBrokerPnLService:
    """Pairs BUY/SELL PostbackLog entries from the mock broker to compute per-trade PnL and session metrics."""

    BROKERAGE_PER_LEG = 20.0  # ₹20 per executed leg (Dhan flat fee)

    @classmethod
    def _get_base_qs(cls, user=None):
        """Returns TRADED mock postback logs ordered oldest-first."""
        from apps.common.models import PostbackLog
        qs = PostbackLog.objects.filter(order_status='TRADED', payload__execution_mode='MOCK').order_by('created_at')
        if user is not None:
            qs = qs.filter(user=user)
        return qs

    @classmethod
    def get_session_trades(cls, user=None):
        """Pairs BUY/SELL legs by correlationId. Returns list of closed trade dicts."""
        logs = list(cls._get_base_qs(user))
        buckets = {}
        for log in logs:
            payload = log.payload or {}
            corr = payload.get('correlationId') or payload.get('correlation_id') or ''
            security_id = payload.get('securityId') or payload.get('security_id') or ''
            sym = log.symbol or payload.get('tradingSymbol') or ''
            key = (security_id or corr or sym).upper().replace(' ', '_').strip()
            buckets.setdefault(key, []).append(log)

        trades = []
        for key, legs in buckets.items():
            buys = [l for l in legs if (l.transaction_type or '').upper() == 'BUY']
            sells = [l for l in legs if (l.transaction_type or '').upper() == 'SELL']
            while buys and sells:
                buy_leg = buys.pop(0)
                sell_leg = sells.pop(0)
                buy_payload = buy_leg.payload or {}
                sell_payload = sell_leg.payload or {}
                qty = max(buy_leg.quantity or 0, sell_leg.quantity or 0)
                entry_price = float(buy_payload.get('tradedPrice') or buy_leg.price or 0)
                exit_price = float(sell_payload.get('tradedPrice') or sell_leg.price or 0)
                gross_pnl = (exit_price - entry_price) * qty
                charges = cls.BROKERAGE_PER_LEG * 2
                net_pnl = gross_pnl - charges
                leg_name = sell_payload.get('legName') or sell_payload.get('leg_name') or ''
                exit_reason = leg_name if leg_name in ('SL_HIT', 'TP_HIT') else 'SQUAREOFF'
                entry_dt = buy_leg.created_at
                exit_dt = sell_leg.created_at
                duration_secs = int((exit_dt - entry_dt).total_seconds()) if exit_dt and entry_dt else 0
                trades.append({
                    'symbol': buy_leg.symbol or sell_leg.symbol or '',
                    'entry_price': round(entry_price, 2),
                    'exit_price': round(exit_price, 2),
                    'qty': qty,
                    'gross_pnl': round(gross_pnl, 2),
                    'charges': round(charges, 2),
                    'net_pnl': round(net_pnl, 2),
                    'exit_reason': exit_reason,
                    'entry_time': entry_dt,
                    'exit_time': exit_dt,
                    'trade_date': entry_dt.date() if entry_dt else None,
                    'duration_secs': duration_secs,
                    'is_winner': net_pnl > 0,
                })
        trades.sort(key=lambda t: t['entry_time'] or '', reverse=True)
        return trades

    @classmethod
    def get_daily_pnl_map(cls, user=None):
        """Returns {date_str: pnl_float} for calendar heatmap coloring."""
        trades = cls.get_session_trades(user)
        daily = {}
        for t in trades:
            if t['trade_date']:
                key = t['trade_date'].strftime('%Y-%m-%d')
                daily[key] = round(daily.get(key, 0.0) + t['net_pnl'], 2)
        return daily

    @classmethod
    def get_session_metrics(cls, user=None):
        """Returns full session performance dict with equity curve."""
        trades = cls.get_session_trades(user)
        if not trades:
            return {
                'total_trades': 0, 'winning_trades': 0, 'losing_trades': 0,
                'win_rate': 0.0, 'gross_pnl': 0.0, 'net_pnl': 0.0,
                'total_charges': 0.0, 'max_drawdown': 0.0, 'profit_factor': 0.0,
                'avg_win': 0.0, 'avg_loss': 0.0, 'equity_curve': [],
            }
        trades_asc = sorted(trades, key=lambda t: t['entry_time'] or '')
        gross_profit = sum(t['gross_pnl'] for t in trades_asc if t['gross_pnl'] > 0)
        gross_loss = abs(sum(t['gross_pnl'] for t in trades_asc if t['gross_pnl'] < 0))
        net_pnl = sum(t['net_pnl'] for t in trades_asc)
        total_charges = sum(t['charges'] for t in trades_asc)
        winners = [t for t in trades_asc if t['is_winner']]
        losers = [t for t in trades_asc if not t['is_winner']]
        peak = 0.0
        running = 0.0
        max_dd = 0.0
        equity_curve = []
        for t in trades_asc:
            running += t['net_pnl']
            if running > peak:
                peak = running
            dd = peak - running
            if dd > max_dd:
                max_dd = dd
            equity_curve.append({
                'label': t['exit_time'].strftime('%d %b %H:%M') if t['exit_time'] else '',
                'equity': round(running, 2),
                'pnl': t['net_pnl'],
                'symbol': t['symbol'],
                'exit_reason': t['exit_reason'],
            })
        return {
            'total_trades': len(trades),
            'winning_trades': len(winners),
            'losing_trades': len(losers),
            'win_rate': round(len(winners) / len(trades) * 100, 1) if trades else 0.0,
            'gross_pnl': round(gross_profit - gross_loss, 2),
            'net_pnl': round(net_pnl, 2),
            'total_charges': round(total_charges, 2),
            'max_drawdown': round(max_dd, 2),
            'profit_factor': round(gross_profit / gross_loss, 2) if gross_loss > 0 else 0.0,
            'avg_win': round(sum(t['net_pnl'] for t in winners) / len(winners), 2) if winners else 0.0,
            'avg_loss': round(sum(t['net_pnl'] for t in losers) / len(losers), 2) if losers else 0.0,
            'equity_curve': equity_curve,
        }

