from django.apps import AppConfig


class LocationsAppConfig(AppConfig):
    default_auto_field = "django.db.models.AutoField"
    name = "archivematica.storage_service.locations"

    def ready(self):
        import archivematica.storage_service.locations.signals  # noqa: F401
