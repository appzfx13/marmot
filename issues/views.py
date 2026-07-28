from django.db.models import Q
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import ListView, DetailView, CreateView, UpdateView
from issues.choices import IssueEnvironmentChoices, IssuePriorityChoices, IssueStatusChoices, IssueTypeChoices, TeamMemberRoleChoices
from django.db.models import Q, Count
from django.views.generic import ListView
from django.contrib.auth.mixins import LoginRequiredMixin
from .models import Issue
from django.contrib.auth import get_user_model
from .forms import ProjectForm, IssueForm, IssueRemarkLogForm
from .models import IssueRemarkLog, Project, Issue
from .forms import TagForm
from .models import Tag
from django.db.models import Q
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView
from django.utils import timezone
from datetime import timedelta
from django.db.models import Count, Q
from django.views.generic import DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from .models import Project, Issue
from .models import Issue
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import DetailView
from .models import Project, IssueStatusChoices


class ProjectListView(LoginRequiredMixin, ListView):
    model = Project
    template_name = 'issues/project_list.html'
    context_object_name = 'projects'

    def get_queryset(self):
        return Project.objects.select_related('owner', 'team').all()


from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import DetailView
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta
from issues.models import Project  # Adjust import paths based on your architecture
from issues.choices import IssueStatusChoices, IssuePriorityChoices, IssueTypeChoices

class ProjectDetailView(LoginRequiredMixin, DetailView):
    model = Project
    template_name = 'issues/project_detail.html'
    context_object_name = 'project'

    def get_queryset(self):
        return Project.objects.select_related('owner')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        project = self.object
        
        # 1. Period & Status Filtering Query Parameter Reading
        period = self.request.GET.get('period', 'all')
        current_status = self.request.GET.get('status', '')  # Dynamic Status Metric Filter Hook
        now = timezone.now()
        
        issues_qs = project.issues.select_related(
            'assignee', 'reporter', 'assignee__team_member', 'reporter__team_member'
        )

        # Apply Period Constraints
        if period == 'daily':
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
            issues_qs = issues_qs.filter(created_at__gte=start_date)
        elif period == 'weekly':
            start_date = now - timedelta(days=7)
            issues_qs = issues_qs.filter(created_at__gte=start_date)

        # 2. Dynamic Status Annotation Helper
        status_choices = IssueStatusChoices.choices
        status_annotations = {
            f"{status.lower()}_count": Count('id', filter=Q(status=status)) 
            for status, label in status_choices
        }
        
        # Calculate overall metrics before applying specific page filters to recent streams
        aggregated_metrics = issues_qs.aggregate(
            total=Count('id'), 
            high_priority=Count('id', filter=Q(priority__in=['high', 'critical'])), 
            **status_annotations
        )

        # 3. Apply Card Status Click Filtering Rule to Recent Stream
        if current_status:
            filtered_qs = issues_qs.filter(status=current_status)
        else:
            filtered_qs = issues_qs

        # 4. Developer Summary (Grouped by Assignee)
        dev_summary_qs = issues_qs.values(
            'assignee__username', 'assignee__id', 'assignee__first_name', 'assignee__last_name'
        ).annotate(
            total=Count('id'),
            high_priority=Count(
                'id', 
                filter=Q(priority__in=['high', 'critical']) & ~Q(status__in=['done', 'closed', 'ready_for_qa', 'qa_in_progress', 'rejected'])
            ),
            **status_annotations
        ).filter(
            Q(assignee__team_member__role='developer') | Q(assignee__team_member__role__isnull=True)
        ).exclude(assignee__team_member__role='qa').order_by('-total')

        # 5. QA Summary (Grouped by Reporter)
        qa_summary_qs = issues_qs.values(
            'reporter__username', 'reporter__id', 'reporter__first_name', 'reporter__last_name'
        ).annotate(
            total=Count('id'),
            high_priority=Count(
                'id', 
                filter=Q(priority__in=['high', 'critical'], status='ready_for_qa')
            ),
            **status_annotations
        ).filter(reporter__team_member__role='qa').order_by('-total')

        # 6. Summary Pipeline Transformation Logic
        def process_summary(summary_qs, user_prefix, is_qa=False):
            processed = []
            for entry in summary_qs:
                u_id = entry.get(f'{user_prefix}__id')
                if not u_id: continue

                if is_qa:
                    entry['pending_label'] = "Ready for QA (High/Critical)"
                    entry['total_pending_all_time'] = project.issues.filter(reporter_id=u_id, status='ready_for_qa').count()
                else:
                    entry['pending_label'] = "Total Workload (High/Critical)"
                    entry['total_pending_all_time'] = project.issues.filter(assignee_id=u_id).exclude(
                        status__in=['done', 'closed', 'ready_for_qa', 'qa_in_progress', 'rejected']
                    ).count()

                first = entry.get(f'{user_prefix}__first_name')
                last = entry.get(f'{user_prefix}__last_name')
                entry['full_display_name'] = f"{first} {last}" if first and last else (first or entry.get(f'{user_prefix}__username'))
                
                entry['status_counts_list'] = [
                    {'label': label, 'count': entry.get(f"{status.lower()}_count", 0), 'slug': status.lower()}
                    for status, label in status_choices
                ]
                processed.append(entry)
            return processed

        # Rebuild layout payload mapping array to handle hyperlinked interface triggers safely
        dynamic_status_cards = []
        for slug, label in status_choices:
            count_key = f"{slug.lower()}_count"
            dynamic_status_cards.append({
                'label': label.upper(),
                'count': aggregated_metrics.get(count_key, 0),
                'slug': slug.lower()
            })

        # Safe python-side replacement mapping to clear template errors
        current_status_display = current_status.replace('_', ' ').title() if current_status else ''

        context.update({
            'dev_summary': process_summary(dev_summary_qs, 'assignee', is_qa=False),
            'qa_summary': process_summary(qa_summary_qs, 'reporter', is_qa=True),
            'issues': filtered_qs.order_by('-created_at')[:10],
            'metrics': aggregated_metrics,
            'dynamic_status_cards': dynamic_status_cards,
            'current_period': period,
            'current_status': current_status,  
            'current_status_display': current_status_display, # Safe display string
            'status_choices': status_choices,
            'IssueStatusChoices': IssueStatusChoices,
            'IssuePriorityChoices': IssuePriorityChoices,
            'IssueTypeChoices': IssueTypeChoices,
        })
        return context

class ProjectCreateView(LoginRequiredMixin, CreateView):
    model = Project
    form_class = ProjectForm
    template_name = 'issues/project_form.html'

    def form_valid(self, form):
        project = form.save(commit=False)
        project.created_by = self.request.user
        project.save()
        return redirect('issues:project_detail', pk=project.pk)


class ProjectUpdateView(LoginRequiredMixin, UpdateView):
    model = Project
    form_class = ProjectForm
    template_name = 'issues/project_form.html'
    context_object_name = 'project'

    def form_valid(self, form):
        project = form.save()
        return redirect('issues:project_detail', pk=project.pk)
    
from django.db.models import Q
from django.contrib.auth import get_user_model
from django.views.generic import ListView
from django.contrib.auth.mixins import LoginRequiredMixin
from .models import Issue, Project, IssueStatusChoices, IssuePriorityChoices, IssueEnvironmentChoices, IssueTypeChoices

class IssueListView(LoginRequiredMixin, ListView):
    model = Issue
    template_name = 'issues/issue_list.html'
    context_object_name = 'issues'
    paginate_by = 50  # Limit to 50 items per page

    def get_queryset(self):
        # Prefetch co_assignees to avoid N+1 query overhead in operational grid views
        qs = Issue.objects.select_related('project', 'assignee', 'reporter', 'related_issue').prefetch_related('tags', 'co_assignees')

        search = self.request.GET.get('q', '').strip()
        if search:
            query = (
                Q(title__icontains=search)
                | Q(description__icontains=search)
                | Q(project__name__icontains=search)
                | Q(assignee__username__icontains=search)
                | Q(reporter__username__icontains=search)
                | Q(tags__name__icontains=search)
            )

            if "-" in search:
                parts = search.split("-")
                prefix = parts[0]
                suffix = parts[1]
                if suffix.isdigit():
                    query |= Q(project__code__iexact=prefix, pk=suffix)

            clean_id = search.replace('#', '')
            if clean_id.isdigit():
                query |= Q(pk=clean_id)

            qs = qs.filter(query).distinct()

        # Status filtering
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)

        priority = self.request.GET.get('priority')
        if priority:
            qs = qs.filter(priority=priority)

        issue_type = self.request.GET.get('issue_type')
        if issue_type:
            qs = qs.filter(issue_type=issue_type)

        project_id = self.request.GET.get('project')
        if project_id:  
            qs = qs.filter(project_id=project_id)

        environment = self.request.GET.get('environment')
        if environment:
            qs = qs.filter(environment=environment)

        source = self.request.GET.get('source')
        if source == 'MINE':
            qs = qs.filter(Q(assignee=self.request.user) | Q(reporter=self.request.user) | Q(co_assignees=self.request.user))

        assignee_id = self.request.GET.get('assignee')
        if assignee_id:
            if assignee_id == 'me':
                qs = qs.filter(assignee=self.request.user)
            else:
                qs = qs.filter(assignee_id=assignee_id)

        # Handle Co-Assignee Query Filtering
        co_assignee_id = self.request.GET.get('co_assignee')
        if co_assignee_id:
            if co_assignee_id == 'me':
                qs = qs.filter(co_assignees=self.request.user)
            else:
                qs = qs.filter(co_assignees=co_assignee_id)

        reporter_id = self.request.GET.get('reporter')
        if reporter_id:
            if reporter_id == 'me':
                qs = qs.filter(reporter=self.request.user)
            else:
                qs = qs.filter(reporter_id=reporter_id)

        assigned_only = self.request.GET.get('assigned')
        if assigned_only == '1':
            qs = qs.filter(assignee__isnull=False)

        # Related Issue Filter Handler
        related_filter = self.request.GET.get('related_filter')
        if related_filter == 'has':
            qs = qs.filter(related_issue__isnull=False)
        elif related_filter == 'none':
            qs = qs.filter(related_issue__isnull=True)

        related_issue_id = self.request.GET.get('related_issue')
        if related_issue_id:
            qs = qs.filter(related_issue_id=related_issue_id)

        return qs.distinct() if (search or co_assignee_id or source == 'MINE') else qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Inject authorization attributes into current page slice dynamically
        for issue in context['issues']:
            issue.can_edit = issue.is_authorized(self.request.user)

        # Build clean query string for pagination to keep your search filters intact across pages
        queries_without_page = self.request.GET.copy()
        if 'page' in queries_without_page:
            del queries_without_page['page']
        context['current_filters'] = queries_without_page.urlencode()

        # Persist state in template
        context['search'] = self.request.GET.get('q')
        context['selected_project_id'] = self.request.GET.get('project')
        context['selected_source'] = self.request.GET.get('source')

        # Dropdown data for filters
        context['projects'] = Project.objects.all()
        
        User = get_user_model()
        context['assignees'] = (
            User.objects.filter(Q(assigned_issues__isnull=False) | Q(co_assigned_issues__isnull=False))
            .distinct()
        )
        context['reporters'] = (
            User.objects.filter(reported_issues__isnull=False)
            .distinct()
        )
        context['related_issues'] = Issue.objects.filter(
            issue_type=IssueTypeChoices.TASK
        ).order_by('title')

        # Expose Choice Enums to Template
        context['IssueStatusChoices'] = IssueStatusChoices
        context['IssuePriorityChoices'] = IssuePriorityChoices
        context['IssueEnvironmentChoices'] = IssueEnvironmentChoices
        context['IssueTypeChoices'] = IssueTypeChoices

        return context


class IssueDetailView(LoginRequiredMixin, DetailView):
    model = Issue
    template_name = 'issues/issue_detail.html'
    context_object_name = 'issue'


    def get_queryset(self):
        return Issue.objects.select_related('project', 'assignee', 'reporter')


    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        issue = self.object
        issue.can_edit = issue.is_authorized(self.request.user)
        context['remark_form'] = IssueRemarkLogForm(initial={'issue': issue})
        context['remark_logs'] = issue.remark_logs.select_related('author').all()
        return context

from django.contrib import messages  # Added for flash messages context notifications

class IssueCreateView(LoginRequiredMixin, View):
    def get(self, request, project_pk):
        project = get_object_or_404(Project, pk=project_pk)
        # Added user context parameter initialization tracking configuration
        form = IssueForm(initial={'project': project, 'reporter': request.user}, user=request.user)
        return render(
            request,
            'issues/issue_form.html',
            {
                'form': form,
                'project': project,
            },
        )

    def post(self, request, project_pk):
        project = get_object_or_404(Project, pk=project_pk)
        # Added user context parameter verification handling here too
        form = IssueForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            issue = form.save(commit=False)
            issue.project = project
            issue.created_by = request.user
            issue.reporter = request.user 
            issue.save()

            IssueRemarkLog.objects.create(
                issue=issue,
                author=request.user,
                from_status=issue.status,
                to_status=issue.status,
                remark=f"Issue initially logged with Status: '{issue.get_status_display()}' and Priority: '{issue.get_priority_display()}'.",
            )

            # Added standard creation success context notification message
            messages.success(request, f"Issue '{issue.title}' logged successfully.")
            return redirect('issues:issue_detail', pk=issue.pk)
            
        return render(
            request,
            'issues/issue_form.html',
            {
                'form': form,
                'project': project,
            },
        )

class IssueUpdateView(LoginRequiredMixin, View):
    def get(self, request, pk):
        issue = get_object_or_404(Issue, pk=pk)
        form = IssueForm(instance=issue, user=request.user)
        
        if 'reporter' in form.fields:
            form.fields['reporter'].widget.attrs['readonly'] = True
            
        return render(
            request,
            'issues/issue_form.html',
            {
                'form': form,
                'project': issue.project,
                'issue': issue,
            },
        )

    def post(self, request, pk):
        issue = get_object_or_404(Issue, pk=pk)
        old_status = issue.status
        old_priority = issue.priority
        old_status_label = issue.get_status_display()
        old_priority_label = issue.get_priority_display()

        form = IssueForm(request.POST, request.FILES, instance=issue, user=request.user)
        
        if form.is_valid():
            issue = form.save()

            if old_status != issue.status:
                IssueRemarkLog.objects.create(
                    issue=issue,
                    author=request.user,
                    from_status=old_status,
                    to_status=issue.status,
                    remark=f"Status changed from {old_status_label} to {issue.get_status_display()}.",
                )

            if old_priority != issue.priority:
                IssueRemarkLog.objects.create(
                    issue=issue,
                    author=request.user,
                    from_status=issue.status,
                    to_status=issue.status,
                    remark=f"Priority changed from {old_priority_label} to {issue.get_priority_display()}.",
                )

            # Added standard modifications update save success context banner message
            messages.success(request, f"Changes to tracking item '{issue.title}' saved successfully.")
            return redirect('issues:issue_detail', pk=issue.pk)

        return render(
            request,
            'issues/issue_form.html',
            {
                'form': form,
                'project': issue.project,
                'issue': issue,
            },
        )

class IssueAddRemarkView(LoginRequiredMixin, View):
    def post(self, request, pk):
        issue = get_object_or_404(Issue, pk=pk)
        form = IssueRemarkLogForm(request.POST)
        if form.is_valid():
            remark_log = form.save(commit=False)
            remark_log.issue = issue
            remark_log.author = request.user
            remark_log.from_status = issue.status
            remark_log.to_status = form.cleaned_data.get('to_status') or issue.status
            remark_log.save()

            if remark_log.to_status and remark_log.to_status != issue.status:
                issue.status = remark_log.to_status
                issue.save(update_fields=['status', 'updated_at'])

        return redirect('issues:issue_detail', pk=issue.pk)

    def get(self, request, pk):
        return redirect('issues:issue_detail', pk=pk)

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView
from django.db.models import Q, Count
from django.utils import timezone
from datetime import timedelta
# Assuming these imports exist in your project structure:
# from .models import Issue, TeamMemberRoleChoices

class MyIssueListView(LoginRequiredMixin, ListView):
    model = Issue
    template_name = 'issues/my_task.html'
    context_object_name = 'issues'
    paginate_by = 50

    def get_queryset(self):
        user = self.request.user
        
        if hasattr(user, 'team_member'):
            role = user.team_member.role
        else:
            role = None
        
        if role == TeamMemberRoleChoices.QA:
            qs = Issue.objects.filter(reporter=user)
        elif role == TeamMemberRoleChoices.DEVELOPER:
            qs = Issue.objects.filter(Q(assignee=user) | Q(co_assignees=user))
        else:
            qs = Issue.objects.filter(Q(assignee=user) | Q(reporter=user) | Q(co_assignees=user))

        # Apply Time Filter
        date_filter = self.request.GET.get('date_filter')
        now = timezone.now()
        if date_filter == 'day':
            qs = qs.filter(created_at__gte=now - timedelta(days=1))
        elif date_filter == 'week':
            qs = qs.filter(created_at__gte=now - timedelta(weeks=1))
        elif date_filter == 'month':
            qs = qs.filter(created_at__gte=now - timedelta(days=30))

        # Apply Status / Assignment Filter
        status = self.request.GET.get('status')
        if status:
            if status == 'pending_qa':
                qs = qs.filter(status='ready_for_qa')
            elif status == 'co_assigned':
                qs = qs.filter(co_assignees=user)
            else:
                qs = qs.filter(status=status)
            
        return qs.select_related('project', 'assignee', 'reporter').prefetch_related('tags', 'co_assignees').distinct().order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        if hasattr(user, 'team_member'):
            role = user.team_member.role
            context['view_perspective'] = user.team_member.get_role_display()
        else:
            role = None
            context['view_perspective'] = "Staff / Admin"
        
        # Build clean query string parameter preservation for pagination loops
        queries_without_page = self.request.GET.copy()
        if 'page' in queries_without_page:
            del queries_without_page['page']
        context['current_filters'] = queries_without_page.urlencode()

        # Summary Metrics Evaluation Base Line
        if role == TeamMemberRoleChoices.QA:
            metrics_qs = Issue.objects.filter(reporter=user)
        elif role == TeamMemberRoleChoices.DEVELOPER:
            metrics_qs = Issue.objects.filter(Q(assignee=user) | Q(co_assignees=user))
        else:
            metrics_qs = Issue.objects.filter(Q(assignee=user) | Q(reporter=user) | Q(co_assignees=user))

        # Align metrics tracking indicators seamlessly with active timeline viewports
        date_filter = self.request.GET.get('date_filter')
        now = timezone.now()
        if date_filter == 'day':
            metrics_qs = metrics_qs.filter(created_at__gte=now - timedelta(days=1))
        elif date_filter == 'week':
            metrics_qs = metrics_qs.filter(created_at__gte=now - timedelta(weeks=1))
        elif date_filter == 'month':
            metrics_qs = metrics_qs.filter(created_at__gte=now - timedelta(days=30))

        # UPDATED: Added tracking evaluation metrics for ALL pipeline variants without breaking original logic paths
        context['metrics'] = metrics_qs.aggregate(
            total=Count('id', distinct=True),
            open=Count('id', filter=Q(status='open'), distinct=True),
            dev_in_progress=Count('id', filter=Q(status='dev_in_progress'), distinct=True),
            pending_qa=Count('id', filter=Q(status='ready_for_qa'), distinct=True),
            qa_in_progress=Count('id', filter=Q(status='qa_in_progress'), distinct=True),
            in_review=Count('id', filter=Q(status='in_review'), distinct=True),
            hold=Count('id', filter=Q(status='hold'), distinct=True),
            scope_review=Count('id', filter=Q(status='scope_review'), distinct=True),
            rejected=Count('id', filter=Q(status='rejected'), distinct=True),
            done=Count('id', filter=Q(status='done'), distinct=True),
            closed=Count('id', filter=Q(status='closed'), distinct=True),
            reopen=Count('id', filter=Q(status='reopen'), distinct=True),
            critical=Count('id', filter=Q(priority='high'), distinct=True),
            co_assigned=Count('id', filter=Q(co_assignees=user), distinct=True)
        )
        
        context['current_status'] = self.request.GET.get('status', '')
        context['current_date_filter'] = self.request.GET.get('date_filter', 'all')

        # --- Dynamic UI Dropdown Permission Engine ---
        all_choices = dict(Issue.StatusChoices.choices if hasattr(Issue, 'StatusChoices') else IssueStatusChoices.choices)
        
        if role == TeamMemberRoleChoices.DEVELOPER:
            allowed_keys = ['open' ,'dev_in_progress', 'scope_review', 'in_review', 'hold', 'ready_for_qa', ]
        elif role == TeamMemberRoleChoices.QA:
            allowed_keys = ['open' ,'qa_in_progress', 'hold', 'scope_review', 'rejected', 'done', 'closed', 'reopen']
        else:
            allowed_keys = list(all_choices.keys())

        context['status_choices'] = [(key, all_choices[key]) for key in allowed_keys if key in all_choices]
        
        return context
    
class TagListView(LoginRequiredMixin, View):
    def get(self, request):
        tags = Tag.objects.all()
        return render(request, "tags/tag_list.html", {"tags": tags})


class TagCreateView(LoginRequiredMixin, View):
    def get(self, request):
        form = TagForm()
        return render(request, "tags/tag_form.html", {"form": form, "title": "Create Tag"})

    def post(self, request):
        form = TagForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("issues:tag_list")
        return render(request, "tags/tag_form.html", {"form": form, "title": "Create Tag"})


class TagUpdateView(LoginRequiredMixin, View):
    def get(self, request, pk):
        tag = get_object_or_404(Tag, pk=pk)
        form = TagForm(instance=tag)
        return render(request, "tags/tag_form.html", {"form": form, "title": "Edit Tag"})

    def post(self, request, pk):
        tag = get_object_or_404(Tag, pk=pk)
        form = TagForm(request.POST, instance=tag)
        if form.is_valid():
            form.save()
            return redirect("issues:tag_list")
        return render(request, "tags/tag_form.html", {"form": form, "title": "Edit Tag"})


class TagDeleteView(LoginRequiredMixin, View):
    def get(self, request, pk):
        tag = get_object_or_404(Tag, pk=pk)
        return render(request, "tags/tag_confirm_delete.html", {"tag": tag})

    def post(self, request, pk):
        tag = get_object_or_404(Tag, pk=pk)
        tag.delete()
        return redirect("issues:tag_list")
    


import json
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.generic import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404
from .models import Issue, IssueRemarkLog  # Adjust application import paths as necessary

class IssueStatusUpdateAjaxView(LoginRequiredMixin, View):
    """
    Handles inline status updates for an Issue over AJAX/Fetch API.
    Returns JSON responses and records history logs on change.
    """
    def post(self, request, pk):
        if request.headers.get('x-requested-with') != 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': 'Invalid request method.'}, status=400)
            
        issue = get_object_or_404(Issue, pk=pk)
        
        try:
            data = json.loads(request.body)
            new_status = data.get('status')
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'error': 'Malformed JSON payload.'}, status=400)

        # Validate that the requested status is defined within model choices
        valid_statuses = [choice[0] for choice in Issue._meta.get_field('status').choices]
        if new_status not in valid_statuses:
            return JsonResponse({'success': False, 'error': 'Invalid status choice.'}, status=400)

        old_status = issue.status
        old_status_label = issue.get_status_display()

        if old_status != new_status:
            issue.status = new_status
            issue.save()

            # Generate modern logging details tracking changes
            IssueRemarkLog.objects.create(
                issue=issue,
                author=request.user,
                from_status=old_status,
                to_status=issue.status,
                remark=f"Status changed from {old_status_label} to {issue.get_status_display()} via quick update dashboard.",
            )
            
            return JsonResponse({
                'success': True,
                'new_status_display': issue.get_status_display(),
                'new_status_class': self._get_status_badge_class(new_status)
            })

        return JsonResponse({'success': True, 'info': 'No status changes detected.'})

    def _get_status_badge_class(self, status):
        """Helper to return CSS classes synchronized with your templates layout."""
        if status == 'open':
            return 'bg-info'
        elif status in ['ready_for_qa', 'pending_qa']:
            return 'bg-success'
        elif status == 'dev_in_progress':
            return 'bg-warning'
        return 'bg-secondary text-white'