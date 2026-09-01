import json
from django.http import JsonResponse
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import get_user_model
from apps.common.models import PostbackLog

User = get_user_model()

@method_decorator(csrf_exempt, name='dispatch')
class PostbackWebhookView(View):
    """
    User-Wise Postback Webhook Handler.
    Receives incoming webhook payloads from broker APIs (e.g., DhanHQ, Fyers),
    parses order signals, and stores raw payloads in PostbackLog database model.
    Endpoints:
      POST /api/postback/
      POST /api/postback/<int:user_id>/
    """
    def post(self, request, user_id=None, *args, **kwargs):
        try:
            if request.body:
                payload = json.loads(request.body.decode('utf-8'))
            else:
                payload = request.POST.dict()
        except Exception:
            payload = {}

        # Parse DhanHQ & general broker postback fields
        dhan_client_id = (
            payload.get('dhanClientId') or 
            payload.get('clientId') or 
            payload.get('client_id') or 
            payload.get('userId') or
            payload.get('user_id')
        )
        order_id = payload.get('orderId') or payload.get('order_id') or payload.get('id')
        symbol = payload.get('tradingSymbol') or payload.get('symbol') or payload.get('securityId')
        order_status = payload.get('orderStatus') or payload.get('status') or payload.get('order_status')
        transaction_type = payload.get('transactionType') or payload.get('txn_type') or payload.get('transaction_type')
        quantity = payload.get('quantity') or payload.get('qty', 0)
        price = payload.get('price') or payload.get('tradedPrice', 0.0)
        broker = payload.get('broker', 'DHAN').upper()

        # Resolve associated user via user_id parameter OR dhanClientId payload matching
        target_user = None
        if user_id:
            target_user = User.objects.filter(pk=user_id).first()

        if not target_user and dhan_client_id:
            # 1. Match User by dhan_client_id field
            target_user = User.objects.filter(dhan_client_id=str(dhan_client_id)).first()
            # 2. Fallback match User by username
            if not target_user:
                target_user = User.objects.filter(username=str(dhan_client_id)).first()

        # Extract Client IP Address
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip_address = x_forwarded_for.split(',')[0].strip()
        else:
            ip_address = request.META.get('REMOTE_ADDR')

        # Record Postback Log
        log = PostbackLog.objects.create(
            user=target_user,
            broker=broker,
            dhan_client_id=str(dhan_client_id) if dhan_client_id else None,
            order_id=str(order_id) if order_id else None,
            symbol=str(symbol) if symbol else None,
            order_status=str(order_status).upper() if order_status else None,
            transaction_type=str(transaction_type).upper() if transaction_type else None,
            quantity=int(quantity) if quantity else 0,
            price=float(price) if price else 0.0,
            payload=payload,
            ip_address=ip_address
        )

        return JsonResponse({
            "status": "success",
            "message": "Postback received and recorded for backup",
            "log_id": log.id,
            "order_id": log.order_id,
            "order_status": log.order_status
        }, status=200)

    def get(self, request, *args, **kwargs):
        return JsonResponse({"status": "active", "message": "Postback webhook endpoint is ready for POST requests."}, status=200)


@method_decorator(csrf_exempt, name='dispatch')
class AIChatAPIView(View):
    """API endpoint for AI Copilot chat conversations powered by Google Gemini."""

    def post(self, request, *args, **kwargs):
        try:
            if request.body:
                payload = json.loads(request.body.decode('utf-8'))
            else:
                payload = request.POST.dict()
        except Exception:
            payload = {}

        message = (payload.get('message') or '').strip()
        history = payload.get('history') or []

        if not message:
            return JsonResponse({"success": False, "error": "Message prompt cannot be empty."}, status=400)

        from apps.common.services.gemini_service import GeminiAIService
        result = GeminiAIService.generate_chat_response(message=message, history=history)
        return JsonResponse(result, status=200)
