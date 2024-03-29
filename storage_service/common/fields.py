import uuid

from django.db import models


class UUIDField(models.UUIDField):
    """Customize Django's UUIDField default behaviour.

    This subclass maintains backward compatibility with django-extension's
    UUIDField data to avoid data migrations.

    By default, Django's UUIDField stores UUIDs as CHAR(32) columns with
    hexadecimal digits only. This subclass stores the hyphens as well using
    VARCHAR(36) columns instead.
    """

    def __init__(self, *args, **kwargs):
        kwargs["max_length"] = 36
        models.Field.__init__(self, *args, **kwargs)

    def db_type(self, connection):
        return "varchar(%s)" % self.max_length

    def get_db_prep_value(self, value, connection, prepared=False):
        if value is None:
            return None
        if not isinstance(value, uuid.UUID):
            value = self.to_python(value)

        if connection.features.has_native_uuid_field:
            return value
        return str(value)
