from django.conf import settings
from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

from apps.notifications.choices import NotificationScope, NotificationType
from django.contrib.auth import get_user_model
User = get_user_model()

class Notification(models.Model):
    """
    Represents a core notification event or announcement triggered in the system.
    Can be automated (via Issues) or manually drafted by Management/Admins.
    """
    notification_type = models.CharField(
        max_length=30,
        choices=NotificationType.choices,
        default=NotificationType.ISSUE_UPDATED
    )
    scope = models.CharField(
        max_length=15,
        choices=NotificationScope.choices,
        default=NotificationScope.INDIVIDUAL,
        help_text="Defines the delivery audience rule for this notification."
    )
    title = models.CharField(max_length=255)
    message = models.TextField()
    
    # Generic Foreign Key to associate with ANY model (e.g., Issue, IssueRemarkLog, Project)
    content_type = models.ForeignKey(
        ContentType, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True
    )
    object_id = models.PositiveIntegerField(null=True, blank=True)
    target_object = GenericForeignKey('content_type', 'object_id')
    
    # Target Filters
    target_team = models.ForeignKey(
        'users.Team',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='team_announcements',
        help_text="Used when scope is set to TEAM."
    )
    target_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name='custom_targeted_notifications',
        help_text="Manually select specific users to receive this notification."
    )
    
    # Actor / Trigger metadata
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sent_notifications',
        help_text="The user who performed the action or wrote the announcement."
    )
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
        ]

    def __str__(self):
        return f"[{self.get_notification_type_display()}] {self.title}"

    def create_delivery_records(self):
        """
        Business Logic: Gathers all recipients based on the scope, issue actors, 
        or manual user configurations, and generates individual UserNotificationStatus rows.
        """
        recipients = set()

        # 1. Direct Target check (If individual users are explicitly chosen)
        if self.target_users.exists():
            recipients.update(self.target_users.all())

        # 2. Automated Issue context logic 
        # (Checks if object is an instance of an Issue to extract Assignees, Reporter, & Co-Assignees)
        elif self.scope == NotificationScope.INDIVIDUAL and self.content_type and self.content_type.model == 'issue':
            issue = self.target_object
            if issue:
                if issue.assignee:
                    recipients.add(issue.assignee)
                if issue.reporter:
                    recipients.add(issue.reporter)
                # Safeguard check to pull ManyToMany fields safely
                recipients.update(issue.co_assignees.all())

        # 3. Management Team scope logic
        elif self.scope == NotificationScope.TEAM and self.target_team:
            # Query active user profiles associated with the target team
            team_users = [member.user for member in self.target_team.teammember_set.select_related('user').all() if member.user]
            recipients.update(team_users)

        # 4. Global application scope
        elif self.scope == NotificationScope.ALL:
            
            recipients.update(User.objects.filter(is_active=True))

        # Bulk optimize delivery database insertions while skipping the trigger sender
        status_instances = [
            UserNotificationStatus(user=user, notification=self)
            for user in recipients if user != self.sender
        ]
        
        if status_instances:
            UserNotificationStatus.objects.bulk_create(status_instances, ignore_conflicts=True)


class UserNotificationStatus(models.Model):
    """
    Per-user recipient mapping that manages individual delivery flags, 
    read states, and timestamp histories.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    notification = models.ForeignKey(
        Notification,
        on_delete=models.CASCADE,
        related_name='recipients'
    )
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    
    is_emailed = models.BooleanField(default=False) 

    class Meta:
        ordering = ['-notification__created_at']
        unique_together = ('user', 'notification')

    def __str__(self):
        status = "Read" if self.is_read else "Unread"
        return f"User: {self.user.username} | {status}"