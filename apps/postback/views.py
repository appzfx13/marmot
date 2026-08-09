import json
from django.http import JsonResponse
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from .services import PostbackService


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

        log = PostbackService.process_postback(
            payload=payload,
            user_id=user_id,
            broker_hint='dhan',
            ip_address=ip_address
        )

        return JsonResponse({
            "status": "success",
            "message": "DhanHQ Postback received and backed up successfully",
            "log_id": log.id,
            "order_id": log.order_id,
            "order_status": log.order_status,
            "client_id": log.broker_client_id
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

        log = PostbackService.process_postback(
            payload=payload,
            user_id=user_id,
            broker_hint=broker,
            ip_address=ip_address
        )

        return JsonResponse({
            "status": "success",
            "message": f"{broker.upper()} Postback received and backed up successfully",
            "log_id": log.id,
            "broker": log.broker,
            "order_id": log.order_id,
            "order_status": log.order_status
        }, status=200)

    def get(self, request, broker='dhan', *args, **kwargs):
        return JsonResponse({"status": "active", "broker": broker.upper(), "message": f"{broker.upper()} Postback Webhook endpoint ready."}, status=200)
