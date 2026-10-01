from django.apps import AppConfig
from django.db.models.signals import post_migrate


def auto_sync_strategy_presets(sender, **kwargs):
    """Automatically seeds missing Go strategy presets into BacktestRule table."""
    try:
        from apps.backtest.services import ensure_strategy_presets_exist
        ensure_strategy_presets_exist()
    except Exception as e:
        import logging
        logging.getLogger(__name__).debug("Strategy presets auto-sync skipped: %s", e)


class BacktestConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.backtest'

    def ready(self):
        post_migrate.connect(auto_sync_strategy_presets, sender=self)
