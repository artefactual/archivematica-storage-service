"""Reingest of stored AIPs through an Archivematica pipeline.

A reingest starts with a request: the Storage Service reads the AIP from a
working copy, selects the files the reingest type needs, adds the processing
configuration and delivers them to the currently processing location of the
pipeline, which then approves the reingest. It ends when the pipeline stores
the reingested AIP back and the Storage Service merges it into the stored one,
which :meth:`Package.finish_reingest` does.
"""

from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass
from typing import TypedDict

import requests
from django.utils.translation import gettext_lazy as _
from django_stubs_ext import StrOrPromise

from archivematica.storage_service.locations.models import Location
from archivematica.storage_service.locations.models import Package
from archivematica.storage_service.locations.models import Pipeline

LOGGER = logging.getLogger(__name__)


class ReingestResponse(TypedDict):
    """Outcome of a reingest request, also the body of the API response."""

    error: bool
    status_code: int
    message: StrOrPromise


class ReingestAccepted(ReingestResponse):
    """Outcome of a reingest request the pipeline accepted."""

    reingest_uuid: str


def _error(status_code: int, message: StrOrPromise) -> ReingestResponse:
    return {"error": True, "status_code": status_code, "message": message}


@dataclass
class WorkingCopy:
    """A directory the content of an AIP is read from while preparing a reingest.

    ``path`` is a bag directory inside ``location``, ending with a slash for
    uncompressed AIPs so that the move functions send its content.
    ``disposable`` tells whether it is a copy made for the reingest or the
    stored AIP itself, and ``temp_dir`` names the directory of an extraction
    to delete along with the copy.
    """

    path: str
    location: Location
    disposable: bool
    temp_dir: str = ""

    @property
    def relative_path(self) -> str:
        """Return ``path`` relative to ``location``, the name the pipeline gets."""
        return self.path.replace(self.location.full_path, "", 1).lstrip("/")

    def discard(self) -> None:
        """Delete the copy, if it is one, and the extraction directory."""
        # Delete local copy of extraction
        if self.disposable:
            try:
                shutil.rmtree(self.path)
            except OSError:  # May have been moved not copied
                pass
        if self.temp_dir:
            shutil.rmtree(self.temp_dir)


def working_copy(package: Package) -> WorkingCopy:
    """Return where the content of ``package`` is read from for a reingest.

    Compressed AIPs are extracted into the internal location and AIPs the
    Storage Service cannot read in place are fetched there. Uncompressed
    AIPs it can read are used where they are stored.
    """
    if package.is_compressed:
        path, temp_dir = package.extract_file()
        LOGGER.debug("Reingest: extracted to %s", path)
    else:
        # Append / to uncompressed AIPS so we send the contents of the dir
        # not the dir itself inside a dir of the same name
        path = os.path.join(package.fetch_local_path(), "")
        temp_dir = ""
        LOGGER.debug("Reingest: uncompressed at %s", path)
    return WorkingCopy(
        path=path,
        location=package.local_path_location or package.current_location,
        disposable=package.local_path != package.full_path,
        temp_dir=temp_dir,
    )


def _select_paths(copy: WorkingCopy, reingest_type: str, package: Package) -> list[str]:
    """Return the paths of ``copy`` to send for ``reingest_type``.

    Paths are relative to the location of the copy. Directories end with a
    slash so that the move functions send their content.
    """
    relative_path = copy.relative_path
    if reingest_type == Package.FULL:
        # All the things!
        return [relative_path]
    paths = [os.path.join(relative_path, "data", f"METS.{package.uuid}.xml")]
    if reingest_type == Package.OBJECTS:
        # All in objects except submissionDocumentation dir
        for name in os.listdir(os.path.join(copy.path, "data", "objects")):
            if name in ("submissionDocumentation",):
                continue
            abs_path = os.path.join(copy.path, "data", "objects", name)
            if os.path.isfile(abs_path):
                paths.append(os.path.join(relative_path, "data", "objects", name))
            elif os.path.isdir(abs_path):
                # Dirs must be / terminated to make the move functions happy
                paths.append(os.path.join(relative_path, "data", "objects", name, ""))
    elif reingest_type == Package.METADATA_ONLY:
        paths.append(os.path.join(relative_path, "data", "objects", "metadata", ""))
    return paths


def _fetch_processing_config(pipeline: Pipeline, name: str) -> str | None:
    """Return the processing configuration ``name`` of ``pipeline``.

    The default configuration is not fetched, and one that cannot be loaded
    is logged and left out of the reingest.
    """
    if name == "default":
        return None
    try:
        return pipeline.get_processing_config(name)
    except requests.exceptions.RequestException:
        LOGGER.error("Reingest: processing configuration %s could not be loaded", name)
        return None


def _write_processing_config(config: str, name: str, directory: str) -> None:
    """Write processing configuration ``name`` at the root of ``directory``."""
    config_path = os.path.join(directory, "processingMCP.xml")
    try:
        # It's not expected to find an existing processingMCP.xml
        # file in the original AIP, but we are using the w+ mode
        # just in case.
        with open(config_path, "w+") as f:
            f.write(config)
    except OSError:
        LOGGER.exception(
            "Reingest: processing configuration %s could not be written", name
        )
        raise
    LOGGER.debug(
        "Reingest: processing configuration %s written, location: %s",
        name,
        config_path,
    )


def _deliver(
    copy: WorkingCopy,
    paths: list[str],
    currently_processing: Location,
    package: Package,
) -> None:
    """Copy ``paths`` of ``copy`` under the tmp directory of the pipeline."""
    LOGGER.debug("Reingest: Current location: %s", copy.location)
    dest_basepath = os.path.join(currently_processing.relative_path, "tmp", "")
    for path in paths:
        copy.location.space.move_to_storage_service(
            source_path=os.path.join(copy.location.relative_path, path),
            destination_path=path,
            destination_space=currently_processing.space,
        )
        currently_processing.space.move_from_storage_service(
            source_path=path,
            destination_path=os.path.join(dest_basepath, path),
            package=package,
        )


def start(
    package: Package,
    pipeline: Pipeline,
    reingest_type: str,
    processing_config: str = "default",
) -> ReingestResponse:
    """Copy ``package`` to ``pipeline`` for reingest.

    Fetches the AIP from storage, extracts and runs fixity on it to verify
    integrity. If ``reingest_type`` is METADATA_ONLY, sends the METS and all
    files in the metadata directory. If it is OBJECTS, sends the METS, all
    files in the metadata directory and all objects, preservation and
    original. If it is FULL, sends the whole AIP to be reingested as a
    transfer. Calls the pipeline's reingest endpoint to start the reingest.

    :param package: Package to reingest.
    :param pipeline: Pipeline object to send reingested AIP to.
    :param reingest_type: Type of reingest to start, one of REINGEST_CHOICES.
    :param processing_config: Name of the processing configuration to send along.
    :return: Dict with keys 'error', 'status_code' and 'message'
    """
    # Reingest type is part of the payload so we can convert it to lower
    # case here to make any calls to start_reingest more robust.
    reingest_type = reingest_type.lower()

    if package.package_type not in Package.PACKAGE_TYPE_CAN_REINGEST:
        return _error(
            405,
            f"Package with type {package.get_package_type_display()} cannot be re-ingested.",
        )

    # Check and set reingest pipeline
    if package.misc_attributes.get("reingest_pipeline", None):
        return _error(
            409,
            _("This AIP is already being reingested on %(pipeline)s")
            % {"pipeline": package.misc_attributes["reingest_pipeline"]},
        )
    package.misc_attributes.update({"reingest_pipeline": str(pipeline.uuid)})

    # Run fixity
    # Fixity will fetch & extract package if needed
    success, _failures, error_msg, _timestamp = package.check_fixity(delete_after=False)
    LOGGER.debug("Reingest: Fixity response: %s, %s", success, error_msg)
    if not success:
        return _error(500, error_msg)

    copy = working_copy(package)
    reingest_files = _select_paths(copy, reingest_type, package)

    # Fetch processing configuration, put it in the root of the package and
    # include the file in reingest_files.
    config = _fetch_processing_config(pipeline, processing_config)
    if config is not None:
        _write_processing_config(config, processing_config, copy.path)
        if reingest_type != Package.FULL:
            reingest_files.append(os.path.join(copy.relative_path, "processingMCP.xml"))

    LOGGER.info("Reingest: files: %s", reingest_files)

    # Copy to pipeline
    try:
        currently_processing = Location.active.filter(pipeline=pipeline).get(
            purpose=Location.CURRENTLY_PROCESSING
        )
    except (Location.DoesNotExist, Location.MultipleObjectsReturned):
        return _error(
            412,
            _("No currently processing Location is associated with pipeline %(uuid)s")
            % {"uuid": pipeline.uuid},
        )
    _deliver(copy, reingest_files, currently_processing, package)
    copy.discard()

    # Call reingest API
    reingest_target = "transfer" if reingest_type == Package.FULL else "ingest"
    try:
        resp = pipeline.reingest(copy.relative_path, package.uuid, reingest_target)
    except requests.exceptions.RequestException as e:
        LOGGER.exception(
            "Error approving reingest in pipeline for package %s", package.uuid
        )
        return _error(502, _("Error in approve reingest API. %(error)s") % {"error": e})
    reingest_uuid = resp.get("reingest_uuid")
    LOGGER.debug("Reingest UUID: %s", reingest_uuid)
    package.save()

    accepted: ReingestAccepted = {
        "error": False,
        "status_code": 202,
        "message": _("Package %(uuid)s sent to pipeline %(pipeline)s for re-ingest")
        % {"uuid": package.uuid, "pipeline": pipeline},
        "reingest_uuid": str(reingest_uuid),
    }
    return accepted
