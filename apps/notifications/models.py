from django.db import models
from django.conf import settings


class RiverJob(models.Model):
    id = models.BigAutoField(primary_key=True)
    kind = models.TextField()
    args = models.JSONField()
    queue = models.TextField(default="default")
    state = models.TextField(default="available")
    max_attempts = models.IntegerField(default=3)

    class Meta:
        db_table = "river_job"
        managed = False  # Tells Django ORM NOT to run migrations on this table




class Notification(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='notifications'
    )
    title = models.CharField(max_length=255)
    message = models.TextField()
    notification_type = models.CharField(max_length=50, default='status_changed')
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='sent_notifications'
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.title}"