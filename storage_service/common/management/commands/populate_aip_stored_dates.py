"""Populate the Package.stored_date field for AIPs and AIP replicas.

Currently this works only for AIPs and replicas that are stored in
a local filesystem Space.

AIPs that already have timestamps are ignored and not updated.

Execution example:
./manage.py populate_aip_stored_dates
"""

import logging
import pathlib
from datetime import datetime

from django.core.management.base import CommandError
from django.utils.timezone import get_current_timezone
from locations.models.package import Package
from locations.models.package import Space

from common.management.commands import StorageServiceCommand

# Suppress the logging from models/package.py.
logging.config.dictConfig({"version": 1, "disable_existing_loggers": True})


class Command(StorageServiceCommand):
    help = __doc__

    def add_arguments(self, parser):
        """Entry point to add custom arguments"""
        parser.add_argument(
            "--location-uuid",
            help="UUID for specific AIP Store or Replicator location",
            default=None,
        )

    def handle(self, *args, **options):
        aips = Package.objects.filter(
            package_type=Package.AIP,
            status=Package.UPLOADED,
            current_location__space__access_protocol=Space.LOCAL_FILESYSTEM,
        )
        if not aips:
            raise CommandError("No AIPs with status UPLOADED found")

        location_uuid = options["location_uuid"]
        if location_uuid:
            aips = aips.filter(current_location=location_uuid)

        aips = aips.all()

        aip_count = len(aips)
        success_count = 0
        skipped_count = 0

        tz = get_current_timezone()

        for aip in aips:
            # Skip AIPs that already have datestamps.
            if aip.stored_date is not None:
                skipped_count += 1
                continue

            try:
                modified_unix = pathlib.Path(aip.full_path).stat().st_mtime
            except (TypeError, FileNotFoundError) as err:
                self.error(
                    "Unable to get timestamp for local AIP {}. Details: {}".format(
                        aip.uuid, err
                    )
                )
                continue

            aip.stored_date = datetime.fromtimestamp(int(modified_unix), tz=tz)
            aip.save()
            success_count += 1

        if aip_count == 0:
            self.success("Complete. No matching AIPs found.")
        elif skipped_count == aip_count:
            self.success(
                "Complete. All {} AIPs that already have stored_dates skipped.".format(
                    aip_count
                )
            )
        else:
            self.success(
                "Complete. Datestamps for {} of {} identified AIPs added. {} AIPs that already have stored_dates were skipped.".format(
                    success_count, aip_count, skipped_count
                )
            )
