import os
import logging
from logging import FileHandler
from datetime import datetime
from django.conf import settings
from apps.common.choices import LoggerCategoryChoices, PermanentLogTargets


class Logger:
    """A logging utility that creates and manages log files for Marmot trading applications."""

    @staticmethod
    def get_log_section(app_name: str) -> str:
        """Maps an app or subsystem name to its dedicated LoggerCategoryChoice."""
        app_mapping = {
            "trade_core": LoggerCategoryChoices.TRADING,
            "trade_config": LoggerCategoryChoices.TRADE_CONFIG,
            "market": LoggerCategoryChoices.MARKET,
            "notifications": LoggerCategoryChoices.NOTIFICATIONS,
            "postback": LoggerCategoryChoices.POSTBACK,
            "users": LoggerCategoryChoices.USERS,
            "admins": LoggerCategoryChoices.ADMINS,
            "backtest": LoggerCategoryChoices.BACKTEST,
            "masters": LoggerCategoryChoices.MASTERS,
            "common": LoggerCategoryChoices.SYSTEM,
        }
        return app_mapping.get(app_name.lower(), LoggerCategoryChoices.SYSTEM)

    def cleanup_old_logs(self, log_dir: str):
        """Cleans up log files older than LOG_RETENTION_DAYS."""
        try:
            retention_days = getattr(settings, "LOG_RETENTION_DAYS", None)
            if not retention_days:
                return
            cutoff = datetime.now().date()
            for name in os.listdir(log_dir):
                if not name.endswith(".log"):
                    continue
                try:
                    date_str = name.replace(".log", "")
                    file_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                except ValueError:
                    continue
                if (cutoff - file_date).days > retention_days:
                    os.remove(os.path.join(log_dir, name))
        except Exception:
            pass

    def __init__(self, section=None, app=None, log_type=None, process=None, msg=None):
        """Initializes the structured file logger with automatic directory creation and rotation."""
        base_log_dir = getattr(settings, "LOG_DIR", os.path.join(settings.BASE_DIR, "logs"))
        path_components = [base_log_dir, section, app, log_type]
        if process:
            path_components.append(process)
        log_dir = os.path.join(*[str(c) for c in path_components if c])
        os.makedirs(log_dir, exist_ok=True)
        if (app, log_type) not in PermanentLogTargets.ALL:
            self.cleanup_old_logs(log_dir)
        filename = os.path.join(log_dir, f"{datetime.now().strftime('%Y-%m-%d')}.log")
        logger_name = f"{section}.{app}.{log_type}" if section else f"{app}.{log_type}"
        if process:
            logger_name += f".{process}"
        self._logger = logging.getLogger(logger_name)
        if not self._logger.handlers:
            self._logger.setLevel(logging.INFO)
            handler = FileHandler(filename, encoding="utf-8")
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
                datefmt="%Y-%m-%d %H:%M:%S"
            )
            handler.setFormatter(formatter)
            self._logger.addHandler(handler)
            self._logger.propagate = False
        if msg:
            self._logger.info(msg)

    def info(self, msg: str):
        """Logs an INFO level message."""
        self._logger.info(msg)

    def error(self, msg: str):
        """Logs an ERROR level message."""
        self._logger.error(msg)

    def warning(self, msg: str):
        """Logs a WARNING level message."""
        self._logger.warning(msg)

    def debug(self, msg: str):
        """Logs a DEBUG level message."""
        self._logger.debug(msg)

    def exception(self, msg: str):
        """Logs an EXCEPTION with traceback at ERROR level."""
        self._logger.exception(msg)
