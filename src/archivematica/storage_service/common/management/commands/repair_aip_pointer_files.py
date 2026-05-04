"""Repair missing pointer files for uploaded compressed AIPs.

This command recreates the Storage Service pointer file for uploaded original
AIPs whose package content still exists but whose pointer XML is missing. It is
intended for data repair after a replica deletion removed a pointer file shared
with its original AIP.

The recreated pointer is operationally equivalent, not historically identical.
It can regenerate the METS wrapper, black-box AIP file reference, decompression
transform, PREMIS object, PREMIS compression event, and Storage Service PREMIS
agent needed for extraction and related Storage Service API operations. Those
values are reconstructed from the current Package row, the stored package path,
the stored package bytes, and compression details inferred from the package
format.

The command cannot recreate provenance that only existed in the deleted pointer
file or in external logs/backups. New METS IDs and timestamps may differ from the
original. Package subtype, encryption transforms, encryption inhibitors,
Archivematica-provided agents, original compression event UUID/timestamp/output,
historical replication events, and replica-specific pointer content cannot be
reliably regenerated unless that information is available from another source.

The command is batch-oriented: without UUID arguments it scans all uploaded
original AIPs, and with UUID arguments it can repair one or more specific AIPs.

Examples:
    Repair all eligible uploaded original AIPs with missing pointer files:
    $ python manage.py repair_aip_pointer_files

    Repair one specific uploaded original AIP:
    $ python manage.py repair_aip_pointer_files 5658e603-277b-4292-9b58-20bf261c8f88

    Repair multiple specific uploaded original AIPs:
    $ python manage.py repair_aip_pointer_files <uuid1> <uuid2>

    Repair eligible uploaded original AIPs in one storage location:
    $ python manage.py repair_aip_pointer_files --location-uuid <location-uuid>

    Report eligible uploaded original AIPs whose pointer XML is missing without
    writing pointer files or fetching AIP content:
    $ python manage.py repair_aip_pointer_files --dry-run

    Force a rewrite for a specific uploaded original AIP even when its pointer
    XML file already exists. Without --force, the command skips AIPs that
    already have pointer XML on disk:
    $ python manage.py repair_aip_pointer_files --force <uuid>
"""

import pathlib
import shutil
import subprocess
import tarfile
import tempfile
import uuid
from argparse import RawDescriptionHelpFormatter
from typing import Any

from django.core.management.base import CommandError
from django.core.management.base import DjangoHelpFormatter
from lxml import etree

from archivematica.storage_service.common import premis
from archivematica.storage_service.common import utils
from archivematica.storage_service.common.management.commands import (
    StorageServiceCommand,
)
from archivematica.storage_service.locations.models import Location
from archivematica.storage_service.locations.models import Package
from archivematica.storage_service.locations.models.package import write_pointer_file

_SEVEN_ZIP_ALGORITHMS = {
    utils.COMPRESSION_7Z_BZIP: utils.COMPRESS_ALGO_BZIP2,
    utils.COMPRESSION_7Z_LZMA: utils.COMPRESS_ALGO_LZMA,
    utils.COMPRESSION_7Z_COPY: utils.COMPRESS_ALGO_7Z_COPY,
}


class RawDescriptionDjangoHelpFormatter(
    DjangoHelpFormatter, RawDescriptionHelpFormatter
):
    """Preserve command help paragraphs while keeping Django option ordering."""


def _default_pointer_file_path(package_uuid: uuid.UUID) -> str:
    return str(
        pathlib.Path(utils.uuid_to_path(package_uuid)) / f"pointer.{package_uuid}.xml"
    )


def _expected_pointer_path(aip: Package, ss_internal: Location) -> str:
    pointer_location = aip.pointer_file_location or ss_internal
    pointer_file_path = aip.pointer_file_path or _default_pointer_file_path(aip.uuid)
    return str(pathlib.Path(pointer_location.full_path) / pointer_file_path)


def _detect_7z_compression(path: str) -> str:
    output = subprocess.check_output(["7z", "l", path], text=True)
    if "Method = LZMA" in output:
        return utils.COMPRESSION_7Z_LZMA
    if "Method = Copy" in output:
        return utils.COMPRESSION_7Z_COPY
    return utils.COMPRESSION_7Z_BZIP


def _detect_compression(path: str) -> str:
    suffixes = [suffix.lower() for suffix in pathlib.Path(path).suffixes]
    if not suffixes:
        raise CommandError(f"Unable to infer compression for {path}")

    if suffixes[-1] == ".7z":
        return _detect_7z_compression(path)
    if suffixes[-2:] in ([".tar", ".gz"], [".tar", ".gzip"]):
        return utils.COMPRESSION_TAR_GZIP
    if suffixes[-2:] in ([".tar", ".bz2"], [".tar", ".bzip2"]):
        return utils.COMPRESSION_TAR_BZIP2
    if suffixes[-1] == ".tar":
        return utils.COMPRESSION_TAR
    if suffixes[-1] == ".gz":
        return utils.COMPRESSION_TAR_GZIP
    if suffixes[-1] == ".bz2":
        return utils.COMPRESSION_TAR_BZIP2

    raise CommandError(f"Unsupported compressed AIP format for {path}")


def _compression_event_detail(compression: str) -> tuple[str, str, str]:
    if compression in _SEVEN_ZIP_ALGORITHMS:
        program = "7z"
        version = utils.get_7z_version()
        algorithm = _SEVEN_ZIP_ALGORITHMS[compression]
    elif compression in (
        utils.COMPRESSION_TAR,
        utils.COMPRESSION_TAR_BZIP2,
        utils.COMPRESSION_TAR_GZIP,
    ):
        program = "tar"
        version = utils.get_tar_version()
        algorithm = {
            utils.COMPRESSION_TAR: utils.COMPRESS_ALGO_TAR,
            utils.COMPRESSION_TAR_BZIP2: utils.COMPRESS_ALGO_BZIP2,
            utils.COMPRESSION_TAR_GZIP: utils.COMPRESS_ALGO_GZIP,
        }[compression]
    else:
        raise CommandError(f"Unsupported compression algorithm: {compression}")

    return (
        f"program={program}; version={version}; algorithm={algorithm}",
        program,
        version,
    )


def _is_aip_mets_path(path: str, package_uuid: uuid.UUID) -> bool:
    parsed_path = pathlib.PurePosixPath(path)
    return (
        parsed_path.name == f"METS.{package_uuid}.xml" and "data" in parsed_path.parts
    )


def _find_aip_mets_path(paths: list[str], package_uuid: uuid.UUID) -> str:
    candidates = [path for path in paths if _is_aip_mets_path(path, package_uuid)]
    if not candidates:
        raise CommandError(f"Unable to find AIP METS for AIP {package_uuid}")

    return sorted(candidates, key=len)[0]


def _parse_mets_createdate(mets_content: bytes, package_uuid: uuid.UUID) -> str:
    mets_root = etree.fromstring(mets_content)
    mets_header = mets_root.find("mets:metsHdr", namespaces=utils.NSMAP)
    if mets_header is None:
        raise CommandError(f"AIP METS for {package_uuid} does not contain metsHdr")

    createdate = mets_header.get("CREATEDATE")
    if not createdate:
        raise CommandError(
            f"AIP METS for {package_uuid} does not contain metsHdr CREATEDATE"
        )

    return createdate


def _get_7z_paths(path: str) -> list[str]:
    output = subprocess.check_output(["7z", "l", "-slt", path], text=True)
    paths = []
    for line in output.splitlines():
        if line.startswith("Path = "):
            paths.append(line.removeprefix("Path = "))

    return paths


def _read_7z_member(path: str, member_path: str) -> bytes:
    temp_dir = pathlib.Path(tempfile.mkdtemp())
    try:
        subprocess.check_output(
            ["7z", "x", "-bd", "-y", f"-o{temp_dir}", path, member_path]
        )
        extracted_path = temp_dir / pathlib.PurePosixPath(member_path)
        return extracted_path.read_bytes()
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _read_tar_member(path: str, member_path: str) -> bytes:
    with tarfile.open(path, "r:*") as tar:
        member = tar.getmember(member_path)
        extracted_file = tar.extractfile(member)
        if extracted_file is None:
            raise CommandError(f"Unable to extract {member_path} from {path}")

        return extracted_file.read()


def _get_aip_mets_createdate(
    path: str, compression: str, package_uuid: uuid.UUID
) -> str:
    if compression in _SEVEN_ZIP_ALGORITHMS:
        mets_path = _find_aip_mets_path(_get_7z_paths(path), package_uuid)
        mets_content = _read_7z_member(path, mets_path)
    else:
        with tarfile.open(path, "r:*") as tar:
            mets_path = _find_aip_mets_path(tar.getnames(), package_uuid)
        mets_content = _read_tar_member(path, mets_path)

    return _parse_mets_createdate(mets_content, package_uuid)


def _set_premis_text(element: Any, xpath: str, value: str) -> Any:
    tree = element.serialize()
    target = tree.find(xpath, namespaces=utils.NSMAP)
    if target is None:
        raise CommandError(f"Unable to find {xpath} in repaired PREMIS metadata")

    target.text = value
    return element.__class__.fromtree(tree)


class Command(StorageServiceCommand):
    help = __doc__

    def create_parser(self, prog_name: str, subcommand: str, **kwargs: Any) -> Any:
        kwargs.setdefault("formatter_class", RawDescriptionDjangoHelpFormatter)
        return super().create_parser(prog_name, subcommand, **kwargs)

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "package_uuids",
            nargs="*",
            type=uuid.UUID,
            help="Specific original AIP UUIDs to repair.",
        )
        parser.add_argument(
            "--location-uuid",
            type=uuid.UUID,
            help="Only repair AIPs in a specific storage location.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Rewrite pointer files even when the XML already exists.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report AIPs with missing pointer XML without writing files.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        aips = Package.objects.filter(
            package_type__in=(Package.AIP, Package.AIC),
            replicated_package__isnull=True,
            status=Package.UPLOADED,
        )

        package_uuids = options["package_uuids"]
        if package_uuids:
            aips = aips.filter(uuid__in=package_uuids)

        location_uuid = options["location_uuid"]
        if location_uuid:
            aips = aips.filter(current_location=location_uuid)

        if options["dry_run"]:
            if options["force"]:
                raise CommandError("--dry-run cannot be used with --force.")
            self._report_missing_pointer_files(aips)
            return

        total = repaired = skipped = 0
        for aip in aips:
            total += 1
            if self._repair_pointer_file(aip, force=options["force"]):
                repaired += 1
            else:
                skipped += 1

        self.success(
            f"Processed {total} uploaded AIPs; repaired {repaired}; skipped {skipped}."
        )

    def _report_missing_pointer_files(self, aips: Any) -> None:
        ss_internal = Location.active.get(purpose=Location.STORAGE_SERVICE_INTERNAL)

        total = missing = skipped = 0
        for aip in aips:
            total += 1
            if not utils.package_is_file(aip.current_path):
                skipped += 1
                continue

            pointer_path = _expected_pointer_path(aip, ss_internal)
            if pathlib.Path(pointer_path).is_file():
                continue

            missing += 1
            self.info(
                f"Missing pointer file for AIP {aip.uuid}: "
                f"{pointer_path} ({aip.current_path})"
            )

        self.success(
            f"Scanned {total} uploaded AIPs; missing pointer files {missing}; "
            f"skipped uncompressed {skipped}."
        )

    def _repair_pointer_file(self, aip: Package, *, force: bool) -> bool:
        if not utils.package_is_file(aip.current_path):
            self.info(f"Skipping uncompressed AIP {aip.uuid}.")
            return False

        ss_internal = Location.active.get(purpose=Location.STORAGE_SERVICE_INTERNAL)
        if aip.pointer_file_location is None:
            aip.pointer_file_location = ss_internal
        if not aip.pointer_file_path:
            aip.pointer_file_path = _default_pointer_file_path(aip.uuid)

        pointer_path = aip.full_pointer_file_path
        if not pointer_path:
            raise CommandError(f"Unable to determine pointer path for AIP {aip.uuid}")
        if pathlib.Path(pointer_path).is_file() and not force:
            self.info(f"Skipping AIP {aip.uuid}; pointer file already exists.")
            return False

        try:
            # Package._create_pointer_file_write_to_disk creates pointer XML by
            # building a PREMIS AIP object and compression event, passing both
            # to Package.create_pointer_file, and writing that METS document to
            # disk. This repair follows the same path, but reconstructs the
            # compression details and event timestamp from the stored package
            # because the original pointer XML is missing.
            local_path = aip.fetch_local_path()
            compression = _detect_compression(local_path)
            aip_mets_createdate = _get_aip_mets_createdate(
                local_path, compression, aip.uuid
            )
            checksum_algorithm = (
                aip.checksum_algorithm or Package.DEFAULT_CHECKSUM_ALGORITHM
            )
            checksum = utils.generate_checksum(
                local_path, checksum_algorithm
            ).hexdigest()
            size = utils.recalculate_size(local_path)
            event_detail, archive_tool, archive_tool_version = (
                _compression_event_detail(compression)
            )

            compression_event = premis.create_premis_aip_compression_event(
                event_detail,
                "Pointer file recreated from stored AIP package content.",
                agents=[premis.SS_AGENT],
            )
            compression_event = _set_premis_text(
                compression_event,
                ".//premis3:eventDateTime",
                aip_mets_createdate,
            )
            extension = pathlib.Path(aip.current_path).suffix
            premis_object = premis.create_aip_premis_object(
                aip.uuid,
                size,
                extension,
                checksum_algorithm,
                checksum,
                archive_tool,
                archive_tool_version,
            )
            premis_object = _set_premis_text(
                premis_object,
                ".//premis3:dateCreatedByApplication",
                aip_mets_createdate,
            )
            pointer_file = aip.create_pointer_file(
                premis_object,
                [compression_event],
                premis_agents=[premis.SS_AGENT],
            )
            if pointer_file is None:
                raise CommandError(f"Unable to create pointer file for AIP {aip.uuid}")

            write_pointer_file(pointer_file, pointer_path)
            aip.size = size
            aip.checksum = checksum
            aip.checksum_algorithm = checksum_algorithm
            aip.save()
            self.success(f"Repaired pointer file for AIP {aip.uuid}.")
            return True
        finally:
            aip.clear_local_tempdirs()
