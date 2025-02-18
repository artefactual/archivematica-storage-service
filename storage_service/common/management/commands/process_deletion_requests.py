"""Process pending package deletion requests

Use the ``--approve`` argument to approve the deletion request corresponding to the
specified package uuid (package should have a deletion request already submitted)

Use the ``--approve-all`` argument to approve all pending deletion requests

When run without ``--approve`` or ``--approve-all`` arguments, the command will
list all pending deletion requests but no action taken on them


"""

from django.contrib.auth import get_user_model
from locations.models.event import Event
from locations.models.package import Package

from common.management.commands import StorageServiceCommand

User = get_user_model()


class Command(StorageServiceCommand):
    help = __doc__

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group()
        group.add_argument(
            "--approve-all",
            help="Approve all pending deletion requests.",
            action="store_true",
            default=False,
        )
        group.add_argument(
            "--approve",
            help="Approve pending deletion of package with the specified UUID"
            " (package should have a deletion request already submitted)",
            default=None,
            required=False,
        )
        parser.add_argument(
            "--admin-id",
            help="admin id used to process deletion request",
            default=1,
        )

    def __approve_deletion_request(self, event, admin_id):
        # Change status of deletion request event to APPROVED
        event.status = Event.APPROVED
        event.status_reason = "Approved via Storage Service management command"
        event.admin_id = User.objects.get(pk=admin_id)
        event.save()
        self.info(f"Package {event.package.uuid} deletion request approved")

        # Delete package from Storage Service location
        success, err_msg = event.package.delete_from_storage()
        if not success:
            self.error(
                f"Error: Package {event.package.uuid} deletion failed: {err_msg}"
            )
        else:
            # Update package status to DELETED if package deletion was successful
            event.package.status = Package.DELETED
            self.success(f"Package {event.package.uuid} deleted successfully")
            event.package.save()

    def handle(self, *args, **options):
        # queryset for list of submitted deletion requests
        q1 = Event.objects.filter(status=Event.SUBMITTED).filter(
            event_type=Event.DELETE
        )

        if options["approve_all"] is True:
            for req in q1:
                # Approve deletion request and delete package from storage
                self.__approve_deletion_request(req, options["admin_id"])

        elif options["approve"] is not None:
            uuid = options["approve"]
            try:
                # check that specified uuid is in the list of deletion requests
                q2 = q1.get(package__uuid=uuid)
            except Event.DoesNotExist:
                self.error(
                    f"Error: There is no deletion request for package uuid {uuid}"
                )
            except Exception as e:
                self.error(f"Error: {e}")
            else:
                # Approve deletion request and delete package from storage
                self.__approve_deletion_request(q2, options["admin_id"])
        else:
            # just print deletion request information
            for req in q1:
                self.info(f"{req}")
            self.info(f"Total deletion requests: {len(q1)}")
