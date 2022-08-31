# -*- coding: utf-8 -*-
"""Populate Package.checksum and Package.checksum_algorithm fields for AIPs
and AIP replicas.

For compressed AIPs, the SHA256 hash for the package is read from the AIP's
pointer file.

For uncompressed AIPs, a SHA256 hash is computed for the Bag's tagmanifest file
if the AIP is stored in a local filesystem Space. If the --download argument is
used, uncompresed AIPs in remote storage locations (e.g. S3) will be downloaded
and the hash computed. Otherwise, only locally stored uncompressed AIPs will
have the Package.checksum and Package.checksum_algorithm fields populated.

Execution example:
./manage.py populate_aip_checksums
"""
from __future__ import absolute_import, print_function
import os

from django.core.management.base import CommandError

from common.management.commands import StorageServiceCommand
from common import utils
from locations.models.package import Package, Space


class Command(StorageServiceCommand):

    help = __doc__

    def add_arguments(self, parser):
        """Entry point to add custom arguments"""
        parser.add_argument(
            "--location-uuid",
            help="UUID for specific AIP Store or Replicator location",
            default=None,
        )
        parser.add_argument(
            "--download",
            action="store_true",
            help="Download remotely-stored uncompressed AIPs to calculate hash",
            default=False,
        )

    @staticmethod
    def filter_aips_by_local_filesystem(aips):
        """Return only AIPs stored in a local filesystem."""
        return [
            aip
            for aip in aips
            if aip.current_location.space.access_protocol == Space.LOCAL_FILESYSTEM
        ]

    @staticmethod
    def split_aips_by_compression(aips):
        """Return a tuple of (compressed aips, uncompressed_aips)."""
        compressed_aips = []
        uncompressed_aips = []
        for aip in aips:
            if os.path.splitext(aip.current_path)[1] in utils.PACKAGE_EXTENSIONS:
                compressed_aips.append(aip)
            else:
                uncompressed_aips.append(aip)
        return (compressed_aips, uncompressed_aips)

    def handle(self, *args, **options):
        aips = Package.objects.filter(
            package_type=Package.AIP,
            status=Package.UPLOADED,
        )
        if not aips:
            raise CommandError("No AIPs with status UPLOADED found")

        location_uuid = options["location_uuid"]
        if location_uuid:
            aips = aips.filter(current_location=location_uuid)

        aips = aips.all()

        download_aips = options["download"]

        compressed_aips, uncompressed_aips = self.split_aips_by_compression(aips)

        if not download_aips:
            uncompressed_aips = self.filter_aips_by_local_filesystem(uncompressed_aips)

        total_aip_count = len(compressed_aips) + len(uncompressed_aips)
        success_count = 0
        error_count = 0

        for aip in compressed_aips:
            checksum, checksum_algorithm = utils.get_compressed_package_checksum(
                aip.full_pointer_file_path
            )
            if checksum is None:
                self.error(
                    "Unable to retrieve checksum information from pointer file for compressed AIP {}".format(
                        aip.uuid
                    )
                )
                error_count += 1
                continue

            aip.checksum = checksum
            aip.checksum_algorithm = checksum_algorithm
            aip.save()
            self.info(
                "AIP {0} updated with {1} checksum {2}".format(
                    aip.uuid, aip.checksum_algorithm, aip.checksum
                )
            )
            success_count += 1

        for aip in uncompressed_aips:
            local_path = aip.fetch_local_path()
            tagmanifest_path = utils.find_tag_manifest(local_path)

            checksum = utils.generate_checksum(
                tagmanifest_path, Package.DEFAULT_CHECKSUM_ALGORITHM
            ).hexdigest()
            if checksum is None:
                self.error(
                    "Unable to calculate tagmanifest checksum for uncompressed AIP {}".format(
                        aip.uuid
                    )
                )
                error_count += 1
                continue

            aip.checksum = checksum
            aip.checksum_algorithm = Package.DEFAULT_CHECKSUM_ALGORITHM
            aip.save()
            self.info(
                "AIP {0} updated with {1} checksum {2}".format(
                    aip.uuid, aip.checksum_algorithm, aip.checksum
                )
            )
            success_count += 1

        if total_aip_count == 0:
            self.info("Complete. No matching AIPs identified.")
        elif success_count == total_aip_count:
            self.info(
                "Complete. Checksums added for all {} identified AIPs.".format(
                    total_aip_count
                )
            )
        else:
            self.info(
                "Complete. Checksums added for {} of {} identified AIPs. See output for details.".format(
                    success_count, total_aip_count
                )
            )
