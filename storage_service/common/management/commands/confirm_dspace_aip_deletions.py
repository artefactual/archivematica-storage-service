from __future__ import absolute_import, print_function

from django.contrib import auth

from common.management.commands import StorageServiceCommand
from locations.models.event import Event
from locations.models.package import Package

User = auth.get_user_model()


def confirm_package_deletion(event, admin_id):
    """Confirm package deletion request."""
    event.status = Event.APPROVED
    event.status_reason = "Package deletion bulk approved."
    event.admin_id = User.objects.get(pk=admin_id)

    success, err_msg = event.package.delete_from_storage()
    if not success:
        event.status = Event.SUBMITTED
        print(
            "ERROR: Package {} not deleted from disk correctly - {}".format(
                event.package.uuid, err_msg
            )
        )
    else:
        event.package.status = Package.DELETED
        print("Package {} deleted successfully".format(event.package.uuid))

    event.save()
    event.package.save()


class Command(StorageServiceCommand):

    help = __doc__

    def add_arguments(self, parser):
        """Entry point to add custom arguments"""
        parser.add_argument(
            "--admin-id",
            help="ID for admin user to confirm deletions as",
            default=1,
        )

    def handle(self, *args, **options):
        """Approve pending AIP deletion requests."""
        request_events = Event.objects.filter(status=Event.SUBMITTED).filter(
            event_type=Event.DELETE
        )
        for event in request_events:
            if (
                event.package.package_type == Package.AIP
                and event.event_reason.startswith("Superceded by newer AIP")
            ):
                confirm_package_deletion(event, options["admin_id"])
