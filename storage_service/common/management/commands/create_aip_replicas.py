"""(Re)create replicas in an AIP store

When called with the -d/--delete argument, this command will attempt to
delete existing replicas of AIPs in the specified AIP Store location
prior to creating new replicas.

If an AIP Store location is not specified with the --location argument,
the task will create replicas for all AIPs in the default AIP Storage
location.

Execution example:
./manage.py create_aip_replicas --location <UUID>
"""
import logging

from django.core.management.base import CommandError

from administration.models import Settings
from common.management.commands import StorageServiceCommand
from locations.models.package import Package

# Suppress the logging from models/package.py.
logging.config.dictConfig({"version": 1, "disable_existing_loggers": True})


class ReplicaDeleteException(Exception):
    pass


def get_replica_count(aip_uuid):
    """Return number of replicas for given AIP

    :param aip_uuid: AIP UUID

    :returns: Number of replicas (int)
    """
    return Package.objects.filter(
        replicated_package=aip_uuid, status=Package.UPLOADED
    ).count()


class Command(StorageServiceCommand):

    help = __doc__

    def add_arguments(self, parser):
        """Entry point to add custom arguments"""
        parser.add_argument(
            "--aip-uuid",
            help="UUID for specific AIP to create replicas of",
            default=None,
        )
        parser.add_argument(
            "-d",
            "--delete",
            action="store_true",
            help="Delete existing replicas in AIP Store location"
            " prior to creating new replicas.",
        )
        parser.add_argument(
            "--aip-store-location",
            help="UUID for AIP Storage location to create replicas",
            default=None,
        )
        parser.add_argument(
            "--replicator-location",
            help="UUID for Replicator location to create replicas"
            " Defaults to all configured Replicators for AIP Store.",
        )

    def handle(self, *args, **options):
        delete_existing_replicas = False
        if options["delete"]:
            delete_existing_replicas = True

        # Determine AIP storage location for which we'll be creating
        # replicas. Use default AIP Store if user did not supply a UUID.
        aip_store_uuid = options["aip_store_location"]
        if aip_store_uuid is None:
            try:
                default_aip_store = Settings.objects.get(name="default_AS_location")
                aip_store_uuid = default_aip_store.value
            except Settings.DoesNotExist:
                raise CommandError("No AIP Store location specified or set as default.")

        aip_uuid = options["aip_uuid"]
        replicator_uuid = options["replicator_location"]

        aips = Package.objects.filter(
            current_location=aip_store_uuid,
            package_type=Package.AIP,
            replicated_package=None,
            status=Package.UPLOADED,
        ).all()
        if aip_uuid:
            aips = aips.filter(uuid=aip_uuid)
        if not aips:
            raise CommandError(f"No AIPs to replicate in location {aip_store_uuid}")

        aips_count = len(aips)
        success_count = 0
        deleted_count = 0

        self.info(f"AIPs to replicate: {aips_count}")

        for aip in aips:
            if delete_existing_replicas:
                self.info(f"Deleting existing replicas of AIP {aip.uuid}")
                aip_deleted_replicas_count = self._delete_replicas(
                    aip.uuid, replicator_uuid
                )
                deleted_count += aip_deleted_replicas_count

            replicas_initial_count = get_replica_count(aip.uuid)

            self.info(f"Creating new replicas for AIP {aip.uuid}")
            aip.create_replicas(replicator_uuid=replicator_uuid, delete_replicas=False)

            # Validate that new replicas were created.
            replicas_count = get_replica_count(aip.uuid)
            if not replicas_count > replicas_initial_count:
                self.error(f"Replicas not created for AIP {aip.uuid}")
                continue

            self.info(f"AIP {aip.uuid} successfully replicated")
            success_count += 1

        self.success(
            "Replica creation complete. {} existing replicas deleted. "
            "New replicas created for {} of {} AIPs in location.".format(
                deleted_count, success_count, aips_count
            )
        )

    def _delete_replicas(self, aip_uuid, replicator_uuid):
        """Delete all existing replicas of an AIP

        :param aip_uuid: UUID of AIP whose replicas we are deleting.
        :param replicator_uuid: UUID of Replicator in which to delete AIP
            replicas.

        :returns: Number of replicas deleted (int)
        """
        deleted_count = 0
        existing_replicas = Package.objects.filter(
            replicated_package=aip_uuid, status=Package.UPLOADED
        ).all()
        if replicator_uuid:
            existing_replicas = existing_replicas.filter(
                current_location__uuid=replicator_uuid
            )
        for replica in existing_replicas:
            try:
                self._delete_replica(replica)
                deleted_count += 1
            except ReplicaDeleteException as err:
                self.error(
                    "Unable to delete existing replica {} of AIP {}: {}".format(
                        replica.uuid, aip_uuid, err
                    )
                )
        return deleted_count

    def _delete_replica(self, replica):
        """Delete replica from filesystem and update Package status

        If filesystem deletion is successful, the replica's status will be
        set to Package.DELETED by `replica.delete_from_storage()`.

        :param replica: Package object of replicated AIP to delete.
        """
        fs_deletion = replica.delete_from_storage()
        fs_deletion_success = fs_deletion[0]
        if not fs_deletion_success:
            error_msg = fs_deletion[1]
            raise ReplicaDeleteException(error_msg)
