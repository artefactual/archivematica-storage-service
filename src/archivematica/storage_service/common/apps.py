from django.apps import AppConfig
from prometheus_client import Info

from storage_service import __version__

version_info = Info("version", "Archivematica Storage Service version info")


class CommonAppConfig(AppConfig):
    default_auto_field = "django.db.models.AutoField"
    name = "common"

    def ready(self):
        import common.signals  # noqa: F401

        version_info.info({"version": __version__})
