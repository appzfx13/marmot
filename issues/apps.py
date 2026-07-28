from django.apps import AppConfig


class IssuesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "issues"

    def ready(self):
        from .scheduler import start_scheduler
        start_scheduler()