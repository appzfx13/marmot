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

        return {
            'broker': 'DHAN',
            'client_id': str(client_id) if client_id else None,
            'order_id': str(order_id) if order_id else None,
            'symbol': str(symbol) if symbol else None,
            'order_status': str(order_status).upper() if order_status else None,
            'transaction_type': str(transaction_type).upper() if transaction_type else None,
            'quantity': int(quantity) if quantity else 0,
            'price': float(price) if price else 0.0,
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
            # 1. Match User by broker_client_id
            target_user = User.objects.filter(broker_client_id=client_id).first()
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

        logger.info(f"Postback recorded: #{log.id} | Broker: {log.broker} | Order: {log.order_id} | User: {target_user}")
        return log
