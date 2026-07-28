from django.db import models

class NotificationType(models.TextChoices):
    # Issue related types
    ISSUE_ASSIGNED = 'issue_assigned', 'Issue Assigned'
    ISSUE_UPDATED = 'issue_updated', 'Issue Updated'
    STATUS_CHANGED = 'status_changed', 'Status Changed'
    REMARK_ADDED = 'remark_added', 'Remark Added'
    QA_NOTE_ADDED = 'qa_note_added', 'QA Note Added'
    
    # Management & Admin related types
    MANAGEMENT_ANNOUNCEMENT = 'management_announcement', 'Management Announcement'
    ADMIN_ANNOUNCEMENT = 'admin_announcement', 'Admin Announcement'
    SYSTEM_ALERT = 'system_alert', 'System Alert'


class NotificationScope(models.TextChoices):
    INDIVIDUAL = 'individual', 'Targeted Individuals'  # Issue automated actors or manually selected users
    TEAM = 'team', 'Specific Team'                    # Management announcements targeting a group
    ALL = 'all', 'Entire Organization'                # Global announcements/system alerts