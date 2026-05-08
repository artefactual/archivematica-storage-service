import pathlib
import uuid
from unittest import mock

import pytest
from common import utils
from django.core.management import call_command
from django.core.management.base import CommandError
from locations import models


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
def aip_storage_fs_location(fs_space: models.Space) -> models.Location:
    result = models.Location.objects.create(
        space=fs_space,
        purpose=models.Location.AIP_STORAGE,
        relative_path="fs-aips",
    )
    pathlib.Path(result.full_path).mkdir()

    return result


@pytest.fixture
def ss_internal_location(fs_space: models.Space) -> models.Location:
    result = models.Location.objects.create(
        space=fs_space,
        purpose=models.Location.STORAGE_SERVICE_INTERNAL,
        relative_path="storage-service",
    )
    pathlib.Path(result.full_path).mkdir()

    return result


def _create_uploaded_aip(
    location: models.Location, package_uuid: uuid.UUID, current_path: str
) -> models.Package:
    return models.Package.objects.create(
        uuid=package_uuid,
        status=models.Package.UPLOADED,
        current_location=location,
        current_path=current_path,
        package_type=models.Package.AIP,
    )


@pytest.mark.django_db
@mock.patch.object(models.Package, "fetch_local_path")
def test_dry_run_reports_missing_pointer_files_without_repairing(
    fetch_local_path: mock.Mock,
    capsys: pytest.CaptureFixture[str],
    aip_storage_fs_location: models.Location,
    ss_internal_location: models.Location,
) -> None:
    missing_uuid = uuid.uuid4()
    missing_aip = _create_uploaded_aip(
        aip_storage_fs_location,
        missing_uuid,
        f"missing-{missing_uuid}.7z",
    )

    existing_uuid = uuid.uuid4()
    existing_pointer_path = (
        pathlib.Path(utils.uuid_to_path(existing_uuid)) / f"pointer.{existing_uuid}.xml"
    )
    existing_aip = _create_uploaded_aip(
        aip_storage_fs_location,
        existing_uuid,
        f"existing-{existing_uuid}.7z",
    )
    existing_aip.pointer_file_location = ss_internal_location
    existing_aip.pointer_file_path = str(existing_pointer_path)
    existing_aip.save()
    pathlib.Path(existing_aip.full_pointer_file_path).parent.mkdir(parents=True)
    pathlib.Path(existing_aip.full_pointer_file_path).touch()

    uncompressed_uuid = uuid.uuid4()
    uncompressed_aip = _create_uploaded_aip(
        aip_storage_fs_location,
        uncompressed_uuid,
        f"uncompressed-{uncompressed_uuid}",
    )

    call_command(
        "repair_aip_pointer_files",
        str(missing_aip.uuid),
        str(existing_aip.uuid),
        str(uncompressed_aip.uuid),
        "--dry-run",
    )

    missing_aip.refresh_from_db()
    captured = capsys.readouterr()
    expected_missing_pointer_path = (
        pathlib.Path(ss_internal_location.full_path)
        / utils.uuid_to_path(missing_uuid)
        / f"pointer.{missing_uuid}.xml"
    )

    fetch_local_path.assert_not_called()
    assert missing_aip.pointer_file_location is None
    assert missing_aip.pointer_file_path is None
    assert f"Missing pointer file for AIP {missing_uuid}" in captured.out
    assert str(expected_missing_pointer_path) in captured.out
    assert f"Missing pointer file for AIP {existing_uuid}" not in captured.out
    assert f"Missing pointer file for AIP {uncompressed_uuid}" not in captured.out
    assert (
        "Scanned 3 uploaded AIPs; missing pointer files 1; skipped uncompressed 1."
    ) in captured.out


@pytest.mark.django_db
def test_dry_run_rejects_force(
    aip_storage_fs_location: models.Location,
    ss_internal_location: models.Location,
) -> None:
    package_uuid = uuid.uuid4()
    _create_uploaded_aip(
        aip_storage_fs_location,
        package_uuid,
        f"package-{package_uuid}.7z",
    )

    with pytest.raises(CommandError, match="--dry-run cannot be used with --force"):
        call_command(
            "repair_aip_pointer_files",
            "--dry-run",
            "--force",
        )
