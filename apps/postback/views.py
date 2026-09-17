import json
import redis
import time
from django.conf import settings
from django.http import JsonResponse
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

def push_webhook_to_stream(payload, user_id=None, broker_hint='dhan', ip_address=None, execution_mode='LIVE'):
    """Push the raw webhook to a Redis Stream for async worker processing."""
    try:
        r = redis.Redis.from_url(settings.REDIS_URL)
        stream_name = 'marmot:webhooks:stream'
        data = {
            'payload': json.dumps(payload),
            'user_id': str(user_id) if user_id else '',
            'broker_hint': str(broker_hint),
            'ip_address': str(ip_address) if ip_address else '',
            'execution_mode': str(execution_mode),
            'timestamp': str(time.time())
        }
        r.xadd(stream_name, data)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Failed to push webhook to Redis Stream: {e}")

@method_decorator(csrf_exempt, name='dispatch')
class DhanPostbackWebhookView(View):
    """
    Dedicated DhanHQ API v2 Webhook Postback Endpoint.
    Endpoints:
      POST /api/dhan/postback/
      POST /api/dhan/postback/<int:user_id>/
    """
    def post(self, request, user_id=None, *args, **kwargs):
        try:
            if request.body:
                payload = json.loads(request.body.decode('utf-8'))
            else:
                payload = request.POST.dict()
        except Exception:
            payload = {}

        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        ip_address = x_forwarded_for.split(',')[0].strip() if x_forwarded_for else request.META.get('REMOTE_ADDR')

        push_webhook_to_stream(payload, user_id=user_id, broker_hint='dhan', ip_address=ip_address, execution_mode='LIVE')

        return JsonResponse({
            "status": "success",
            "message": "DhanHQ Postback received and queued successfully"
        }, status=200)

    def get(self, request, *args, **kwargs):
        return JsonResponse({"status": "active", "broker": "DHAN", "message": "DhanHQ Postback Webhook endpoint ready."}, status=200)


@method_decorator(csrf_exempt, name='dispatch')
class GenericBrokerPostbackWebhookView(View):
    """
    Dynamic Multi-Broker Webhook Postback Endpoint.
    Endpoints:
      POST /api/<str:broker>/postback/
      POST /api/<str:broker>/postback/<int:user_id>/
    """
    def post(self, request, broker='dhan', user_id=None, *args, **kwargs):
        try:
            if request.body:
                payload = json.loads(request.body.decode('utf-8'))
            else:
                payload = request.POST.dict()
        except Exception:
            payload = {}

        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        ip_address = x_forwarded_for.split(',')[0].strip() if x_forwarded_for else request.META.get('REMOTE_ADDR')

        push_webhook_to_stream(payload, user_id=user_id, broker_hint=broker, ip_address=ip_address, execution_mode='LIVE')

        return JsonResponse({
            "status": "success",
            "message": f"{broker.upper()} Postback received and queued successfully"
        }, status=200)

    def get(self, request, broker='dhan', *args, **kwargs):
        return JsonResponse({"status": "active", "broker": broker.upper(), "message": f"{broker.upper()} Postback Webhook endpoint ready."}, status=200)


@method_decorator(csrf_exempt, name='dispatch')
class MockDhanPostbackWebhookView(View):
    """
    Dedicated Dhan Emulator Live Mock Webhook Postback Endpoint.
    Endpoints: POST /api/mock/dhan/postback/
    """
    def post(self, request, *args, **kwargs):
        try:
            if request.body:
                payload = json.loads(request.body.decode('utf-8'))
            else:
                payload = request.POST.dict()
        except Exception:
            payload = {}

        payload['execution_mode'] = 'MOCK'
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        ip_address = x_forwarded_for.split(',')[0].strip() if x_forwarded_for else request.META.get('REMOTE_ADDR')

        push_webhook_to_stream(payload, broker_hint='dhan', ip_address=ip_address, execution_mode='MOCK')

        return JsonResponse({
            "status": "success",
            "environment": "MOCK",
            "message": "Dhan Emulator Mock Postback received and queued successfully"
        }, status=200)

    def get(self, request, *args, **kwargs):
        return JsonResponse({
            "status": "active",
            "environment": "MOCK",
            "broker": "DHAN-EMULATOR",
            "message": "Mock Postback Webhook endpoint ready."
        }, status=200)

