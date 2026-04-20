"""Set the replication failure flag for a Replicator location.

When called without ``--id``, this command will automatically select the
single Replicator location available in the database. If multiple Replicator
locations exist, use ``--id=<UUID>`` to indicate which one should be updated.

Execution examples:
./manage.py set_replica_to_fail true
./manage.py set_replica_to_fail false --id <UUID>
"""

from django.core.management.base import CommandError

from archivematica.storage_service.common.management.commands import (
    StorageServiceCommand,
)
from archivematica.storage_service.locations.models import Location


class Command(StorageServiceCommand):
    help = __doc__

    TRUE_VALUES = {"1", "true", "t", "yes", "y", "on"}
    FALSE_VALUES = {"0", "false", "f", "no", "n", "off"}

    def add_arguments(self, parser):
        parser.add_argument(
            "value",
            help="Whether replication to the selected Replicator should fail.",
        )
        parser.add_argument(
            "--id",
            help="UUID for the Replicator location to update.",
            default=None,
        )

    def handle(self, *args, **options):
        value = self._parse_bool(options["value"])
        replicator = self._get_replicator(options["id"])
        replicator.fail_replication = value

        self.success(
            f"Replicator {replicator.uuid} fail_replication set to {value}."
        )

    def _parse_bool(self, value):
        normalized = value.strip().lower()
        if normalized in self.TRUE_VALUES:
            return True
        if normalized in self.FALSE_VALUES:
            return False
        raise CommandError(
            f"Invalid value {value!r}. Expected one of: true, false, 1, 0, yes, no, on, off."
        )

    def _get_replicator(self, replicator_uuid):
        replicators = Location.objects.filter(purpose=Location.REPLICATOR).order_by(
            "uuid"
        )

        if replicator_uuid:
            try:
                return replicators.get(uuid=replicator_uuid)
            except Location.DoesNotExist as exc:
                raise CommandError(
                    f"No Replicator location found with id {replicator_uuid}."
                ) from exc

        count = replicators.count()
        if count == 0:
            raise CommandError("No Replicator locations found.")
        if count == 1:
            return replicators.get()

        self.info("Replicators found:")
        for replicator in replicators:
            self.info(f"  {replicator}")
        raise CommandError(
            "can't choose a replicator, pass --id=<uuid> to indicate which"
        )
