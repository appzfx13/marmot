import os
import sys
import logging
from logging import FileHandler, StreamHandler
from datetime import datetime
from django.conf import settings
from apps.common.choices import LoggerCategoryChoices, PermanentLogTargets


class Logger:
    """A global date-wise structured logging utility for Django with traceback support."""

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
            retention_days = getattr(settings, "LOG_RETENTION_DAYS", 30)
            if not retention_days:
                return
            cutoff = datetime.now().date()
            if not os.path.exists(log_dir):
                return
            for name in os.listdir(log_dir):
                if not name.endswith(".log"):
                    continue
                try:
                    clean_name = name.replace("errors_", "").replace(".log", "")
                    file_date = datetime.strptime(clean_name, "%Y-%m-%d").date()
                except ValueError:
                    continue
                if (cutoff - file_date).days > retention_days:
                    os.remove(os.path.join(log_dir, name))
        except Exception:
            pass

    def __init__(self, section=None, app=None, log_type=None, process=None, msg=None):
        """Initializes date-wise structured file logger under logs/django/."""
        base_log_dir = getattr(settings, "LOG_DIR", os.path.join(settings.BASE_DIR, "logs"))
        django_log_dir = os.path.join(base_log_dir, "django")

        path_components = [django_log_dir]
        if section or app or log_type:
            path_components.append("apps")
            if section:
                path_components.append(str(section))
            if app:
                path_components.append(str(app))
            if log_type:
                path_components.append(str(log_type))
            if process:
                path_components.append(str(process))

        log_dir = os.path.join(*path_components)
        os.makedirs(log_dir, exist_ok=True)
        os.makedirs(django_log_dir, exist_ok=True)

        if (app, log_type) not in PermanentLogTargets.ALL:
            self.cleanup_old_logs(log_dir)
            self.cleanup_old_logs(django_log_dir)

        today_str = datetime.now().strftime("%Y-%m-%d")
        daily_log_path = os.path.join(django_log_dir, f"{today_str}.log")
        daily_error_log_path = os.path.join(django_log_dir, f"errors_{today_str}.log")
        app_log_path = os.path.join(log_dir, f"{today_str}.log") if log_dir != django_log_dir else daily_log_path

        logger_name = f"django.{section}.{app}.{log_type}" if section else f"django.{app}.{log_type}"
        if process:
            logger_name += f".{process}"

        self._logger = logging.getLogger(logger_name)
        if not self._logger.handlers:
            self._logger.setLevel(logging.INFO)
            formatter = logging.Formatter(
                "%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            )

            # 1. Main Daily Django Log Handler
            main_handler = FileHandler(daily_log_path, encoding="utf-8")
            main_handler.setFormatter(formatter)
            main_handler.setLevel(logging.INFO)
            self._logger.addHandler(main_handler)

            # 2. Specific App Log Handler (if different from root)
            if app_log_path != daily_log_path:
                app_handler = FileHandler(app_log_path, encoding="utf-8")
                app_handler.setFormatter(formatter)
                app_handler.setLevel(logging.INFO)
                self._logger.addHandler(app_handler)

            # 3. Dedicated Error Traceback Log Handler
            err_handler = FileHandler(daily_error_log_path, encoding="utf-8")
            err_handler.setFormatter(formatter)
            err_handler.setLevel(logging.ERROR)
            self._logger.addHandler(err_handler)

            # 4. Console Output Handler
            console_handler = StreamHandler(sys.stdout)
            console_handler.setFormatter(formatter)
            console_handler.setLevel(logging.INFO)
            self._logger.addHandler(console_handler)

            self._logger.propagate = False

        if msg:
            self._logger.info(msg)

    def info(self, msg: str):
        """Logs an INFO level message."""
        self._logger.info(msg)

    def warning(self, msg: str):
        """Logs a WARNING level message."""
        self._logger.warning(msg)

    def debug(self, msg: str):
        """Logs a DEBUG level message."""
        self._logger.debug(msg)

    def error(self, msg: str, exc_info=False):
        """Logs an ERROR level message with optional traceback."""
        self._logger.error(msg, exc_info=exc_info)

    def exception(self, msg: str):
        """Logs an EXCEPTION with full python traceback to daily and error log files."""
        self._logger.exception(msg)
