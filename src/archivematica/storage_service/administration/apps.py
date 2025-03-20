from django.apps import AppConfig
from django.contrib.auth import get_user_model


class AdministrationAppConfig(AppConfig):
    default_auto_field = "django.db.models.AutoField"
    name = "administration"

    def ready(self):
        from . import roles

        User = get_user_model()
        User.add_to_class("get_role", roles.get_user_role)
        User.add_to_class("get_role_label", roles.get_user_role_label)
        User.add_to_class("set_role", roles.set_user_role)
        User.add_to_class("is_admin", roles.is_admin)
