import json
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, DetailView, DeleteView, View

from apps.users.mixins import HTMXPartialMixin
from apps.admins.permissions import AdminRequiredMixin
from apps.common.mixins import HtmxMessageMixin, HtmxModalMixin

from .models import MarketBackupTask
from .forms import MarketBackupForm
from .services import create_and_start_backup_task, send_control_command


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
        context['ws_url'] = settings.MARMOT_WS_URL
        
        query_params = self.request.GET.copy()
        query_params.pop('page', None)
        query_params.pop('sort', None)
        context['current_filters'] = query_params.urlencode()
        
        backups = context.get('backups')
        if backups is not None:
            context['has_active_tasks'] = any(b.status in ['running', 'pending'] for b in backups)
        else:
            context['has_active_tasks'] = False
        return context


class MarketBackupCreateView(HtmxMessageMixin, LoginRequiredMixin, AdminRequiredMixin, CreateView):
    model = MarketBackupTask
    form_class = MarketBackupForm
    template_name = 'admins/backup_form.html'
    success_url = reverse_lazy('market:market_backup_list')
    success_message = "Market backup job initialized successfully. Engine is starting..."

    def form_valid(self, form):
        # Override standard save to use our Service Layer
        # This creates the DB record AND fires the 'START' command to Redis
        self.object = create_and_start_backup_task(
            start_date=form.cleaned_data['start_date'],
            end_date=form.cleaned_data['end_date'],
            index_name=form.cleaned_data['index_name'],
            strike_count=form.cleaned_data['strike_count'],
            user=self.request.user
        )
        
        # Add success message and redirect back to the dashboard
        messages.success(self.request, self.success_message)
        return HttpResponseRedirect(self.get_success_url())


class MarketBackupDetailView(HTMXPartialMixin, LoginRequiredMixin, AdminRequiredMixin, DetailView):
    model = MarketBackupTask
    template_name = 'admins/backup_detail.html'
    partial_template_name = 'admins/partials/backup_detail_content.html'
    context_object_name = 'backup'

    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['ws_url'] = settings.MARMOT_WS_URL
        return context


class MarketBackupControlView(LoginRequiredMixin, AdminRequiredMixin, View):
    """
    Handles live controls: start, pause, stop/cancel tasks by pushing commands to the Go Engine via Redis.
    GET  → serves the confirmation modal partial (for pause/stop actions).
    POST → dispatches the command to the Go Engine via Redis.
    """
    def get(self, request, pk, *args, **kwargs):
        """Serve the confirmation modal partial for destructive actions (pause / stop)."""
        task = MarketBackupTask.objects.filter(pk=pk, is_deleted=False).first()
        if not task:
            return HttpResponse('Task not found', status=404)

        action = request.GET.get('action', 'stop').lower()
        return render(request, 'admins/partials/backup_control_confirm.html', {
            'backup': task,
            'action': action,
        })

    def post(self, request, pk, *args, **kwargs):
        task = MarketBackupTask.objects.filter(pk=pk, is_deleted=False).first()
        if not task:
            return JsonResponse({'error': 'Task not found'}, status=404)

        # Get the requested action from HTMX/Frontend
        action = request.POST.get('action', '').upper()
        
        # Map frontend actions to Go Engine commands
        command_map = {
            'PAUSE': 'PAUSE',
            'RESUME': 'RESUME',
            'START': 'RESUME',
            'CANCEL': 'CANCEL',
            'STOP': 'CANCEL'
        }
        
        command = command_map.get(action)
        
        if command:
            try:
                # Dispatch the command through the Service Layer
                send_control_command(task.id, command)
                
                # Setup UI response
                msg = f'Task command {command} sent to engine.'
                level = 'success'
            except Exception as e:
                msg = f'Error communicating with engine: {str(e)}'
                level = 'error'
        else:
            msg = 'Invalid control action requested.'
            level = 'error'

        # Return 204 No Content so HTMX does not wipe the UI.
        # Fire both table and detail-page reload triggers so whichever is present updates.
        # closeGlobalModal dismisses the confirmation modal (pause/stop flow).
        response = HttpResponse(status=204)
        response['HX-Trigger'] = json.dumps({
            'showToast': {'message': msg, 'level': level},
            'closeGlobalModal': True,
            'reloadBackupTable': True,
            'reloadBackupDetail': True,
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
        
        # Optional: If you want deleting a running task to cancel it in Go Engine first
        if self.object.status in [MarketBackupTask.StatusChoices.RUNNING, MarketBackupTask.StatusChoices.PENDING]:
             send_control_command(self.object.id, 'CANCEL')

        # Triggers BaseModel soft delete
        self.object.delete() 

        # FIX: Ensure HTMX processes triggers without wiping layout during a standard form POST delete
        response = HttpResponse(status=204)
        response['HX-Trigger'] = json.dumps({
            'closeGlobalModal': True,
            'showToast': {'message': str(self.success_message), 'level': 'success'},
            'reloadBackupTable': True
        })
        return response

