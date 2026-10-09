import datetime
import pathlib
from unittest import mock

import pytest
import pytest_django
from django.core.management import call_command
from django.core.management.base import CommandError

from archivematica.storage_service.locations import models
from tests.factories import LocationFactory
from tests.factories import PackageFactory
from tests.factories import SpaceFactory


@pytest.fixture
def secondary_space(make_space: SpaceFactory, tmp_path: pathlib.Path) -> models.Space:
    """A second local filesystem space in the temporary directory."""
    space_dir = tmp_path / "secondary-space"
    space_dir.mkdir()
    staging_dir = tmp_path / "secondary-staging"
    staging_dir.mkdir()

    return make_space(path=str(space_dir), staging_path=str(staging_dir))


@pytest.fixture
def secondary_aip_storage_location(
    make_location: LocationFactory, secondary_space: models.Space
) -> models.Location:
    return make_location(
        secondary_space, models.Location.AIP_STORAGE, relative_path="secondary-aips"
    )


@pytest.fixture
def secondary_package(
    make_package: PackageFactory, secondary_aip_storage_location: models.Location
) -> models.Package:
    """An AIP stored in the secondary space."""
    return make_package(secondary_aip_storage_location, "secondary-uploaded.7z")


@pytest.mark.django_db
def test_command_fails_when_there_are_no_uploaded_aips(
    deleted_package: models.Package,
) -> None:
    with pytest.raises(CommandError, match="No AIPs with status UPLOADED found"):
        call_command("populate_aip_stored_dates")


@pytest.mark.django_db
@mock.patch(
    "archivematica.storage_service.common.management.commands.StorageServiceCommand.error"
)
@mock.patch(
    "archivematica.storage_service.common.management.commands.StorageServiceCommand.success"
)
def test_command_completes_when_location_does_not_contain_aips(
    success: mock.Mock,
    error: mock.Mock,
    package: models.Package,
    secondary_aip_storage_location: models.Location,
) -> None:
    call_command(
        "populate_aip_stored_dates",
        "--location-uuid",
        secondary_aip_storage_location.uuid,
    )

    success.assert_called_once_with("Complete. No matching AIPs found.")
    error.assert_not_called()


@pytest.mark.django_db
@mock.patch("pathlib.Path.stat", side_effect=[mock.Mock(st_mtime=1710831600)])
@mock.patch(
    "archivematica.storage_service.common.management.commands.StorageServiceCommand.error"
)
@mock.patch(
    "archivematica.storage_service.common.management.commands.StorageServiceCommand.success"
)
def test_command_filters_aips_by_location_uuid(
    success: mock.Mock,
    error: mock.Mock,
    stat: mock.Mock,
    settings: pytest_django.Settings,
    package: models.Package,
    secondary_package: models.Package,
    secondary_aip_storage_location: models.Location,
) -> None:
    settings.TIME_ZONE = "UTC"

    call_command(
        "populate_aip_stored_dates",
        "--location-uuid",
        secondary_aip_storage_location.uuid,
    )

    assert models.Package.objects.get(
        uuid=secondary_package.uuid
    ).stored_date == datetime.datetime(2024, 3, 19, 7, 0, tzinfo=datetime.timezone.utc)

    success.assert_called_once_with(
        "Complete. Datestamps for 1 of 1 identified AIPs added. 0 AIPs that already have stored_dates were skipped."
    )
    error.assert_not_called()


@pytest.mark.django_db
@mock.patch(
    "pathlib.Path.stat", side_effect=FileNotFoundError("no such file or directory")
)
@mock.patch(
    "archivematica.storage_service.common.management.commands.StorageServiceCommand.error"
)
@mock.patch(
    "archivematica.storage_service.common.management.commands.StorageServiceCommand.success"
)
def test_command_logs_error_when_it_cannot_read_aip_file(
    success: mock.Mock,
    error: mock.Mock,
    stat: mock.Mock,
    secondary_package: models.Package,
    secondary_aip_storage_location: models.Location,
) -> None:
    call_command(
        "populate_aip_stored_dates",
        "--location-uuid",
        secondary_aip_storage_location.uuid,
    )

    success.assert_called_once_with(
        "Complete. Datestamps for 0 of 1 identified AIPs added. 0 AIPs that already have stored_dates were skipped."
    )
    error.assert_called_once_with(
        f"Unable to get timestamp for local AIP {secondary_package.uuid}. Details: no such file or directory"
    )


@pytest.mark.django_db
@mock.patch(
    "archivematica.storage_service.common.management.commands.StorageServiceCommand.error"
)
@mock.patch(
    "archivematica.storage_service.common.management.commands.StorageServiceCommand.success"
)
def test_command_skips_aips_with_stored_dates(
    success: mock.Mock,
    error: mock.Mock,
    secondary_package: models.Package,
) -> None:
    secondary_package.stored_date = datetime.datetime(
        2023, 1, 1, 0, 0, tzinfo=datetime.timezone.utc
    )
    secondary_package.save()

    call_command("populate_aip_stored_dates")

    success.assert_called_once_with(
        "Complete. All 1 AIPs that already have stored_dates skipped."
    )
    error.assert_not_called()
