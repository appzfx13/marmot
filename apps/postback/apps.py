from django.apps import AppConfig


class PostbackConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.postback'
    verbose_name = 'Broker Postback & Webhook Management'
