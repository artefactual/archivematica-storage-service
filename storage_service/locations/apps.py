from django.apps import AppConfig


class LocationsAppConfig(AppConfig):
    default_auto_field = "django.db.models.AutoField"
    name = "locations"

    def ready(self):
        import locations.signals  # noqa: F401
