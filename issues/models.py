from django.conf import settings
from django.db import models
from cloudinary.models import CloudinaryField

from .choices import IssueEnvironmentChoices, IssuePriorityChoices, IssueStatusChoices, IssueTypeChoices


class Project(models.Model):
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='owned_projects',
    )
    team = models.ForeignKey(
        'users.Team',  # change this string if your Team model lives elsewhere
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='projects',
    )
    is_active = models.BooleanField(default=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_projects',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        if self.code:
            return f'{self.code} - {self.name}'
        return self.name
    

class Issue(models.Model):
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='issues',
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    issue_type = models.CharField(
        max_length=20,
        choices=IssueTypeChoices.choices,
        default=IssueTypeChoices.TASK,
    )
    drive_url = models.CharField(
        max_length=500,
        null=True,
        blank=True
    )

    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reported_issues',
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_issues',
        limit_choices_to={'is_superuser': False},
    )
    
    co_assignees = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name='co_assigned_issues',
        help_text='Additional users assigned to this issue',
        limit_choices_to={'is_superuser': False},
    )

    priority = models.CharField(
        max_length=20,
        choices=IssuePriorityChoices.choices,
        default=IssuePriorityChoices.MEDIUM,
    )

    environment = models.CharField(
        max_length=20,
        choices=IssueEnvironmentChoices.choices,
        default=IssueEnvironmentChoices.STAGING,
    )
    
    status = models.CharField(
        max_length=20,
        choices=IssueStatusChoices.choices,
        default=IssueStatusChoices.OPEN,
    )

    time_estimate_hours = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Estimated effort in hours',
    )

    # NEW: optional self‑reference for related / parent issue
    related_issue = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='related_issues',
        help_text='Optional related or parent issue',
        limit_choices_to={'issue_type': IssueTypeChoices.TASK},  # optional extra safety
    )
    tags = models.ManyToManyField(
        'Tag',
        related_name='issues',
        blank=True,
        help_text='Tags used to classify this issue',
    )
    remarks = models.TextField(blank=True)
    qa_note = models.TextField(blank=True)

    image_1 = CloudinaryField('image', null=True, blank=True)
    image_2 = CloudinaryField('image', null=True, blank=True)
    image_3 = CloudinaryField('image', null=True, blank=True)
    image_4 = CloudinaryField('image', null=True, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_issues',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
            ordering = ['-created_at']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Track initial state to detect field updates during save execution
        self._current_status = self.status

    def __str__(self):
        return self.title
    
    def is_authorized(self, user):
        if not user or not user.is_authenticated:
            return False
        
        # 1. Check primary assignee
        if user == self.assignee:
            return True
            
        # 3. Check reporter
        if user == self.reporter:
            return True
            
        # 2. Check co-assignees list (Optimized check)
        if self.co_assignees.contains(user):
            return True
            
        # 4. Check management roles
        team_member = getattr(user, 'team_member', None)
        if team_member and team_member.role in getattr(settings, 'MANAGEMENT_ROLES', []):
            return True
            
        return False


class IssueRemarkLog(models.Model):
    issue = models.ForeignKey(
        Issue,
        on_delete=models.CASCADE,
        related_name='remark_logs',
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='issue_remark_logs',
    )
    from_status = models.CharField(
        max_length=20,
        blank=True,
    )
    to_status = models.CharField(
        max_length=20,
        blank=True,
    )
    remark = models.TextField(blank=True)
    qa_note = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Log #{self.id} for Issue #{self.issue_id}'
    

class Tag(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name