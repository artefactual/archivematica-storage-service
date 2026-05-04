"""Repair pointer files for uploaded compressed AIP replicas.

This command repairs uploaded replica AIPs whose pointer file metadata still
points at the original AIP's pointer XML, or whose replica-specific pointer XML
is missing. It is intended for data repair before deleting affected replicas, so
replica deletion removes only the replica pointer file and does not remove the
original AIP pointer file.

The command uses the original AIP pointer as the source for compression metadata
and package subtype, fetches the replica package content to calculate a current
checksum, then asks the Package model to create the replica pointer file. The
repaired pointer contains the replica UUID, current replica path, PREMIS
relationship back to the original AIP, replica creation event, and replication
validation event.

During normal replication, the Package model also updates the original AIP
pointer with a replication event and a derivation relationship to the replica.
This command recreates the replica-to-original AIP reference in the replica
pointer, but it does not recreate the opposite original-to-replica reference in
the original AIP pointer. Its scope is to give each live replica its own pointer
file so future replica deletion does not remove the original AIP pointer.
Reconstructing original-side replication relationships from live replica rows
would require a separate repair and would still create synthetic event UUIDs and
timestamps.

The recreated pointer is operationally equivalent, not historically identical.
It cannot recover the original replica pointer's event UUIDs, timestamps, or
original validation text unless that information is available from another
source.

The command is batch-oriented: without UUID arguments it scans all uploaded
replicas, and with UUID arguments it can repair one or more specific replicas.

Examples:
    Repair all eligible uploaded replicas with missing or shared pointer files:
    $ python manage.py repair_replica_pointer_files

    Repair one specific uploaded replica:
    $ python manage.py repair_replica_pointer_files 5658e603-277b-4292-9b58-20bf261c8f88

    Repair multiple specific uploaded replicas:
    $ python manage.py repair_replica_pointer_files <uuid1> <uuid2>

    Repair eligible uploaded replicas in one storage location:
    $ python manage.py repair_replica_pointer_files --location-uuid <location-uuid>

    Force a rewrite for a specific uploaded replica even when its replica
    pointer XML file already exists. Without --force, the command skips replicas
    that already have their own pointer XML on disk:
    $ python manage.py repair_replica_pointer_files --force <uuid>
"""

import pathlib
import uuid
from argparse import RawDescriptionHelpFormatter
from typing import Any

import metsrw
from django.core.management.base import CommandError
from django.core.management.base import DjangoHelpFormatter

from archivematica.storage_service.common import premis
from archivematica.storage_service.common import utils
from archivematica.storage_service.common.management.commands import (
    StorageServiceCommand,
)
from archivematica.storage_service.locations.models import Package
from archivematica.storage_service.locations.models.package import write_pointer_file


class RawDescriptionDjangoHelpFormatter(
    DjangoHelpFormatter, RawDescriptionHelpFormatter
):
    """Preserve command help paragraphs while keeping Django option ordering."""


def _shares_pointer_file(replica: Package, original: Package) -> bool:
    return (
        replica.pointer_file_location_id == original.pointer_file_location_id
        and replica.pointer_file_path == original.pointer_file_path
    )


def _checksum_report(
    original_checksum: str,
    original_uuid: uuid.UUID,
    replica_checksum: str,
    replica_uuid: uuid.UUID,
    algorithm: str,
) -> dict[str, bool | str]:
    success = replica_checksum == original_checksum
    if success:
        message = (
            f"Original AIP {original_uuid} and replica AIP {replica_uuid} both"
            f" have checksum {original_checksum} when using algorithm {algorithm}."
        )
    else:
        message = (
            f"Using algorithm {algorithm}, original AIP {original_uuid} has checksum"
            f" {original_checksum} while replica AIP {replica_uuid} has checksum"
            f" {replica_checksum}."
        )
    return {"success": success, "message": message}


class Command(StorageServiceCommand):
    help = __doc__

    def create_parser(self, prog_name: str, subcommand: str, **kwargs: Any) -> Any:
        kwargs.setdefault("formatter_class", RawDescriptionDjangoHelpFormatter)
        return super().create_parser(prog_name, subcommand, **kwargs)

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "replica_uuids",
            nargs="*",
            type=uuid.UUID,
            help="Specific replica AIP UUIDs to repair.",
        )
        parser.add_argument(
            "--location-uuid",
            type=uuid.UUID,
            help="Only repair replicas in a specific storage location.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Rewrite replica pointer files even when the XML already exists.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        replicas = Package.objects.filter(
            package_type__in=(Package.AIP, Package.AIC),
            replicated_package__isnull=False,
            replicated_package__status=Package.UPLOADED,
            status=Package.UPLOADED,
        )

        replica_uuids = options["replica_uuids"]
        if replica_uuids:
            replicas = replicas.filter(uuid__in=replica_uuids)

        location_uuid = options["location_uuid"]
        if location_uuid:
            replicas = replicas.filter(current_location=location_uuid)

        total = repaired = skipped = 0
        for replica in replicas:
            total += 1
            if self._repair_pointer_file(replica, force=options["force"]):
                repaired += 1
            else:
                skipped += 1

        self.success(
            f"Processed {total} uploaded replicas; repaired {repaired}; skipped {skipped}."
        )

    def _repair_pointer_file(self, replica: Package, *, force: bool) -> bool:
        if not utils.package_is_file(replica.current_path):
            self.info(f"Skipping uncompressed replica {replica.uuid}.")
            return False

        original = replica.replicated_package
        if original is None:
            self.info(f"Skipping package {replica.uuid}; it is not a replica.")
            return False

        original_pointer_path = original.full_pointer_file_path
        if (
            not original_pointer_path
            or not pathlib.Path(original_pointer_path).is_file()
        ):
            self.warning(
                f"Skipping replica {replica.uuid}; original AIP {original.uuid} does "
                "not have pointer XML on disk."
            )
            return False

        shared_pointer = _shares_pointer_file(replica, original)
        replica_pointer_path = replica.full_pointer_file_path
        replica_pointer_exists = bool(
            replica_pointer_path and pathlib.Path(replica_pointer_path).is_file()
        )
        if replica_pointer_exists and not shared_pointer and not force:
            self.info(
                f"Skipping replica {replica.uuid}; replica pointer file already exists."
            )
            return False

        try:
            # Package.replicate normally creates the replica pointer while the
            # replica is still staged locally. This repair follows the same
            # Package.create_replica_pointer_file path, but fetches the uploaded
            # replica back to local storage first so it can create the validation
            # event from the current replica bytes.
            original_pointer = metsrw.METSDocument.fromfile(original_pointer_path)
            original_fsentry = original_pointer.get_file(file_uuid=str(original.uuid))
            original_premis_object = original_fsentry.get_premis_objects()[0]
            checksum_algorithm = original_premis_object.message_digest_algorithm
            original_checksum = original_premis_object.message_digest

            replica_local_path = replica.fetch_local_path()
            replica_checksum = utils.generate_checksum(
                replica_local_path, checksum_algorithm
            ).hexdigest()
            replica.size = utils.recalculate_size(replica_local_path)
            replica.checksum = replica_checksum
            replica.checksum_algorithm = checksum_algorithm

            checksum_report = _checksum_report(
                original_checksum,
                original.uuid,
                replica_checksum,
                replica.uuid,
                checksum_algorithm,
            )
            replication_validation_event = premis.create_replication_validation_event(
                replica.uuid,
                checksum_report=checksum_report,
                master_aip_uuid=original.uuid,
            )
            replica_pointer_file = original.create_replica_pointer_file(
                replica,
                uuid.uuid4(),
                replication_validation_event,
                master_ptr=original_pointer,
            )
            if replica_pointer_file is None:
                raise CommandError(
                    f"Unable to create pointer file for replica {replica.uuid}"
                )

            repaired_pointer_path = replica.full_pointer_file_path
            if not repaired_pointer_path:
                raise CommandError(
                    f"Unable to determine pointer path for replica {replica.uuid}"
                )

            write_pointer_file(replica_pointer_file, repaired_pointer_path)
            replica.save()
            self.success(f"Repaired pointer file for replica {replica.uuid}.")
            return True
        finally:
            replica.clear_local_tempdirs()
