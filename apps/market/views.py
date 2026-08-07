import json
from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, JsonResponse
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, DetailView, DeleteView, View
from apps.users.mixins import HTMXPartialMixin
from apps.admins.permissions import AdminRequiredMixin
from apps.common.mixins import HtmxMessageMixin, HtmxModalMixin
from .models import MarketBackupTask
from .forms import MarketBackupForm


class MarketBackupListView(HTMXPartialMixin, LoginRequiredMixin, AdminRequiredMixin, ListView):
    """
    Unified Market Backup Dashboard & List View.
    Handles full-page loads, HTMX partial requests, filtering, sorting, and pagination.
    """
    model = MarketBackupTask
    template_name = 'admins/backup_dashboard.html'
    partial_template_name = 'admins/partials/backup_dashboard_content.html'
    context_object_name = 'backups'
    paginate_by = settings.PAGINATION_COUNT

    def get_queryset(self):
        queryset = super().get_queryset().filter(is_deleted=False)

        # Search filter (by ID or index name)
        q = self.request.GET.get('q', '').strip()
        if q:
            queryset = queryset.filter(index_name__icontains=q) | queryset.filter(id__icontains=q)

        # Status filter
        status = self.request.GET.get('status', '').strip()
        if status:
            queryset = queryset.filter(status=status)

        # Sorting
        sort = self.request.GET.get('sort', '-created_at').strip()
        allowed_sort = ['created_at', '-created_at', 'index_name', '-index_name', 'status', '-status']
        if sort in allowed_sort:
            queryset = queryset.order_by(sort)
        else:
            queryset = queryset.order_by('-created_at')

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = "Market Backup Management"
        context['current_sort'] = self.request.GET.get('sort', '-created_at').strip()
        
        query_params = self.request.GET.copy()
        query_params.pop('page', None)
        query_params.pop('sort', None)
        context['current_filters'] = query_params.urlencode()
        return context


class MarketBackupCreateView(HtmxMessageMixin, LoginRequiredMixin, AdminRequiredMixin, CreateView):
    model = MarketBackupTask
    form_class = MarketBackupForm
    template_name = 'admins/backup_form.html'
    success_url = reverse_lazy('market:market_backup_list')
    success_message = "Market backup job initialized successfully."


class MarketBackupDetailView(LoginRequiredMixin, AdminRequiredMixin, DetailView):
    model = MarketBackupTask
    template_name = 'admins/backup_detail.html'
    context_object_name = 'backup'

    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


class MarketBackupControlView(LoginRequiredMixin, AdminRequiredMixin, View):
    """
    Handles live controls: start, pause, stop/cancel tasks communicating with the backend engine.
    """
    def post(self, request, pk, *args, **kwargs):
        task = MarketBackupTask.objects.filter(pk=pk, is_deleted=False).first()
        if not task:
            return JsonResponse({'error': 'Task not found'}, status=404)

        action = request.POST.get('action')
        if action == 'pause':
            task.status = MarketBackupTask.StatusChoices.PAUSED
        elif action == 'resume' or action == 'start':
            task.status = MarketBackupTask.StatusChoices.RUNNING
        elif action == 'cancel' or action == 'stop':
            task.status = MarketBackupTask.StatusChoices.CANCELLED
        
        task.save()

        response = HttpResponse()
        response['HX-Trigger'] = json.dumps({
            'showToast': {'message': f'Task status updated to {task.status.upper()}', 'level': 'success'},
            'reloadBackupTable': True
        })
        return response


class MarketBackupDeleteView(HtmxModalMixin, HtmxMessageMixin, LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    model = MarketBackupTask
    modal_template_name = 'admins/partials/confirm_delete.html'
    template_name = 'admins/partials/confirm_delete.html'
    success_message = "Market backup task deleted successfully."

    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.object.delete() # Triggers BaseModel soft delete

        response = HttpResponse()
        response['HX-Trigger'] = json.dumps({
            'closeGlobalModal': True,
            'showToast': {'message': str(self.success_message), 'level': 'success'},
            'reloadBackupTable': True
        })
        return response