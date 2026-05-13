"""Reconcile pointer file location hrefs for stored compressed AIPs and AICs.

This command updates existing pointer files so their METS FLocat href points
at the package's current full path. It is useful after changing an AIP store
path or moving packages when existing pointer files still refer to the old
storage path.

The Storage Service database is treated as the source of truth. The expected
href is built from Package.current_location and Package.current_path via
Package.full_path; this command does not discover package paths from disk.

Only uploaded AIPs and AICs with pointer-file database fields are reconciled.
Deleted, failed, and uncompressed package rows are ignored. Missing pointer
files are skipped so otherwise stale package rows do not stop the full
reconciliation.

Execution examples:
./manage.py reconcile_pointer_file_locations --dry-run
./manage.py reconcile_pointer_file_locations --location-uuid <location_uuid>
"""

from dataclasses import dataclass
from pathlib import Path

from django.core.management.base import CommandError
from lxml import etree

from archivematica.storage_service.common import utils
from archivematica.storage_service.common.management.commands import (
    StorageServiceCommand,
)
from archivematica.storage_service.locations.models import Location
from archivematica.storage_service.locations.models import Package

PACKAGE_TYPES_TO_RECONCILE = (Package.AIP, Package.AIC)


@dataclass(frozen=True)
class PointerChange:
    uuid: str
    pointer_path: str
    current: str
    expected: str
    skipped: str = ""

    @property
    def changed(self):
        return not self.skipped and self.current != self.expected


def pointer_file_href(package):
    pointer_path = Path(package.full_pointer_file_path)
    if not pointer_path.exists():
        raise FileNotFoundError(package.full_pointer_file_path)

    root = etree.parse(str(pointer_path))
    for element in root.findall(".//mets:file", namespaces=utils.NSMAP):
        flocat = element.find("mets:FLocat", namespaces=utils.NSMAP)
        if str(package.uuid) in element.get("ID", "") and flocat is not None:
            return flocat.get(f"{{{utils.NSMAP['xlink']}}}href") or ""
    raise CommandError(f"Pointer file for package {package.uuid} has no AIP FLocat.")


class Command(StorageServiceCommand):
    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument(
            "--location-uuid",
            help="UUID for a specific AIP Storage location.",
            default=None,
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only print the pointer file changes that would be applied.",
        )

    def handle(self, *args, **options):
        packages = Package.objects.filter(
            package_type__in=PACKAGE_TYPES_TO_RECONCILE,
            status=Package.UPLOADED,
            current_location__purpose=Location.AIP_STORAGE,
            pointer_file_location__isnull=False,
            pointer_file_path__isnull=False,
        )
        packages = packages.exclude(pointer_file_path__isnull=True).exclude(
            pointer_file_path=""
        )

        location_uuid = options["location_uuid"]
        if location_uuid:
            packages = packages.filter(current_location=location_uuid)

        packages = list(
            packages.select_related(
                "current_location__space",
                "pointer_file_location__space",
            )
        )
        if not packages:
            raise CommandError("No uploaded AIPs or AICs with pointer files found.")

        dry_run = options["dry_run"]
        results = []
        failed = []

        for package in packages:
            try:
                result = PointerChange(
                    uuid=str(package.uuid),
                    pointer_path=package.full_pointer_file_path,
                    current=pointer_file_href(package),
                    expected=package.full_path,
                )
            except FileNotFoundError as err:
                result = PointerChange(
                    uuid=str(package.uuid),
                    pointer_path=package.full_pointer_file_path,
                    current="",
                    expected=package.full_path,
                    skipped=f"pointer file not found: {err.filename}",
                )
            except (OSError, etree.XMLSyntaxError, CommandError) as err:
                failed.append(package.uuid)
                result = PointerChange(
                    uuid=str(package.uuid),
                    pointer_path=package.full_pointer_file_path,
                    current="",
                    expected=package.full_path,
                    skipped=str(err),
                )

            results.append(result)
            self._print_result(result, dry_run=dry_run)

            if result.changed and not dry_run:
                package._update_existing_ptr_loc_info()

        changed = sum(1 for result in results if result.changed)
        unchanged = sum(
            1 for result in results if not result.changed and not result.skipped
        )
        skipped = sum(1 for result in results if result.skipped)
        message = (
            f"Reconciliation complete. Processed {len(results)} pointer files: "
            f"{changed} changed, {unchanged} already matched, {skipped} skipped"
        )
        if failed:
            self.error(f"{message}.")
            raise CommandError(f"{len(failed)} pointer files could not be reconciled.")

        self.success(f"{message}.")

    def _print_result(self, result, dry_run):
        if result.skipped:
            self.warning(f"{result.uuid}: skipped, {result.skipped}.")
            return

        if not result.changed:
            if not dry_run:
                self.info(f"{result.uuid}: pointer file already matched.")
            return

        prefix = "would update" if dry_run else "updated"
        self.info(f"{result.uuid}: {prefix} pointer href")
        self.info(f"  {result.current!r} -> {result.expected!r}")
