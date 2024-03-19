import datetime
import pathlib
from typing import Any
from unittest import mock

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from locations import models


@pytest.fixture
@pytest.mark.django_db
def fs_space(tmp_path: pathlib.Path) -> models.Location:
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
@pytest.mark.django_db
def aip_storage_fs_location(fs_space: models.Space) -> models.Location:
    return models.Location.objects.create(
        space=fs_space,
        purpose=models.Location.AIP_STORAGE,
        relative_path="fs-aips",
    )


@pytest.fixture
@pytest.mark.django_db
def aip_deleted_fs_location(aip_storage_fs_location: models.Location) -> models.Package:
    return models.Package.objects.create(
        package_type=models.Package.AIP,
        status=models.Package.DELETED,
        current_location=aip_storage_fs_location,
        current_path="deleted.7z",
    )


@pytest.fixture
@pytest.mark.django_db
def aip_uploaded_fs_location(
    aip_storage_fs_location: models.Location,
) -> models.Package:
    return models.Package.objects.create(
        package_type=models.Package.AIP,
        status=models.Package.UPLOADED,
        current_location=aip_storage_fs_location,
        current_path="uploaded.7z",
    )


@pytest.fixture
@pytest.mark.django_db
def secondary_fs_space(tmp_path: pathlib.Path) -> models.Location:
    space_dir = tmp_path / "secondary-space"
    space_dir.mkdir()

    staging_dir = tmp_path / "secondary-staging"
    staging_dir.mkdir()

    result = models.Space.objects.create(
        access_protocol=models.Space.LOCAL_FILESYSTEM,
        path=str(space_dir),
        staging_path=str(staging_dir),
    )
    models.LocalFilesystem.objects.create(space=result)

    return result


@pytest.fixture
@pytest.mark.django_db
def secondary_aip_storage_fs_location(
    secondary_fs_space: models.Space,
) -> models.Location:
    return models.Location.objects.create(
        space=secondary_fs_space,
        purpose=models.Location.AIP_STORAGE,
        relative_path="secondary-fs-aips",
    )


@pytest.fixture
@pytest.mark.django_db
def secondary_aip_uploaded_fs_location(
    secondary_aip_storage_fs_location: models.Location,
) -> models.Package:
    return models.Package.objects.create(
        package_type=models.Package.AIP,
        status=models.Package.UPLOADED,
        current_location=secondary_aip_storage_fs_location,
        current_path="secondary-uploaded.7z",
    )


@pytest.mark.django_db
def test_command_fails_when_there_are_no_uploaded_aips(
    aip_deleted_fs_location: models.Package,
) -> None:
    with pytest.raises(CommandError, match="No AIPs with status UPLOADED found"):
        call_command("populate_aip_stored_dates")


@pytest.mark.django_db
@mock.patch("common.management.commands.StorageServiceCommand.error")
@mock.patch("common.management.commands.StorageServiceCommand.success")
def test_command_completes_when_location_does_not_contain_aips(
    success: mock.Mock,
    error: mock.Mock,
    aip_uploaded_fs_location: models.Package,
    secondary_aip_storage_fs_location: models.Location,
) -> None:
    call_command(
        "populate_aip_stored_dates",
        "--location-uuid",
        secondary_aip_storage_fs_location.uuid,
    )

    success.assert_called_once_with("Complete. No matching AIPs found.")
    error.assert_not_called()


@pytest.mark.django_db
@mock.patch("os.path.getmtime", side_effect=[1710831600])
@mock.patch("common.management.commands.StorageServiceCommand.error")
@mock.patch("common.management.commands.StorageServiceCommand.success")
def test_command_filters_aips_by_location_uuid(
    success: mock.Mock,
    error: mock.Mock,
    getmtime: mock.Mock,
    settings: Any,
    aip_uploaded_fs_location: models.Package,
    secondary_aip_uploaded_fs_location: models.Package,
    secondary_aip_storage_fs_location: models.Location,
) -> None:
    settings.TIME_ZONE = "UTC"

    call_command(
        "populate_aip_stored_dates",
        "--location-uuid",
        secondary_aip_storage_fs_location.uuid,
    )

    assert models.Package.objects.get(
        uuid=secondary_aip_uploaded_fs_location.uuid
    ).stored_date == datetime.datetime(2024, 3, 19, 7, 0, tzinfo=datetime.timezone.utc)

    getmtime.assert_called_once_with(secondary_aip_uploaded_fs_location.full_path)
    success.assert_called_once_with(
        "Complete. Datestamps for 1 of 1 identified AIPs added. 0 AIPs that already have stored_dates were skipped."
    )
    error.assert_not_called()


@pytest.mark.django_db
@mock.patch("os.path.getmtime", side_effect=OSError("no such file or directory"))
@mock.patch("common.management.commands.StorageServiceCommand.error")
@mock.patch("common.management.commands.StorageServiceCommand.success")
def test_command_logs_error_when_it_cannot_read_aip_file(
    success: mock.Mock,
    error: mock.Mock,
    getmtime: mock.Mock,
    secondary_aip_uploaded_fs_location: models.Package,
    secondary_aip_storage_fs_location: models.Location,
) -> None:
    call_command(
        "populate_aip_stored_dates",
        "--location-uuid",
        secondary_aip_storage_fs_location.uuid,
    )

    getmtime.assert_called_once_with(secondary_aip_uploaded_fs_location.full_path)
    success.assert_called_once_with(
        "Complete. Datestamps for 0 of 1 identified AIPs added. 0 AIPs that already have stored_dates were skipped."
    )
    error.assert_called_once_with(
        f"Unable to get timestamp for local AIP {secondary_aip_uploaded_fs_location.uuid}. Details: no such file or directory"
    )


@pytest.mark.django_db
@mock.patch("common.management.commands.StorageServiceCommand.error")
@mock.patch("common.management.commands.StorageServiceCommand.success")
def test_command_skips_aips_with_stored_dates(
    success: mock.Mock,
    error: mock.Mock,
    secondary_aip_uploaded_fs_location: models.Package,
) -> None:
    secondary_aip_uploaded_fs_location.stored_date = datetime.datetime(
        2023, 1, 1, 0, 0, tzinfo=datetime.timezone.utc
    )
    secondary_aip_uploaded_fs_location.save()

    call_command("populate_aip_stored_dates")

    success.assert_called_once_with(
        "Complete. All 1 AIPs that already have stored_dates skipped."
    )
    error.assert_not_called()
