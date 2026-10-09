import uuid
from unittest import mock

import pytest

from archivematica.storage_service.locations import models
from archivematica.storage_service.locations.models.rclone import RClone
from tests.factories import LocationFactory
from tests.factories import PackageFactory
from tests.factories import PipelineFactory
from tests.factories import SpaceFactory

RCLONE_SPACE_UUID = str(uuid.uuid4())
RCLONE_AS_LOCATION_UUID = str(uuid.uuid4())
RCLONE_AIP_UUID = str(uuid.uuid4())
PIPELINE_UUID = str(uuid.uuid4())

COMPRESSED_SRC_PATH = "/path/to/src/aip.7z"
COMPRESSED_DEST_PATH = "/path/to/dest/aip.7z"

UNCOMPRESSED_SRC_PATH = "/path/to/src/aip"
UNCOMPRESSED_DEST_PATH = "/path/to/dest/aip"

MOCK_LSJSON_STDOUT = b'[{"Name":"dir1","IsDir":true,"ModTime":"timevalue1"},{"Name":"dir2","IsDir":true,"ModTime":"timevalue2"},{"Name":"obj1.txt","IsDir":false,"ModTime":"timevalue3","MimeType":"text/plain","Size":1024},{"Name":"obj2.mp4","IsDir":false,"ModTime":"timevalue4","MimeType":"video/mp4","Size":2345567}]'


@pytest.fixture
def rclone_space(make_space: SpaceFactory) -> RClone:
    """An rclone space using the "testcontainer" container of its remote."""
    space = make_space(
        uuid=RCLONE_SPACE_UUID,
        access_protocol=models.Space.RCLONE,
        staging_path="rclonestaging",
    )

    return RClone.objects.create(
        space=space, remote_name="testremote", container="testcontainer"
    )


@pytest.fixture
def rclone_space_no_container(rclone_space: RClone) -> RClone:
    """The rclone space addressing its remote without a container."""
    rclone_space.container = ""
    rclone_space.save()

    return rclone_space


@pytest.fixture
def rclone_aip(
    rclone_space: RClone,
    make_pipeline: PipelineFactory,
    make_location: LocationFactory,
    make_package: PackageFactory,
) -> models.Package:
    """An AIP of a pipeline stored in the rclone space."""
    pipeline = make_pipeline(uuid=PIPELINE_UUID)
    aipstore = make_location(
        rclone_space.space,
        models.Location.AIP_STORAGE,
        uuid=RCLONE_AS_LOCATION_UUID,
        relative_path="test",
    )
    aipstore.pipeline.add(pipeline)

    return make_package(
        aipstore,
        "fixtures/small_compressed_bag.zip",
        uuid=RCLONE_AIP_UUID,
        origin_pipeline=pipeline,
        size=1024,
    )


@pytest.fixture
def rclone_aip_no_container(
    rclone_aip: models.Package, rclone_space_no_container: RClone
) -> models.Package:
    """The AIP once its space addresses the remote without a container."""
    return rclone_aip


@pytest.mark.django_db
@mock.patch(
    "archivematica.storage_service.locations.models.rclone.RClone._execute_rclone_subcommand"
)
@mock.patch(
    "archivematica.storage_service.locations.models.rclone.RClone.remote_prefix",
    return_value="testremote:",
    new_callable=mock.PropertyMock,
)
@mock.patch(
    "archivematica.storage_service.locations.models.rclone.RClone._ensure_container_exists"
)
def test_rclone_delete(
    _ensure_container_exists: mock.MagicMock,
    remote_prefix: mock.PropertyMock,
    _execute_rclone_subcommand: mock.MagicMock,
    rclone_aip: models.Package,
) -> None:
    """Mock method call and assert correctness of rclone command."""
    rclone_aip.delete_from_storage()
    _execute_rclone_subcommand.assert_called_with(
        ["delete", "testremote:testcontainer/test/fixtures/small_compressed_bag.zip"]
    )


@pytest.mark.django_db
@mock.patch(
    "archivematica.storage_service.locations.models.rclone.RClone._execute_rclone_subcommand"
)
@mock.patch(
    "archivematica.storage_service.locations.models.rclone.RClone.remote_prefix",
    return_value="testremote:",
    new_callable=mock.PropertyMock,
)
def test_rclone_delete_no_container(
    remote_prefix: mock.PropertyMock,
    _execute_rclone_subcommand: mock.MagicMock,
    rclone_aip_no_container: models.Package,
) -> None:
    """Mock method call and assert correctness of rclone command."""

    rclone_aip_no_container.delete_from_storage()
    _execute_rclone_subcommand.assert_called_with(
        ["delete", "testremote:test/fixtures/small_compressed_bag.zip"]
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    "subprocess_return_code, raises_storage_exception",
    [
        # Test case where container already exists or is created.
        (0, False),
        # Test case where container doesn't exist and creating fails, resulting in exception.
        (1, True),
    ],
)
@mock.patch(
    "archivematica.storage_service.locations.models.rclone.RClone.remote_prefix",
    return_value="testremote:",
    new_callable=mock.PropertyMock,
)
@mock.patch("archivematica.storage_service.locations.models.rclone.subprocess")
def test_rclone_ensure_container_exists(
    subprocess: mock.MagicMock,
    remote_prefix: mock.PropertyMock,
    rclone_space: RClone,
    subprocess_return_code: int,
    raises_storage_exception: bool,
) -> None:
    subprocess.Popen.return_value.returncode = subprocess_return_code
    subprocess.Popen.return_value.communicate.return_value = ("stdout", "stderr")

    if not raises_storage_exception:
        rclone_space._ensure_container_exists()
    else:
        with pytest.raises(models.StorageException):
            rclone_space._ensure_container_exists()
            subprocess.assert_called_with(["mkdir", "testremote:testcontainer"])


@pytest.mark.django_db
@pytest.mark.parametrize(
    "listremotes_return, expected_return, subprocess_return_code, raises_storage_exception",
    [
        # One matching remote returned from listremotes.
        ("testremote:\n", "testremote:", 0, False),
        # Several remotes returned from listremotes, including a match.
        ("another-remote:\ntestremote:\n", "testremote:", 0, False),
        # Several remotes returned from listremotes, no match.
        ("another-remote:\nnon-matching-remote:\n", None, 1, True),
    ],
)
@mock.patch("archivematica.storage_service.locations.models.rclone.subprocess")
def test_rclone_remote_prefix(
    subprocess: mock.MagicMock,
    rclone_space: RClone,
    listremotes_return: str,
    expected_return: str | None,
    subprocess_return_code: int,
    raises_storage_exception: bool,
) -> None:
    subprocess.Popen.return_value.communicate.return_value = (listremotes_return, "")
    subprocess.Popen.return_value.returncode = subprocess_return_code

    if not raises_storage_exception:
        remote_prefix = rclone_space.remote_prefix
        assert remote_prefix == expected_return
    else:
        with pytest.raises(models.StorageException):
            assert rclone_space.remote_prefix is not None


@pytest.mark.django_db
@pytest.mark.parametrize(
    "subprocess_communicate_return, subprocess_return_code, exception_raised",
    [
        # Test that stdout is returned
        (("stdout", ""), 0, False),
        # Test that non-zero return code results in StorageException.
        (("", ""), 1, True),
    ],
)
@mock.patch("archivematica.storage_service.locations.models.rclone.subprocess")
def test_rclone_execute_rclone_subcommand(
    subprocess: mock.MagicMock,
    rclone_space: RClone,
    subprocess_communicate_return: tuple[str, str],
    subprocess_return_code: int,
    exception_raised: bool,
) -> None:
    subcommand = ["listremotes"]

    subprocess.Popen.return_value.communicate.return_value = (
        subprocess_communicate_return
    )
    subprocess.Popen.return_value.returncode = subprocess_return_code
    if exception_raised:
        with pytest.raises(models.StorageException):
            rclone_space._execute_rclone_subcommand(subcommand)
    else:
        return_value = rclone_space._execute_rclone_subcommand(subcommand)
        assert return_value == subprocess_communicate_return[0]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "package_is_file_result, expected_subcommand",
    [
        # Package is file, expect "copyto" subcommand
        (
            True,
            [
                "copyto",
                "testremote:testcontainer/{}".format(COMPRESSED_SRC_PATH.lstrip("/")),
                COMPRESSED_DEST_PATH,
            ],
        ),
        # Package is directory, expect "copy" subcommand
        (
            False,
            [
                "copy",
                "testremote:testcontainer/{}".format(UNCOMPRESSED_SRC_PATH.lstrip("/")),
                UNCOMPRESSED_DEST_PATH + "/",
            ],
        ),
    ],
)
@mock.patch("archivematica.storage_service.common.utils.package_is_file")
@mock.patch(
    "archivematica.storage_service.locations.models.rclone.RClone._ensure_container_exists"
)
@mock.patch(
    "archivematica.storage_service.locations.models.rclone.RClone.remote_prefix",
    return_value="testremote:",
    new_callable=mock.PropertyMock,
)
@mock.patch(
    "archivematica.storage_service.locations.models.rclone.RClone._execute_rclone_subcommand"
)
def test_rclone_move_to_storage_service(
    _execute_rclone_subcommand: mock.MagicMock,
    remote_prefix: mock.PropertyMock,
    _ensure_container_exists: mock.MagicMock,
    package_is_file: mock.MagicMock,
    rclone_space: RClone,
    package_is_file_result: bool,
    expected_subcommand: list[str],
) -> None:
    package_is_file.return_value = package_is_file_result

    if package_is_file_result:
        rclone_space.move_to_storage_service(
            COMPRESSED_SRC_PATH, COMPRESSED_DEST_PATH, rclone_space
        )
    else:
        rclone_space.move_to_storage_service(
            UNCOMPRESSED_SRC_PATH, UNCOMPRESSED_DEST_PATH, rclone_space
        )
    _execute_rclone_subcommand.assert_called_with(expected_subcommand)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "package_is_file_result, expected_subcommand",
    [
        # Package is file, expect "copyto" subcommand
        (
            True,
            [
                "copyto",
                "testremote:{}".format(COMPRESSED_SRC_PATH.lstrip("/")),
                COMPRESSED_DEST_PATH,
            ],
        ),
        # Package is directory, expect "copy" subcommand
        (
            False,
            [
                "copy",
                "testremote:{}".format(UNCOMPRESSED_SRC_PATH.lstrip("/")),
                UNCOMPRESSED_DEST_PATH + "/",
            ],
        ),
    ],
)
@mock.patch("archivematica.storage_service.common.utils.package_is_file")
@mock.patch(
    "archivematica.storage_service.locations.models.rclone.RClone.remote_prefix",
    return_value="testremote:",
    new_callable=mock.PropertyMock,
)
@mock.patch(
    "archivematica.storage_service.locations.models.rclone.RClone._execute_rclone_subcommand"
)
def test_rclone_move_to_storage_service_no_container(
    _execute_rclone_subcommand: mock.MagicMock,
    remote_prefix: mock.PropertyMock,
    package_is_file: mock.MagicMock,
    rclone_space_no_container: RClone,
    package_is_file_result: bool,
    expected_subcommand: list[str],
) -> None:
    package_is_file.return_value = package_is_file_result

    if package_is_file_result:
        rclone_space_no_container.move_to_storage_service(
            COMPRESSED_SRC_PATH, COMPRESSED_DEST_PATH, rclone_space
        )
    else:
        rclone_space_no_container.move_to_storage_service(
            UNCOMPRESSED_SRC_PATH, UNCOMPRESSED_DEST_PATH, rclone_space
        )
    _execute_rclone_subcommand.assert_called_with(expected_subcommand)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "package_is_file_result, expected_subcommand",
    [
        # Package is file, expect "copyto" subcommand
        (
            True,
            [
                "copyto",
                COMPRESSED_SRC_PATH,
                "testremote:testcontainer/{}".format(COMPRESSED_DEST_PATH.lstrip("/")),
            ],
        ),
        # Package is directory, expect "copy" subcommand
        (
            False,
            [
                "copy",
                UNCOMPRESSED_SRC_PATH,
                "testremote:testcontainer/{}".format(
                    UNCOMPRESSED_DEST_PATH.lstrip("/")
                ),
            ],
        ),
    ],
)
@mock.patch(
    "archivematica.storage_service.locations.models.Space.create_local_directory"
)
@mock.patch("archivematica.storage_service.common.utils.package_is_file")
@mock.patch(
    "archivematica.storage_service.locations.models.rclone.RClone._ensure_container_exists"
)
@mock.patch(
    "archivematica.storage_service.locations.models.rclone.RClone.remote_prefix",
    return_value="testremote:",
    new_callable=mock.PropertyMock,
)
@mock.patch(
    "archivematica.storage_service.locations.models.rclone.RClone._execute_rclone_subcommand"
)
def test_rclone_move_from_storage_service(
    _execute_rclone_subcommand: mock.MagicMock,
    remote_prefix: mock.PropertyMock,
    _ensure_container_exists: mock.MagicMock,
    package_is_file: mock.MagicMock,
    create_local_directory: mock.MagicMock,
    rclone_space: RClone,
    package_is_file_result: bool,
    expected_subcommand: list[str],
) -> None:
    package_is_file.return_value = package_is_file_result

    if package_is_file_result:
        rclone_space.move_from_storage_service(
            COMPRESSED_SRC_PATH, COMPRESSED_DEST_PATH, rclone_space
        )
    else:
        rclone_space.move_from_storage_service(
            UNCOMPRESSED_SRC_PATH, UNCOMPRESSED_DEST_PATH, rclone_space
        )
    _execute_rclone_subcommand.assert_called_with(expected_subcommand)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "package_is_file_result, expected_subcommand",
    [
        # Package is file, expect "copyto" subcommand
        (
            True,
            [
                "copyto",
                COMPRESSED_SRC_PATH,
                "testremote:{}".format(COMPRESSED_DEST_PATH.lstrip("/")),
            ],
        ),
        # Package is directory, expect "copy" subcommand
        (
            False,
            [
                "copy",
                UNCOMPRESSED_SRC_PATH,
                "testremote:{}".format(UNCOMPRESSED_DEST_PATH.lstrip("/")),
            ],
        ),
    ],
)
@mock.patch(
    "archivematica.storage_service.locations.models.Space.create_local_directory"
)
@mock.patch("archivematica.storage_service.common.utils.package_is_file")
@mock.patch(
    "archivematica.storage_service.locations.models.rclone.RClone.remote_prefix",
    return_value="testremote:",
    new_callable=mock.PropertyMock,
)
@mock.patch(
    "archivematica.storage_service.locations.models.rclone.RClone._execute_rclone_subcommand"
)
def test_rclone_move_from_storage_service_no_container(
    _execute_rclone_subcommand: mock.MagicMock,
    remote_prefix: mock.PropertyMock,
    package_is_file: mock.MagicMock,
    create_local_directory: mock.MagicMock,
    rclone_space_no_container: RClone,
    package_is_file_result: bool,
    expected_subcommand: list[str],
) -> None:
    package_is_file.return_value = package_is_file_result

    if package_is_file_result:
        rclone_space_no_container.move_from_storage_service(
            COMPRESSED_SRC_PATH, COMPRESSED_DEST_PATH, rclone_space
        )
    else:
        rclone_space_no_container.move_from_storage_service(
            UNCOMPRESSED_SRC_PATH, UNCOMPRESSED_DEST_PATH, rclone_space
        )
    _execute_rclone_subcommand.assert_called_with(expected_subcommand)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "subprocess_return, expected_properties, raises_storage_exception",
    [
        # Test with stdout as expected.
        (
            MOCK_LSJSON_STDOUT,
            {
                "dir1": {"timestamp": "timevalue1"},
                "dir2": {"timestamp": "timevalue2"},
                "obj1.txt": {
                    "size": 1024,
                    "timestamp": "timevalue3",
                    "mimetype": "text/plain",
                },
                "obj2.mp4": {
                    "size": 2345567,
                    "timestamp": "timevalue4",
                    "mimetype": "video/mp4",
                },
            },
            False,
        ),
        # Test that stderr raises exception
        (b"", None, True),
    ],
)
@mock.patch(
    "archivematica.storage_service.locations.models.rclone.RClone._ensure_container_exists"
)
@mock.patch(
    "archivematica.storage_service.locations.models.rclone.RClone.remote_prefix",
    return_value="testremote:",
    new_callable=mock.PropertyMock,
)
@mock.patch(
    "archivematica.storage_service.locations.models.rclone.RClone._execute_rclone_subcommand"
)
def test_rclone_browse(
    _execute_rclone_subcommand: mock.MagicMock,
    remote_prefix: mock.PropertyMock,
    _ensure_container_exists: mock.MagicMock,
    rclone_space: RClone,
    subprocess_return: bytes,
    expected_properties: dict[str, dict[str, object]] | None,
    raises_storage_exception: bool,
) -> None:
    _execute_rclone_subcommand.return_value = subprocess_return

    if not raises_storage_exception:
        return_value = rclone_space.browse("/")
        assert sorted(return_value["directories"]) == ["dir1", "dir2"]
        assert sorted(return_value["entries"]) == [
            "dir1",
            "dir2",
            "obj1.txt",
            "obj2.mp4",
        ]
        assert return_value["properties"] == expected_properties
    else:
        with pytest.raises(models.StorageException):
            rclone_space.browse("/")


@pytest.mark.django_db
@pytest.mark.parametrize(
    "subprocess_return, expected_properties, raises_storage_exception",
    [
        # Test with stdout as expected.
        (
            MOCK_LSJSON_STDOUT,
            {
                "dir1": {"timestamp": "timevalue1"},
                "dir2": {"timestamp": "timevalue2"},
                "obj1.txt": {
                    "size": 1024,
                    "timestamp": "timevalue3",
                    "mimetype": "text/plain",
                },
                "obj2.mp4": {
                    "size": 2345567,
                    "timestamp": "timevalue4",
                    "mimetype": "video/mp4",
                },
            },
            False,
        ),
        # Test that stderr raises exception
        (b"", None, True),
    ],
)
@mock.patch(
    "archivematica.storage_service.locations.models.rclone.RClone.remote_prefix",
    return_value="testremote:",
    new_callable=mock.PropertyMock,
)
@mock.patch(
    "archivematica.storage_service.locations.models.rclone.RClone._execute_rclone_subcommand"
)
def test_rclone_browse_no_container(
    _execute_rclone_subcommand: mock.MagicMock,
    remote_prefix: mock.PropertyMock,
    rclone_space_no_container: RClone,
    subprocess_return: bytes,
    expected_properties: dict[str, dict[str, object]] | None,
    raises_storage_exception: bool,
) -> None:
    _execute_rclone_subcommand.return_value = subprocess_return

    if not raises_storage_exception:
        return_value = rclone_space_no_container.browse("/")
        assert sorted(return_value["directories"]) == ["dir1", "dir2"]
        assert sorted(return_value["entries"]) == [
            "dir1",
            "dir2",
            "obj1.txt",
            "obj2.mp4",
        ]
        assert return_value["properties"] == expected_properties
    else:
        with pytest.raises(models.StorageException):
            rclone_space_no_container.browse("/")
