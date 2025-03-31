import pathlib
import uuid
from unittest import mock

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from archivematica.storage_service.locations import models

TEST_DIR = pathlib.Path(__file__).resolve().parent
FIXTURES_DIR = TEST_DIR / "fixtures"
POINTER_FILE_PATH = FIXTURES_DIR / "premis_3_pointer.xml"


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
def compressed_package(aip_storage_fs_location: models.Location) -> models.Package:
    package_uuid = uuid.uuid4()
    package_current_path = f"compressedaip-{package_uuid}.7z"
    (pathlib.Path(aip_storage_fs_location.full_path) / package_current_path).touch()

    result = models.Package.objects.create(
        uuid=package_uuid,
        status=models.Package.UPLOADED,
        current_location=aip_storage_fs_location,
        current_path=package_current_path,
        package_type=models.Package.AIP,
    )
    assert result.is_compressed

    return result


@pytest.fixture
def uncompressed_package(aip_storage_fs_location: models.Location) -> models.Package:
    package_uuid = uuid.uuid4()
    package_current_path = f"uncompressedaip-{package_uuid}"
    package_dir = pathlib.Path(aip_storage_fs_location.full_path) / package_current_path
    package_dir.mkdir()

    # Add tag manifest to fake a valid bag.
    (package_dir / "tagmanifest-sha256.txt").touch()

    result = models.Package.objects.create(
        uuid=package_uuid,
        status=models.Package.UPLOADED,
        current_location=aip_storage_fs_location,
        current_path=package_current_path,
        package_type=models.Package.AIP,
    )

    assert not result.is_compressed

    return result


@pytest.fixture
def deleted_package(aip_storage_fs_location: models.Location) -> models.Package:
    return models.Package.objects.create(
        package_type=models.Package.AIP,
        status=models.Package.DELETED,
        current_location=aip_storage_fs_location,
        current_path="deleted.7z",
    )


@pytest.mark.django_db
def test_command_fails_when_there_are_no_uploaded_aips(
    deleted_package: models.Package,
) -> None:
    with pytest.raises(CommandError, match="No AIPs with status UPLOADED found"):
        call_command("populate_aip_checksums")


@pytest.mark.django_db
@mock.patch(
    "archivematica.storage_service.common.management.commands.StorageServiceCommand.error"
)
@mock.patch(
    "archivematica.storage_service.common.utils.get_compressed_package_checksum"
)
def test_command_fails_when_checksum_is_missing_for_compressed_aip(
    get_compressed_package_checksum: mock.Mock,
    error: mock.Mock,
    capsys: pytest.CaptureFixture[str],
    compressed_package: models.Package,
    aip_storage_fs_location: models.Location,
) -> None:
    # The compressed AIP checksum is set to None when it cannot be retrieved from the pointer file.
    get_compressed_package_checksum.return_value = (None, "sha256")

    call_command(
        "populate_aip_checksums",
        "--location-uuid",
        aip_storage_fs_location.uuid,
    )

    error.assert_called_once_with(
        f"Unable to retrieve checksum information from pointer file for compressed AIP {compressed_package.uuid}"
    )
    captured = capsys.readouterr()
    assert captured.out.splitlines() == [
        f"Complete. Checksums added for 0 of {models.Package.objects.count()} identified AIPs. See output for details."
    ]


@pytest.mark.django_db
def test_command_updates_checksum_for_compressed_aip(
    capsys: pytest.CaptureFixture[str],
    compressed_package: models.Package,
    aip_storage_fs_location: models.Location,
) -> None:
    with mock.patch.object(models.Package, "full_pointer_file_path", POINTER_FILE_PATH):
        call_command(
            "populate_aip_checksums",
            "--location-uuid",
            aip_storage_fs_location.uuid,
        )

    captured = capsys.readouterr()
    compressed_package_checksum = (
        "c2924159fcbbeadf8d7f3962b43ec1bf301e1b4f12dd28a8b89ec819f3714747"
    )
    algo = "sha256"
    assert captured.out.splitlines() == [
        f"AIP {compressed_package.uuid} updated with {algo} checksum {compressed_package_checksum}",
        f"Complete. Checksums added for all {models.Package.objects.count()} identified AIPs.",
    ]


@pytest.mark.django_db
@mock.patch("archivematica.storage_service.common.utils.generate_checksum")
def test_command_updates_checksum_for_uncompressed_aip(
    generate_checksum: mock.Mock,
    capsys: pytest.CaptureFixture[str],
    uncompressed_package: models.Package,
    aip_storage_fs_location: models.Location,
) -> None:
    uncompressed_package_checksum = (
        "c2924159fcbbeadf8d7f3962b43ec1bf301e1b4f12dd28a8b89ec819f3714848"
    )
    generate_checksum.return_value = mock.Mock(
        **{
            "hexdigest.return_value": uncompressed_package_checksum,
        }
    )

    call_command(
        "populate_aip_checksums",
        "--location-uuid",
        aip_storage_fs_location.uuid,
    )

    captured = capsys.readouterr()
    assert captured.out.splitlines() == [
        f"AIP {uncompressed_package.uuid} updated with sha256 checksum {uncompressed_package_checksum}",
        f"Complete. Checksums added for all {models.Package.objects.count()} identified AIPs.",
    ]


@pytest.mark.django_db
@mock.patch("archivematica.storage_service.common.utils.generate_checksum")
def test_command_updates_checksum_for_aip_downloaded_remotely(
    generate_checksum: mock.Mock,
    capsys: pytest.CaptureFixture[str],
    compressed_package: models.Package,
    uncompressed_package: models.Package,
    aip_storage_fs_location: models.Location,
) -> None:
    uncompressed_package_checksum = (
        "c2924159fcbbeadf8d7f3962b43ec1bf301e1b4f12dd28a8b89ec819f3714848"
    )
    generate_checksum.return_value = mock.Mock(
        **{
            "hexdigest.return_value": uncompressed_package_checksum,
        }
    )

    with mock.patch.object(models.Package, "full_pointer_file_path", POINTER_FILE_PATH):
        call_command(
            "populate_aip_checksums",
            "--location-uuid",
            aip_storage_fs_location.uuid,
            "--download",
        )

    captured = capsys.readouterr()
    compressed_package_checksum = (
        "c2924159fcbbeadf8d7f3962b43ec1bf301e1b4f12dd28a8b89ec819f3714747"
    )
    algo = "sha256"
    assert captured.out.splitlines() == [
        f"AIP {compressed_package.uuid} updated with {algo} checksum {compressed_package_checksum}",
        f"AIP {uncompressed_package.uuid} updated with {algo} checksum {uncompressed_package_checksum}",
        f"Complete. Checksums added for all {models.Package.objects.count()} identified AIPs.",
    ]


@pytest.mark.django_db
@mock.patch("archivematica.storage_service.common.utils.generate_checksum")
def test_command_fails_when_checksum_is_missing_for_uncompressed_aip(
    generate_checksum: mock.Mock,
    capsys: pytest.CaptureFixture[str],
    compressed_package: models.Package,
    uncompressed_package: models.Package,
    aip_storage_fs_location: models.Location,
) -> None:
    uncompressed_package_checksum = None
    generate_checksum.return_value = mock.Mock(
        **{
            "hexdigest.return_value": uncompressed_package_checksum,
        }
    )

    with mock.patch.object(models.Package, "full_pointer_file_path", POINTER_FILE_PATH):
        call_command(
            "populate_aip_checksums",
            "--location-uuid",
            aip_storage_fs_location.uuid,
            "--download",
        )

    captured = capsys.readouterr()
    compressed_package_checksum = (
        "c2924159fcbbeadf8d7f3962b43ec1bf301e1b4f12dd28a8b89ec819f3714747"
    )
    algo = "sha256"
    assert captured.out.splitlines() == [
        f"AIP {compressed_package.uuid} updated with {algo} checksum {compressed_package_checksum}",
        f"Unable to calculate tagmanifest checksum for uncompressed AIP {uncompressed_package.uuid}",
        f"Complete. Checksums added for 1 of {models.Package.objects.count()} identified AIPs. See output for details.",
    ]
