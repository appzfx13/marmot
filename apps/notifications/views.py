from django.views import View
from django.http import JsonResponse
from django.contrib.auth.mixins import LoginRequiredMixin
from .models import Notification

class LiveNotificationsView(LoginRequiredMixin, View):
    """CBV for live notification retrieval and status updates."""

    def get(self, request, *args, **kwargs):
        notifications_qs = Notification.objects.filter(user=request.user).order_by('-created_at')[:10]
        unread_count = Notification.objects.filter(user=request.user, is_read=False).count()

        notifications_data = [
            {
                'id': notif.id,
                'title': notif.title,
                'message': notif.message,
                'is_read': notif.is_read,
                'created_at': notif.created_at.isoformat(),
                'sender': notif.sender.username if notif.sender else 'System',
                'type': notif.notification_type,
            }
            for notif in notifications_qs
        ]

        return JsonResponse({
            'unread_count': unread_count,
            'notifications': notifications_data,
        })

    def post(self, request, *args, **kwargs):
        mark_all = request.POST.get('mark_all')
        notification_id = request.POST.get('notification_id')

        if mark_all == 'true':
            Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
            return JsonResponse({'status': 'success', 'message': 'All notifications marked as read'})

        if notification_id:
            Notification.objects.filter(id=notification_id, user=request.user).update(is_read=True)
            return JsonResponse({'status': 'success', 'message': 'Notification marked as read'})

        return JsonResponse({'status': 'error', 'message': 'Invalid parameters'}, status=400)