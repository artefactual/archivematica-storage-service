import pathlib
import uuid

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from archivematica.storage_service.common.management.commands import (
    reconcile_pointer_file_locations,
)
from archivematica.storage_service.locations import models


@pytest.fixture
def fs_space(tmp_path: pathlib.Path) -> models.Space:
    space_dir = tmp_path / "space"
    space_dir.mkdir()
    staging_dir = tmp_path / "staging"
    staging_dir.mkdir()

    result = models.Space.objects.create(
        access_protocol=models.Space.LOCAL_FILESYSTEM,
        path=str(space_dir),
        staging_path=str(staging_dir),
    )
    models.LocalFilesystem.objects.create(space=result)
    return result


@pytest.fixture
def aip_storage_location(fs_space: models.Space) -> models.Location:
    result = models.Location.objects.create(
        space=fs_space,
        purpose=models.Location.AIP_STORAGE,
        relative_path="new-aips",
    )
    pathlib.Path(result.full_path).mkdir()
    return result


@pytest.fixture
def internal_location(fs_space: models.Space) -> models.Location:
    result = models.Location.objects.create(
        space=fs_space,
        purpose=models.Location.STORAGE_SERVICE_INTERNAL,
        relative_path="internal",
    )
    pathlib.Path(result.full_path).mkdir()
    return result


def pointer_xml(package_uuid: uuid.UUID, href: str) -> str:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<mets:mets xmlns:mets="http://www.loc.gov/METS/" xmlns:xlink="http://www.w3.org/1999/xlink">
  <mets:fileSec>
    <mets:fileGrp>
      <mets:file ID="file-aip-{package_uuid}">
        <mets:FLocat xlink:href="{href}" />
      </mets:file>
    </mets:fileGrp>
  </mets:fileSec>
</mets:mets>
"""


@pytest.fixture
def package_with_stale_pointer(
    aip_storage_location: models.Location,
    internal_location: models.Location,
) -> models.Package:
    package_uuid = uuid.uuid4()
    current_path = f"test-{package_uuid}.7z"
    (pathlib.Path(aip_storage_location.full_path) / current_path).touch()
    pointer_path = f"pointer.{package_uuid}.xml"
    (pathlib.Path(internal_location.full_path) / pointer_path).write_text(
        pointer_xml(package_uuid, f"/old-aips/{current_path}")
    )

    return models.Package.objects.create(
        uuid=package_uuid,
        package_type=models.Package.AIP,
        status=models.Package.UPLOADED,
        current_location=aip_storage_location,
        current_path=current_path,
        pointer_file_location=internal_location,
        pointer_file_path=pointer_path,
        size=1,
    )


def create_package_with_pointer(
    aip_storage_location: models.Location,
    internal_location: models.Location,
    status: str,
    package_type: str = models.Package.AIP,
) -> models.Package:
    package_uuid = uuid.uuid4()
    current_path = f"test-{package_uuid}.7z"
    (pathlib.Path(aip_storage_location.full_path) / current_path).touch()
    pointer_path = f"pointer.{package_uuid}.xml"
    (pathlib.Path(internal_location.full_path) / pointer_path).write_text(
        pointer_xml(package_uuid, f"/old-aips/{current_path}")
    )

    return models.Package.objects.create(
        uuid=package_uuid,
        package_type=package_type,
        status=status,
        current_location=aip_storage_location,
        current_path=current_path,
        pointer_file_location=internal_location,
        pointer_file_path=pointer_path,
        size=1,
    )


@pytest.mark.django_db
def test_command_updates_pointer_file_href(
    package_with_stale_pointer: models.Package,
) -> None:
    call_command("reconcile_pointer_file_locations")

    assert (
        reconcile_pointer_file_locations.pointer_file_href(package_with_stale_pointer)
        == package_with_stale_pointer.full_path
    )


@pytest.mark.django_db
def test_command_updates_uploaded_aic_pointer_file_href(
    aip_storage_location: models.Location,
    internal_location: models.Location,
) -> None:
    package = create_package_with_pointer(
        aip_storage_location,
        internal_location,
        models.Package.UPLOADED,
        package_type=models.Package.AIC,
    )

    call_command("reconcile_pointer_file_locations")

    assert (
        reconcile_pointer_file_locations.pointer_file_href(package) == package.full_path
    )


@pytest.mark.django_db
def test_command_skips_non_uploaded_packages(
    package_with_stale_pointer: models.Package,
    aip_storage_location: models.Location,
    internal_location: models.Location,
) -> None:
    failed_package = create_package_with_pointer(
        aip_storage_location, internal_location, models.Package.FAIL
    )

    call_command("reconcile_pointer_file_locations")

    assert (
        reconcile_pointer_file_locations.pointer_file_href(package_with_stale_pointer)
        == package_with_stale_pointer.full_path
    )
    assert reconcile_pointer_file_locations.pointer_file_href(failed_package).startswith(
        "/old-aips/"
    )


@pytest.mark.django_db
def test_command_skips_deleted_packages(
    package_with_stale_pointer: models.Package,
    aip_storage_location: models.Location,
    internal_location: models.Location,
) -> None:
    deleted_package = create_package_with_pointer(
        aip_storage_location, internal_location, models.Package.DELETED
    )

    call_command("reconcile_pointer_file_locations")

    assert (
        reconcile_pointer_file_locations.pointer_file_href(package_with_stale_pointer)
        == package_with_stale_pointer.full_path
    )
    assert reconcile_pointer_file_locations.pointer_file_href(deleted_package).startswith(
        "/old-aips/"
    )


@pytest.mark.django_db
def test_command_dry_run_does_not_update_pointer_file_href(
    package_with_stale_pointer: models.Package,
) -> None:
    call_command("reconcile_pointer_file_locations", "--dry-run")

    assert reconcile_pointer_file_locations.pointer_file_href(
        package_with_stale_pointer
    ).startswith("/old-aips/")


@pytest.mark.django_db
def test_command_skips_missing_pointer_file(
    aip_storage_location: models.Location,
    internal_location: models.Location,
    capsys: pytest.CaptureFixture[str],
) -> None:
    package = models.Package.objects.create(
        uuid=uuid.uuid4(),
        package_type=models.Package.AIP,
        status=models.Package.UPLOADED,
        current_location=aip_storage_location,
        current_path="deleted.7z",
        pointer_file_location=internal_location,
        pointer_file_path="missing-pointer.xml",
    )

    call_command("reconcile_pointer_file_locations")

    captured = capsys.readouterr()
    assert f"{package.uuid}: skipped, pointer file not found:" in captured.out


@pytest.mark.django_db
def test_command_fails_when_no_pointer_files_match(
    aip_storage_location: models.Location,
) -> None:
    models.Package.objects.create(
        uuid=uuid.uuid4(),
        package_type=models.Package.AIP,
        status=models.Package.UPLOADED,
        current_location=aip_storage_location,
        current_path="uncompressed-aip",
    )

    with pytest.raises(CommandError, match="No uploaded AIPs or AICs with pointer files"):
        call_command("reconcile_pointer_file_locations")
