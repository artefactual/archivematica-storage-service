"""Add description to default transfer source location."""
import ast

from django.db import migrations

# We can't use apps.get_model for this model as we need to access class
# attributes.
from locations.models import Location


DEFAULT_DESCRIPTION = "Default transfer source"


def get_default_transfer_source_location_uuids(apps):
    """Get the UUID of the default transfer source location.

    There are two `administration.models.Settings` that track the
    default transfer source location:

    * `default_transfer_source` which is stored as an `ast` parseable
      list of UUIDs

    * `default_TS_location` which is stored as a UUID string

    Since it is possible they get out of sync, we get them both here.
    """
    Settings = apps.get_model("administration", "Settings")
    result = set()
    for setting in Settings.objects.filter(
        name__in=["default_transfer_source", "default_TS_location"]
    ):
        try:
            value = ast.literal_eval(setting.value)
        except (ValueError, SyntaxError):
            value = [setting.value]
        result.update(value)
    return result


def data_migration_down(apps, schema_editor):
    Location.objects.filter(
        purpose=Location.TRANSFER_SOURCE,
        uuid__in=get_default_transfer_source_location_uuids(apps),
        description=DEFAULT_DESCRIPTION,
        enabled=True,
    ).update(description="")


def data_migration_up(apps, schema_editor):
    Location.objects.filter(
        purpose=Location.TRANSFER_SOURCE,
        uuid__in=get_default_transfer_source_location_uuids(apps),
        description="",
        enabled=True,
    ).update(description=DEFAULT_DESCRIPTION)


class Migration(migrations.Migration):

    dependencies = [("locations", "0026_update_package_status")]

    operations = [migrations.RunPython(data_migration_up, data_migration_down)]
