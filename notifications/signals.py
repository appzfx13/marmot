from django.db.models.signals import post_save, m2m_changed
from django.dispatch import receiver
from django.contrib.contenttypes.models import ContentType

from issues.models import Issue, IssueRemarkLog
from .models import Notification, NotificationType, NotificationScope


@receiver(post_save, sender=Issue)
def handle_issue_creation_and_changes(sender, instance, created, **kwargs):
    """
    Listens for new issues or updates to critical issue fields like 'status'.
    """
    # 1. Handle New Issue Creation
    if created:
        notification = Notification.objects.create(
            notification_type=NotificationType.ISSUE_ASSIGNED,
            scope=NotificationScope.INDIVIDUAL,
            title=f"New Issue Assigned: {instance.title}",
            message=f"You have been added to the issue '{instance.title}' under project {instance.project.name}.",
            target_object=instance,
            sender=instance.created_by
        )
        notification.create_delivery_records()
        return

    # 2. Handle Existing Issue Updates (e.g., Status changes)
    # Note: To avoid spamming on every tiny change, we usually check if status changed.
    # For a robust approach, we track dirty fields, but here is a clear implementation:
    if hasattr(instance, '_current_status') and instance.status != instance._current_status:
        notification = Notification.objects.create(
            notification_type=NotificationType.STATUS_CHANGED,
            scope=NotificationScope.INDIVIDUAL,
            title=f"Status Updated: {instance.title}",
            message=f"The status of issue '{instance.title}' has been shifted to {instance.get_status_display()}.",
            target_object=instance,
            sender=instance.created_by # Or tie to request.user if passing via custom middleware
        )
        notification.create_delivery_records()


@receiver(m2m_changed, sender=Issue.co_assignees.through)
def handle_co_assignees_changed(sender, instance, action, pk_set, **kwargs):
    """
    Listens specifically to shifts in the Co-Assignees ManyToMany field 
    to alert users when they are added to a task squad.
    """
    if action == "post_add":
        from django.contrib.auth import get_user_model
        User = get_user_model()
        added_users = User.objects.filter(pk__in=pk_set)
        
        # Create a specific notification targeted directly to those newly chosen users
        notification = Notification.objects.create(
            notification_type=NotificationType.ISSUE_UPDATED,
            scope=NotificationScope.INDIVIDUAL,
            title=f"Added as Co-assignee: {instance.title}",
            message=f"You have been added as a co-assignee to track and collaborate on: '{instance.title}'.",
            target_object=instance,
        )
        # Instead of generic issue processing, directly populate these specific new users
        notification.target_users.add(*added_users)
        notification.create_delivery_records()


@receiver(post_save, sender=IssueRemarkLog)
def handle_new_remark_log(sender, instance, created, **kwargs):
    """
    Triggers notifications whenever a Developer or QA submits a formal comment block.
    """
    if created:
        # Determine if it's a structural QA update or standard progress remark
        notif_type = NotificationType.QA_NOTE_ADDED if instance.qa_note else NotificationType.REMARK_ADDED
        title_prefix = "New QA Note" if instance.qa_note else "New Developer Remark"
        
        notification = Notification.objects.create(
            notification_type=notif_type,
            scope=NotificationScope.INDIVIDUAL,
            title=f"{title_prefix} on Issue #{instance.issue.id}",
            message=f"Author {instance.author} added a note regarding issue '{instance.issue.title}'.",
            target_object=instance.issue, # Point back to the main Issue page
            sender=instance.author
        )
        notification.create_delivery_records()