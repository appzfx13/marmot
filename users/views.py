from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import (
    TemplateView,
    ListView,
    CreateView,
    UpdateView,
    DeleteView,
)
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from issues.choices import IssuePriorityChoices, IssueStatusChoices, IssueTypeChoices, TeamMemberRoleChoices
from issues.models import Issue, IssueRemarkLog, Project

from .forms import TeamForm, TeamMemberForm
from .models import Team, TeamMember
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.db.models import Q, Count
from issues.models import Project, Issue, IssueRemarkLog
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import HttpResponse
from django.views.generic import View
import sqlite3
import os
from django.db import models


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'users/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        project_id = self.request.GET.get('project')
        source = self.request.GET.get('source', 'ALL')
        page_number = self.request.GET.get('page', 1)  # Get current page number
        user = self.request.user

        # Safe Check: Prevent RelatedObjectDoesNotExist if user has no profile
        if hasattr(user, 'team_member'):
            role = user.team_member.role
        else:
            role = None

        context['projects'] = Project.objects.all()
        context['selected_project_id'] = project_id
        context['selected_source'] = source

        # 1. Base Querysets
        recent_activities_qs = IssueRemarkLog.objects.select_related(
            'issue', 'author', 'issue__project'
        ).order_by('-created_at')
        
        issues_qs = Issue.objects.all()

        # 2. Filtering Logic
        if project_id:
            issues_qs = issues_qs.filter(project_id=project_id)
            recent_activities_qs = recent_activities_qs.filter(issue__project_id=project_id)
        
        if source == 'MINE':
            if role == TeamMemberRoleChoices.QA:
                issues_qs = issues_qs.filter(reporter=self.request.user)
                recent_activities_qs = recent_activities_qs.filter(issue__reporter=self.request.user)
            elif role == TeamMemberRoleChoices.DEVELOPER:
                issues_qs = issues_qs.filter(assignee=self.request.user)
                recent_activities_qs = recent_activities_qs.filter(issue__assignee=self.request.user)
            else:
                issues_qs = issues_qs.filter(assignee=self.request.user, reporter=self.request.user)
                recent_activities_qs = recent_activities_qs.filter(issue__assignee=self.request.user, issue__reporter=self.request.user)

        # 3. Pagination Configuration (10 activities per page)
        paginator = Paginator(recent_activities_qs, 10)
        try:
            activities_page = paginator.page(page_number)
        except PageNotAnInteger:
            activities_page = paginator.page(1)
        except EmptyPage:
            activities_page = paginator.page(paginator.num_pages)

        # 4. Process Recent Activities (Pre-mapping labels for HTML)
        status_map = {c.value: c.label for c in IssueStatusChoices}
        type_map = {t.value: t.label for t in IssueTypeChoices}
        
        for log in activities_page:
            # Map raw strings to human-readable labels
            log.from_status_label = status_map.get(log.from_status, log.from_status)
            log.to_status_label = status_map.get(log.to_status, log.to_status)
            log.type_label = type_map.get(log.issue.issue_type, log.issue.issue_type)

        context['recent_activities'] = activities_page  # Passes Page Object

        # 5. Dashboard Metrics
        context['active_bugs'] = issues_qs.filter(status=IssueStatusChoices.OPEN).count()
        context['active_tasks'] = issues_qs.filter(
            models.Q(status=IssueStatusChoices.DEV_IN_PROGRESS) |
            models.Q(status=IssueStatusChoices.QA_IN_PROGRESS),
            assignee__isnull=False
        ).count()
        context['high_priority_bugs'] = issues_qs.filter(
            status=IssueStatusChoices.OPEN, priority=IssuePriorityChoices.HIGH
        ).count()
        context['my_open_issues'] = issues_qs.filter(
            status=IssueStatusChoices.OPEN, assignee=self.request.user
        ).count()

        # 6. Status Grid Stats
        raw_status_stats = issues_qs.values('status').annotate(count=Count('id'))
        count_map = {item['status']: item['count'] for item in raw_status_stats}
        context['issue_status_stats'] = [
            {'value': c.value, 'label': c.label, 'count': count_map.get(c.value, 0)}
            for c in IssueStatusChoices
        ]

        # 7. Pass Enums for HTML logic comparisons
        context['IssueStatusChoices'] = IssueStatusChoices
        context['IssueTypeChoices'] = IssueTypeChoices
        context['IssuePriorityChoices'] = IssuePriorityChoices

        return context
    
    
class TeamListView(LoginRequiredMixin, ListView):
    model = Team
    template_name = 'users/team_list.html'
    context_object_name = 'teams'
    ordering = ['-created_at']


class TeamCreateView(LoginRequiredMixin, CreateView):
    model = Team
    form_class = TeamForm
    template_name = 'users/team_form.html'
    success_url = reverse_lazy('users:team_list')


class TeamUpdateView(LoginRequiredMixin, UpdateView):
    model = Team
    form_class = TeamForm
    template_name = 'users/team_form.html'
    success_url = reverse_lazy('users:team_list')


class TeamDeleteView(LoginRequiredMixin, DeleteView):
    model = Team
    template_name = 'users/team_confirm_delete.html'
    success_url = reverse_lazy('users:team_list')


class TeamMemberListView(LoginRequiredMixin, ListView):
    model = TeamMember
    template_name = 'users/teammember_list.html'
    context_object_name = 'members'
    ordering = ['-created_at']

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.select_related('user').filter(user__is_superuser=False)


class TeamMemberCreateView(LoginRequiredMixin, CreateView):
    model = TeamMember
    form_class = TeamMemberForm
    template_name = 'users/teammember_form.html'
    success_url = reverse_lazy('users:teammember_list')


class TeamMemberUpdateView(LoginRequiredMixin, UpdateView):
    model = TeamMember
    form_class = TeamMemberForm
    template_name = 'users/teammember_form.html'
    success_url = reverse_lazy('users:teammember_list')


class TeamMemberDeleteView(LoginRequiredMixin, DeleteView):
    model = TeamMember
    template_name = 'users/teammember_confirm_delete.html'
    success_url = reverse_lazy('users:teammember_list')


class DownloadDBView(LoginRequiredMixin, UserPassesTestMixin, View):
    def test_func(self):
        return self.request.user.is_superuser
    
    def get(self, request):
        db_path = 'db.sqlite3'
        if not os.path.exists(db_path):
            return HttpResponse('DB not found', status=404)
        
        # Fix: Backup to temp file, then read (non-blocking, safe)
        temp_path = '/tmp/db_backup.sqlite3'
        conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
        try:
            backup_conn = sqlite3.connect(temp_path)
            conn.backup(backup_conn)
            backup_conn.close()
            
            with open(temp_path, 'rb') as f:
                response = HttpResponse(f.read(), content_type='application/x-sqlite3')
                response['Content-Disposition'] = 'attachment; filename="db.sqlite3"'
                return response
        finally:
            conn.close()
            if os.path.exists(temp_path):
                os.unlink(temp_path)


# MARMOT 

from django.contrib.auth.views import LoginView
from django.urls import reverse_lazy
from django.views.generic import TemplateView

from .mixins import MarmotRoleRequiredMixin
from .models import MarmotUser, TeamMember, TeamMemberRoleChoices

class MarmotLoginView(LoginView):
    template_name = 'marmot/login.html'
    redirect_authenticated_user = True

    def get_success_url(self):
        user = self.request.user
        allowed_roles = [
            TeamMemberRoleChoices.ADMIN,
            TeamMemberRoleChoices.TRADERS,
        ]
        allowed_values = [
            role.value if hasattr(role, 'value') else role
            for role in allowed_roles
        ]

        # 1. Superusers pass automatically
        if user.is_superuser:
            return reverse_lazy('users:marmot-dashboard')

        # 2. Check TeamMember model
        if hasattr(user, 'team_member') and user.team_member:
            if user.team_member.role in allowed_values:
                return reverse_lazy('users:marmot-dashboard')

        # 3. Check MarmotUser model (matching by username or full name)
        marmot_user = MarmotUser.objects.filter(
            name__iexact=user.username
        ).first()
        if marmot_user and marmot_user.role in allowed_values:
            return reverse_lazy('users:marmot-dashboard')

        # 4. Check Django Groups fallback
        if user.groups.filter(name__in=allowed_values).exists():
            return reverse_lazy('users:marmot-dashboard')

        # Fallback redirect if unauthorized role
        return reverse_lazy('users:marmot-login')



class MarmotDashboardView(MarmotRoleRequiredMixin, TemplateView):
    template_name = 'marmot/dashboard.html'
    allowed_roles = [
        TeamMemberRoleChoices.ADMIN,
        TeamMemberRoleChoices.TRADERS,
    ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Retrieve current user's MarmotUser risk/trading metrics
        context['marmot_profile'] = MarmotUser.objects.filter(
            name__iexact=self.request.user.username
        ).first()

        return context


