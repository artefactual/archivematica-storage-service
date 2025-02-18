"""Process pending package deletion requests.

Use the ``--approve`` argument to approve the pending deletion request corresponding
to the specified package UUID (the package must already have a submitted request).

Use the ``--approve-all`` argument to approve all pending deletion requests.

When run without ``--approve`` or ``--approve-all`` arguments, the command lists all
pending deletion requests without taking any action.
"""

from argparse import ArgumentParser
from typing import Any
from typing import Optional
from typing import cast

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from django.core.management.base import CommandError

from archivematica.storage_service.common.management.commands import (
    StorageServiceCommand,
)
from archivematica.storage_service.locations import package_request
from archivematica.storage_service.locations.models import Event

APPROVAL_REASON = "Approved via Storage Service management command"


class Command(StorageServiceCommand):
    help = __doc__

    def add_arguments(self, parser: ArgumentParser) -> None:
        group = parser.add_mutually_exclusive_group()
        group.add_argument(
            "--approve-all",
            help="Approve all pending deletion requests.",
            action="store_true",
            default=False,
        )
        group.add_argument(
            "--approve",
            help=(
                "Approve the pending deletion of the package with the specified UUID "
                "(a deletion request must already exist)."
            ),
            default=None,
            required=False,
        )
        parser.add_argument(
            "--admin-id",
            help="Admin user ID to record as the reviewer.",
            default=1,
        )

    def handle(self, *args: Any, **options: Any) -> None:
        pending_events = Event.objects.filter(
            status=Event.SUBMITTED, event_type=Event.DELETE
        ).select_related("package")

        approve_all = bool(options.get("approve_all", False))
        approve_uuid = cast(Optional[str], options.get("approve"))
        admin_id_option = options.get("admin_id")

        if approve_all:
            admin = self._get_admin(admin_id_option)
            for event in pending_events.iterator():
                self._approve_event(event, admin=admin)
            return

        if approve_uuid is not None:
            admin = self._get_admin(admin_id_option)
            try:
                event = pending_events.get(package__uuid=approve_uuid)
            except Event.DoesNotExist:
                self.error(
                    f"Error: There is no pending deletion request for package UUID "
                    f"{approve_uuid}"
                )
                return
            self._approve_event(event, admin=admin)
            return

        events_list = list(pending_events)
        for event in events_list:
            self.info(str(event))
        self.info(f"Total deletion requests: {len(events_list)}")

    def _get_admin(self, admin_id_option: object) -> AbstractBaseUser:
        if admin_id_option is None:
            raise CommandError("--admin-id must be provided.")

        if isinstance(admin_id_option, int):
            admin_id = admin_id_option
        elif isinstance(admin_id_option, str):
            try:
                admin_id = int(admin_id_option)
            except ValueError as exc:
                raise CommandError("--admin-id must be an integer.") from exc
        else:
            raise CommandError("--admin-id must be an integer.")

        user_model = cast(Any, get_user_model())

        try:
            user = user_model.objects.get(pk=admin_id)
        except user_model.DoesNotExist as exc:
            raise CommandError(
                f"Admin user with id {admin_id} does not exist."
            ) from exc
        return cast(AbstractBaseUser, user)

    def _approve_event(self, event: Event, *, admin: AbstractBaseUser) -> None:
        config = package_request.PackageDeletionRequestHandlerConfig()
        self.info(f"Processing package {event.package.uuid}")
        result = package_request.process_package_request_decision(
            config,
            event,
            package_request.PackageRequestDecision.APPROVE,
            reason=APPROVAL_REASON,
            admin=admin,
        )
        self._log_message(result.message)

    def _log_message(self, message: package_request.PackageRequestMessage) -> None:
        content = str(message.content)
        if message.level == "error":
            self.error(content)
        elif message.level == "success":
            self.success(content)
        if message.detail:
            self.info(str(message.detail))
