import pathlib
import uuid

import pytest
from django.core.management import call_command
from locations import models

TEST_DIR = pathlib.Path(__file__).resolve().parent
FIXTURES_DIR = TEST_DIR / "fixtures"
AIP_PATH = FIXTURES_DIR / "import_aip_test.7z"


@pytest.fixture
def aip_storage_location(db, tmp_path):
    space_directory = tmp_path / "sub"
    space_directory.mkdir()
    space = models.Space.objects.create(
        uuid=str(uuid.uuid4()),
        path=space_directory,
        access_protocol=models.Space.LOCAL_FILESYSTEM,
        staging_path=space_directory,
    )
    pipeline = models.Pipeline.objects.create(uuid=str(uuid.uuid4()))
    aipstore = models.Location.objects.create(
        uuid=str(uuid.uuid4()),
        space=space,
        purpose="AS",
        relative_path="",
    )
    models.Location.objects.create(
        space=space, purpose=models.Location.STORAGE_SERVICE_INTERNAL, relative_path=""
    )
    models.LocalFilesystem.objects.create(space=space)
    models.LocationPipeline.objects.get_or_create(pipeline=pipeline, location=aipstore)
    return aipstore


@pytest.mark.django_db
def test_import_aip_command_creates_uncompressed_package(
    mocker, capsys, aip_storage_location
):
    mocker.patch("os.chown")
    mocker.patch("pwd.getpwnam")
    mocker.patch("logging.config")
    call_command(
        "import_aip",
        "--decompress-source",
        "--aip-storage-location",
        aip_storage_location.uuid,
        AIP_PATH,
    )
    captured = capsys.readouterr()
    assert "Successfully imported AIP" in captured.out

    # Verify a new package was created.
    assert models.Package.objects.count() == 1

    # Verify package is not compressed.
    package = models.Package.objects.first()

    assert not package.is_compressed


@pytest.mark.parametrize(
    "compression_algorithm",
    [
        ("7z with bzip"),
        ("7z without compression"),
    ],
)
@pytest.mark.django_db
def test_import_aip_command_creates_compressed_package(
    mocker, capsys, aip_storage_location, compression_algorithm
):
    mocker.patch("os.chown")
    mocker.patch("pwd.getpwnam")
    mocker.patch("logging.config")
    call_command(
        "import_aip",
        "--decompress-source",
        "--aip-storage-location",
        aip_storage_location.uuid,
        AIP_PATH,
        "--compression-algorithm",
        compression_algorithm,
    )
    captured = capsys.readouterr()
    assert "Successfully imported AIP" in captured.out

    # Verify a new package was created.
    assert models.Package.objects.count() == 1

    # Verify package is compressed.
    package = models.Package.objects.first()

    assert package.is_compressed
