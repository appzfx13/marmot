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
    """API endpoint for AI Copilot chat conversations with database persistence and Gemini inference."""

    def _get_session_id(self, request):
        """Resolve persistent session identifier for authenticated user or browser session."""
        if request.user.is_authenticated:
            return f"user_{request.user.id}"
        if not request.session.session_key:
            request.session.create()
        return f"anon_{request.session.session_key}"

    def get(self, request, *args, **kwargs):
        """Retrieve stored chat history from database."""
        from apps.common.models import AIChatMessage
        session_id = self._get_session_id(request)
        user = request.user if request.user.is_authenticated else None

        queryset = AIChatMessage.objects.filter(session_id=session_id)
        if user:
            queryset = queryset | AIChatMessage.objects.filter(user=user)

        messages = list(queryset.order_by('created_at').values('id', 'role', 'content', 'created_at'))
        
        formatted_history = []
        for msg in messages:
            formatted_history.append({
                "id": msg['id'],
                "role": msg['role'],
                "text": msg['content'],
                "created_at": msg['created_at'].isoformat() if msg.get('created_at') else None
            })

        return JsonResponse({"success": True, "history": formatted_history}, status=200)

    def post(self, request, *args, **kwargs):
        """Process user message via Gemini AI, store both user prompt and response in database."""
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

        session_id = self._get_session_id(request)
        user = request.user if request.user.is_authenticated else None

        # 1. Save user query to database
        from apps.common.models import AIChatMessage
        from apps.common.choices import AIChatRoleChoices
        
        user_chat_record = AIChatMessage.objects.create(
            user=user,
            session_id=session_id,
            role=AIChatRoleChoices.USER,
            content=message,
            created_by=user,
        )

        # 2. Invoke Gemini AI Service
        from apps.common.services.gemini_service import GeminiAIService
        result = GeminiAIService.generate_chat_response(message=message, history=history)

        # 3. If response generated successfully, persist AI response
        if result.get("success") and result.get("reply"):
            AIChatMessage.objects.create(
                user=user,
                session_id=session_id,
                role=AIChatRoleChoices.MODEL,
                content=result.get("reply"),
                model_name=result.get("model", "gemini-3.6-flash"),
                created_by=user,
            )

        return JsonResponse(result, status=200)

    def delete(self, request, *args, **kwargs):
        """Clear conversation history from database for the current user/session."""
        from apps.common.models import AIChatMessage
        session_id = self._get_session_id(request)
        user = request.user if request.user.is_authenticated else None

        queryset = AIChatMessage.objects.filter(session_id=session_id)
        if user:
            queryset = queryset | AIChatMessage.objects.filter(user=user)

        deleted_count = queryset.delete()
        return JsonResponse({"success": True, "message": "Chat history cleared.", "deleted": deleted_count[0] if deleted_count else 0}, status=200)

