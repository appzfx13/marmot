import io
import json
import os
import zipfile
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect, FileResponse, Http404
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
    success_message = "Market backup entry created successfully. Click 'Start' in the dashboard to begin download."

    def form_valid(self, form):
        # Override standard save to use our Service Layer
        # This creates the DB record AND fires the 'START' command to Redis
        token = form.cleaned_data.get('dhan_access_token', '').strip()
        self.object = create_and_start_backup_task(
            start_date=form.cleaned_data['start_date'],
            end_date=form.cleaned_data['end_date'],
            index_name=form.cleaned_data['index_name'],
            strike_count=form.cleaned_data['strike_count'],
            user=self.request.user,
            dhan_access_token=token if token else None
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


class MarketBackupChartView(LoginRequiredMixin, AdminRequiredMixin, View):
    """Renders full-screen TradingView Lightweight Chart terminal for a market backup dataset."""
    def get(self, request, pk, *args, **kwargs):
        task = MarketBackupTask.objects.filter(pk=pk, is_deleted=False).first()
        if not task:
            raise Http404("Market backup task not found.")

        ws_port = getattr(settings, 'WS_PORT', '8082')
        go_chart_api_url = f"http://localhost:{ws_port}/api/chart?task_id={task.id}"

        context = {
            'backup': task,
            'go_chart_api_url': go_chart_api_url,
            'page_title': f"{task.index_name} Interactive Option Chart - Backup #{task.id}",
        }
        return render(request, 'admins/market_chart.html', context)



class MarketBackupDownloadView(LoginRequiredMixin, AdminRequiredMixin, View):
    """Packs date-partitioned Parquet datasets into a ZIP archive and streams it to the user."""
    def get(self, request, pk, *args, **kwargs):
        task = MarketBackupTask.objects.filter(pk=pk, is_deleted=False).first()
        if not task:
            raise Http404("Market backup task not found.")

        user_id = str(task.created_by.id if getattr(task, 'created_by', None) else 1)
        backup_id = str(task.id)
        index_name = task.index_name.lower()

        candidate_paths = [
            task.parquet_file_path,
            os.path.join(settings.BASE_DIR, 'backup', user_id, backup_id),
            os.path.join('/app', 'backup', user_id, backup_id),
            os.path.join(settings.BASE_DIR, 'go-app', 'data', 'users', user_id, f"{index_name}_options"),
        ]

        target_path = None
        for p in candidate_paths:
            if p and os.path.exists(p):
                target_path = p
                break

        if not target_path:
            raise Http404("Backup data directory or file not found on disk.")

        zip_buffer = io.BytesIO()
        zip_filename = f"{index_name}_backup_task_{task.id}.zip"

        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            if os.path.isdir(target_path):
                for root, _, files in os.walk(target_path):
                    for file in files:
                        full_path = os.path.join(root, file)
                        rel_path = os.path.relpath(full_path, target_path)
                        zip_file.write(full_path, arcname=rel_path)
            else:
                zip_file.write(target_path, arcname=os.path.basename(target_path))

        zip_buffer.seek(0)
        return FileResponse(zip_buffer, as_attachment=True, filename=zip_filename)


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


class MarketBackupBulkDeleteView(LoginRequiredMixin, AdminRequiredMixin, View):
    """CBV for bulk soft-deletion of market backup tasks via HTMX."""
    def get(self, request, *args, **kwargs):
        ids_raw = request.GET.get('ids', '')
        ids_list = [i.strip() for i in ids_raw.split(',') if i.strip().isdigit()]
        count = len(ids_list)
        context = {
            'count': count,
            'ids_str': ','.join(ids_list),
            'item_name': 'backup entry' if count == 1 else 'backup entries',
            'post_url': reverse_lazy('market:market_backup_bulk_delete'),
        }
        return render(request, 'admins/partials/confirm_bulk_delete.html', context)

    def post(self, request, *args, **kwargs):
        ids_raw = request.POST.get('ids', '')
        ids_list = [int(i.strip()) for i in ids_raw.split(',') if i.strip().isdigit()]
        if ids_list:
            qs = MarketBackupTask.objects.filter(id__in=ids_list, is_deleted=False)
            count = qs.count()
            qs.update(is_deleted=True)
            msg = f"Successfully deleted {count} market backup{'s' if count != 1 else ''}."
        else:
            msg = "No valid backup entries selected."
            count = 0

        response = HttpResponse()
        response['HX-Trigger'] = json.dumps({
            'closeGlobalModal': True,
            'showToast': {'message': msg, 'level': 'success' if count > 0 else 'warning'},
            'reloadBackupTable': True
        })
        return response


