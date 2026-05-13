"""Reconcile storage Location.used and Space.used counters.

This command recalculates the database counters from the packages currently
stored in AIP Storage, DIP Storage, and Replicator locations. It is useful
after moving packages through paths that changed Package.current_location
without updating the persisted location and space usage counters.

The Storage Service database is treated as the source of truth. Package sizes
are counted from Package.size and Package.current_location only when the package
is in a status that should still occupy storage: STAGING, UPLOADED, VERIFIED,
DEL_REQ, MOVING, or RECOVER_REQ.

Location.used is reconciled for AIP Storage, DIP Storage, and Replicator
locations only.
Space.used is adjusted by the same net delta applied to the selected locations.
This avoids recalculating unrelated locations in the same space.

Packages in PENDING, FAIL, DELETED, or FINALIZE are not counted. PENDING and
FAIL are excluded because the package may not be in final storage. DELETED is
excluded because the package was removed. FINALIZE is deposit-specific and is
not considered part of AIP/DIP storage usage.

Execution examples:
./manage.py reconcile_location_sizes --dry-run
./manage.py reconcile_location_sizes --location-uuid <location_uuid>
"""

from dataclasses import dataclass

from django.core.management.base import CommandError
from django.db.models import BigIntegerField
from django.db.models import Sum
from django.db.models import Value
from django.db.models.functions import Coalesce

from archivematica.storage_service.common.management.commands import (
    StorageServiceCommand,
)
from archivematica.storage_service.locations.models import Location
from archivematica.storage_service.locations.models import Package

LOCATION_PURPOSES_TO_RECONCILE = (
    Location.AIP_STORAGE,
    Location.DIP_STORAGE,
    Location.REPLICATOR,
)
PACKAGE_STATUSES_TO_COUNT = (
    Package.STAGING,
    Package.UPLOADED,
    Package.VERIFIED,
    Package.DEL_REQ,
    Package.MOVING,
    Package.RECOVER_REQ,
)


@dataclass(frozen=True)
class CounterChange:
    kind: str
    uuid: str
    current: int
    expected: int

    @property
    def changed(self):
        return self.current != self.expected

    @property
    def delta(self):
        return self.expected - self.current


def _package_size_sum(packages):
    return packages.aggregate(
        total=Coalesce(Sum("size"), Value(0), output_field=BigIntegerField())
    )["total"]


def expected_location_used(location):
    return _package_size_sum(
        Package.objects.filter(
            current_location=location,
            status__in=PACKAGE_STATUSES_TO_COUNT,
        )
    )


class Command(StorageServiceCommand):
    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument(
            "--location-uuid",
            help=(
                "UUID for a specific AIP Storage, DIP Storage, or Replicator "
                "location."
            ),
            default=None,
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only print the counter changes that would be applied.",
        )

    def handle(self, *args, **options):
        locations = Location.objects.filter(purpose__in=LOCATION_PURPOSES_TO_RECONCILE)

        location_uuid = options["location_uuid"]
        if location_uuid:
            locations = locations.filter(uuid=location_uuid)

        locations = list(locations.select_related("space"))
        if not locations:
            raise CommandError(
                "No AIP Storage, DIP Storage, or Replicator locations found."
            )

        dry_run = options["dry_run"]
        changes = []
        space_deltas = {}
        spaces = {}

        for location in locations:
            change = CounterChange(
                kind="location",
                uuid=str(location.uuid),
                current=location.used,
                expected=expected_location_used(location),
            )
            changes.append(change)
            space_uuid = str(location.space.uuid)
            spaces[space_uuid] = location.space
            space_deltas[space_uuid] = space_deltas.get(space_uuid, 0) + change.delta

        for space_uuid, delta in space_deltas.items():
            space = spaces[space_uuid]
            changes.append(
                CounterChange(
                    kind="space",
                    uuid=space_uuid,
                    current=space.used,
                    expected=space.used + delta,
                )
            )

        changed = [change for change in changes if change.changed]
        for change in changed:
            action = "would update" if dry_run else "updated"
            self.info(
                f"{change.kind} {change.uuid}: {action} used from {change.current} to {change.expected}"
            )

        if not dry_run:
            locations_by_uuid = {str(location.uuid): location for location in locations}
            for change in changed:
                if change.kind == "location":
                    location = locations_by_uuid[change.uuid]
                    location.used = change.expected
                    location.save(update_fields=["used"])
                else:
                    space = spaces[change.uuid]
                    space.used = change.expected
                    space.save(update_fields=["used"])

        unchanged = len(changes) - len(changed)
        self.success(
            f"Reconciliation complete. Checked {len(changes)} counters: {len(changed)} changed, {unchanged} already matched."
        )
