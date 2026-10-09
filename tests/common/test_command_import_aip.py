import pathlib
import subprocess
from collections.abc import Sequence
from unittest import mock

import pytest
from django.core.management import call_command
from lxml import etree

from archivematica.storage_service.common import utils
from archivematica.storage_service.common.compression import CommandLineArchiver
from archivematica.storage_service.common.compression import override_archiver
from archivematica.storage_service.common.compression import run_command
from archivematica.storage_service.locations import models

TEST_DIR = pathlib.Path(__file__).resolve().parent
FIXTURES_DIR = TEST_DIR / "fixtures"
AIP_PATH = FIXTURES_DIR / "import_aip_test.7z"


@pytest.fixture
def aip_storage_location(
    aip_storage_location: models.Location,
    pipeline: models.Pipeline,
    ss_internal_location: models.Location,
) -> models.Location:
    """The AIP storage location of the pipeline, in the space of the internal
    location.
    """
    aip_storage_location.pipeline.add(pipeline)

    return aip_storage_location


@pytest.mark.django_db
@mock.patch("os.chown")
@mock.patch(
    "archivematica.storage_service.common.management.commands.import_aip.getpwnam"
)
def test_import_aip_command_creates_uncompressed_package(
    getpwnam, chown, capsys, aip_storage_location
):
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
    "compression_algorithm,expected_event_detail_algorithm",
    [
        ("7z with bzip", utils.COMPRESS_ALGO_BZIP2),
        ("7z without compression", utils.COMPRESS_ALGO_7Z_COPY),
    ],
)
@pytest.mark.django_db
@mock.patch("os.chown")
@mock.patch(
    "archivematica.storage_service.common.management.commands.import_aip.getpwnam"
)
@mock.patch("logging.config")
def test_import_aip_command_creates_compressed_package(
    logging_config,
    getpwnam,
    chown,
    capsys,
    aip_storage_location,
    compression_algorithm,
    expected_event_detail_algorithm,
):
    expected_event_detail_version = "p7zip Version 3.0"

    def run(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        """Run the real tools, but answer the 7z version probe with a banner."""
        if list(command) == ["7z"]:
            banner = f"\n7-Zip [64] 16.02 : Copyright (c) 1999-2016\n{expected_event_detail_version}\n"
            return subprocess.CompletedProcess(list(command), 0, banner, "")
        return run_command(command)

    with override_archiver(CommandLineArchiver(run=run)):
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

    # Verify the pointer file contains the compression event.
    assert package.full_pointer_file_path is not None
    root = etree.parse(package.full_pointer_file_path)
    event_details = root.xpath(
        ".//premis3:eventType[text()='compression']/../premis3:eventDetailInformation/premis3:eventDetail",
        namespaces=utils.NSMAP,
    )
    assert len(event_details) == 1
    assert (
        event_details[0].text.strip()
        == f"program=7z; algorithm={expected_event_detail_algorithm}; version={expected_event_detail_version}"
    )


@pytest.mark.django_db
@mock.patch("os.chown")
@mock.patch(
    "archivematica.storage_service.common.management.commands.import_aip.getpwnam"
)
def test_import_aip_command_sets_unix_owner(
    getpwnam: mock.MagicMock,
    chown: mock.MagicMock,
    capsys: pytest.CaptureFixture[str],
    aip_storage_location: models.Location,
) -> None:
    user = "foobar"
    user_id = 256
    user_group_id = 512
    getpwnam.return_value = mock.Mock(
        pw_name=user, pw_uid=user_id, pw_gid=user_group_id
    )

    call_command(
        "import_aip",
        "--decompress-source",
        "--aip-storage-location",
        aip_storage_location.uuid,
        AIP_PATH,
        "--unix-owner",
        user,
    )

    captured = capsys.readouterr()
    assert "Successfully imported AIP" in captured.out

    # Verify a new package was created.
    assert models.Package.objects.count() == 1

    getpwnam.assert_called_with(user)

    # Verify all calls to os.chown used the expected user ID and group ID.
    assert {(call.args[1], call.args[2]) for call in chown.mock_calls} == {
        (user_id, user_group_id)
    }
