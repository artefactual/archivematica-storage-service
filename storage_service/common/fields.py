import uuid

from django.db import models


class UUIDField(models.UUIDField):
    def __init__(self, *args, **kwargs):
        kwargs["max_length"] = 36
        models.Field.__init__(self, *args, **kwargs)

    def get_db_prep_value(self, value, connection, prepared=False):
        if value is None:
            return None
        if not isinstance(value, uuid.UUID):
            value = self.to_python(value)

        if connection.features.has_native_uuid_field:
            return value
        return str(value)
