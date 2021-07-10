from django.apps import AppConfig


class CommonAppConfig(AppConfig):
    name = "common"

    def ready(self):
        import common.signals  # noqa: F401
