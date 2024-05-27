import uuid

import pytest
from locations import models

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
def rclone_space(db):
    space = models.Space.objects.create(
        uuid=RCLONE_SPACE_UUID,
        access_protocol="RCLONE",
        staging_path="rclonestaging",
    )
    rclone_space = models.RClone.objects.create(
        space=space, remote_name="testremote", container="testcontainer"
    )
    return rclone_space


@pytest.fixture
def rclone_space_no_container(db):
    space = models.Space.objects.create(
        uuid=RCLONE_SPACE_UUID,
        access_protocol="RCLONE",
        staging_path="rclonestaging",
    )
    rclone_space = models.RClone.objects.create(
        space=space, remote_name="testremote", container=""
    )
    return rclone_space


@pytest.fixture
def rclone_aip(db):
    space = models.Space.objects.create(
        uuid=RCLONE_SPACE_UUID,
        access_protocol="RCLONE",
        staging_path="rclonestaging",
    )
    models.RClone.objects.create(
        space=space, remote_name="testremote", container="testcontainer"
    )
    pipeline = models.Pipeline.objects.create(uuid=PIPELINE_UUID)
    aipstore = models.Location.objects.create(
        uuid=RCLONE_AS_LOCATION_UUID, space=space, purpose="AS", relative_path="test"
    )
    models.LocationPipeline.objects.get_or_create(pipeline=pipeline, location=aipstore)
    aip = models.Package.objects.create(
        uuid=RCLONE_AIP_UUID,
        origin_pipeline=pipeline,
        current_location=aipstore,
        current_path="fixtures/small_compressed_bag.zip",
        size=1024,
    )
    return aip


@pytest.fixture
def rclone_aip_no_container(db):
    space = models.Space.objects.create(
        uuid=RCLONE_SPACE_UUID,
        access_protocol="RCLONE",
        staging_path="rclonestaging",
    )
    models.RClone.objects.create(space=space, remote_name="testremote", container="")
    pipeline = models.Pipeline.objects.create(uuid=PIPELINE_UUID)
    aipstore = models.Location.objects.create(
        uuid=RCLONE_AS_LOCATION_UUID, space=space, purpose="AS", relative_path="test"
    )
    models.LocationPipeline.objects.get_or_create(pipeline=pipeline, location=aipstore)
    aip = models.Package.objects.create(
        uuid=RCLONE_AIP_UUID,
        origin_pipeline=pipeline,
        current_location=aipstore,
        current_path="fixtures/small_compressed_bag.zip",
        size=1024,
    )
    return aip


def test_rclone_delete(mocker, rclone_aip):
    """Mock method call and assert correctness of rclone command."""
    delete_path = mocker.patch(
        "locations.models.rclone.RClone._execute_rclone_subcommand"
    )
    mocker.patch(
        "locations.models.rclone.RClone.remote_prefix",
        return_value="testremote:",
        new_callable=mocker.PropertyMock,
    )
    mocker.patch("locations.models.rclone.RClone._ensure_container_exists")

    rclone_aip.delete_from_storage()
    delete_path.assert_called_with(
        ["delete", "testremote:testcontainer/test/fixtures/small_compressed_bag.zip"]
    )


def test_rclone_delete_no_container(mocker, rclone_aip_no_container):
    """Mock method call and assert correctness of rclone command."""
    delete_path = mocker.patch(
        "locations.models.rclone.RClone._execute_rclone_subcommand"
    )
    mocker.patch(
        "locations.models.rclone.RClone.remote_prefix",
        return_value="testremote:",
        new_callable=mocker.PropertyMock,
    )

    rclone_aip_no_container.delete_from_storage()
    delete_path.assert_called_with(
        ["delete", "testremote:test/fixtures/small_compressed_bag.zip"]
    )


@pytest.mark.parametrize(
    "subprocess_return_code, raises_storage_exception",
    [
        # Test case where container already exists or is created.
        (0, False),
        # Test case where container doesn't exist and creating fails, resulting in exception.
        (1, True),
    ],
)
def test_rclone_ensure_container_exists(
    mocker,
    rclone_space,
    subprocess_return_code,
    raises_storage_exception,
):
    mocker.patch(
        "locations.models.rclone.RClone.remote_prefix",
        return_value="testremote:",
        new_callable=mocker.PropertyMock,
    )
    subprocess = mocker.patch("locations.models.rclone.subprocess")
    subprocess.Popen.return_value.returncode = subprocess_return_code
    subprocess.Popen.return_value.communicate.return_value = ("stdout", "stderr")

    if not raises_storage_exception:
        rclone_space._ensure_container_exists()
    else:
        with pytest.raises(models.StorageException):
            rclone_space._ensure_container_exists()
            subprocess.assert_called_with(["mkdir", "testremote:testcontainer"])


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
def test_rclone_remote_prefix(
    mocker,
    rclone_space,
    listremotes_return,
    expected_return,
    subprocess_return_code,
    raises_storage_exception,
):
    subprocess = mocker.patch("locations.models.rclone.subprocess")
    subprocess.Popen.return_value.communicate.return_value = (listremotes_return, "")
    subprocess.Popen.return_value.returncode = subprocess_return_code

    if not raises_storage_exception:
        remote_prefix = rclone_space.remote_prefix
        assert remote_prefix == expected_return
    else:
        with pytest.raises(models.StorageException):
            assert rclone_space.remote_prefix is not None


@pytest.mark.parametrize(
    "subprocess_communicate_return, subprocess_return_code, exception_raised",
    [
        # Test that stdout is returned
        (("stdout", ""), 0, False),
        # Test that non-zero return code results in StorageException.
        (("", ""), 1, True),
    ],
)
def test_rclone_execute_rclone_subcommand(
    mocker,
    rclone_space,
    subprocess_communicate_return,
    subprocess_return_code,
    exception_raised,
):
    subcommand = ["listremotes"]

    subprocess = mocker.patch("locations.models.rclone.subprocess")
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


@pytest.mark.parametrize(
    "package_is_file, expected_subcommand",
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
def test_rclone_move_to_storage_service(
    mocker, rclone_space, package_is_file, expected_subcommand
):
    exec_subprocess = mocker.patch(
        "locations.models.rclone.RClone._execute_rclone_subcommand"
    )
    mocker.patch(
        "locations.models.rclone.RClone.remote_prefix",
        return_value="testremote:",
        new_callable=mocker.PropertyMock,
    )
    mocker.patch("locations.models.rclone.RClone._ensure_container_exists")
    mocker.patch("common.utils.package_is_file", return_value=package_is_file)

    if package_is_file:
        rclone_space.move_to_storage_service(
            COMPRESSED_SRC_PATH, COMPRESSED_DEST_PATH, rclone_space
        )
    else:
        rclone_space.move_to_storage_service(
            UNCOMPRESSED_SRC_PATH, UNCOMPRESSED_DEST_PATH, rclone_space
        )
    exec_subprocess.assert_called_with(expected_subcommand)


@pytest.mark.parametrize(
    "package_is_file, expected_subcommand",
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
def test_rclone_move_to_storage_service_no_container(
    mocker, rclone_space_no_container, package_is_file, expected_subcommand
):
    exec_subprocess = mocker.patch(
        "locations.models.rclone.RClone._execute_rclone_subcommand"
    )
    mocker.patch(
        "locations.models.rclone.RClone.remote_prefix",
        return_value="testremote:",
        new_callable=mocker.PropertyMock,
    )
    mocker.patch("common.utils.package_is_file", return_value=package_is_file)

    if package_is_file:
        rclone_space_no_container.move_to_storage_service(
            COMPRESSED_SRC_PATH, COMPRESSED_DEST_PATH, rclone_space
        )
    else:
        rclone_space_no_container.move_to_storage_service(
            UNCOMPRESSED_SRC_PATH, UNCOMPRESSED_DEST_PATH, rclone_space
        )
    exec_subprocess.assert_called_with(expected_subcommand)


@pytest.mark.parametrize(
    "package_is_file, expected_subcommand",
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
def test_rclone_move_from_storage_service(
    mocker, rclone_space, package_is_file, expected_subcommand
):
    exec_subprocess = mocker.patch(
        "locations.models.rclone.RClone._execute_rclone_subcommand"
    )
    mocker.patch(
        "locations.models.rclone.RClone.remote_prefix",
        return_value="testremote:",
        new_callable=mocker.PropertyMock,
    )
    mocker.patch("locations.models.rclone.RClone._ensure_container_exists")
    mocker.patch("common.utils.package_is_file", return_value=package_is_file)
    mocker.patch("locations.models.Space.create_local_directory")

    if package_is_file:
        rclone_space.move_from_storage_service(
            COMPRESSED_SRC_PATH, COMPRESSED_DEST_PATH, rclone_space
        )
    else:
        rclone_space.move_from_storage_service(
            UNCOMPRESSED_SRC_PATH, UNCOMPRESSED_DEST_PATH, rclone_space
        )
    exec_subprocess.assert_called_with(expected_subcommand)


@pytest.mark.parametrize(
    "package_is_file, expected_subcommand",
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
def test_rclone_move_from_storage_service_no_container(
    mocker, rclone_space_no_container, package_is_file, expected_subcommand
):
    exec_subprocess = mocker.patch(
        "locations.models.rclone.RClone._execute_rclone_subcommand"
    )
    mocker.patch(
        "locations.models.rclone.RClone.remote_prefix",
        return_value="testremote:",
        new_callable=mocker.PropertyMock,
    )
    mocker.patch("common.utils.package_is_file", return_value=package_is_file)
    mocker.patch("locations.models.Space.create_local_directory")

    if package_is_file:
        rclone_space_no_container.move_from_storage_service(
            COMPRESSED_SRC_PATH, COMPRESSED_DEST_PATH, rclone_space
        )
    else:
        rclone_space_no_container.move_from_storage_service(
            UNCOMPRESSED_SRC_PATH, UNCOMPRESSED_DEST_PATH, rclone_space
        )
    exec_subprocess.assert_called_with(expected_subcommand)


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
def test_rclone_browse(
    mocker,
    rclone_space,
    subprocess_return,
    expected_properties,
    raises_storage_exception,
):
    exec_subprocess = mocker.patch(
        "locations.models.rclone.RClone._execute_rclone_subcommand"
    )
    exec_subprocess.return_value = subprocess_return
    mocker.patch(
        "locations.models.rclone.RClone.remote_prefix",
        return_value="testremote:",
        new_callable=mocker.PropertyMock,
    )
    mocker.patch("locations.models.rclone.RClone._ensure_container_exists")

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
def test_rclone_browse_no_container(
    mocker,
    rclone_space_no_container,
    subprocess_return,
    expected_properties,
    raises_storage_exception,
):
    exec_subprocess = mocker.patch(
        "locations.models.rclone.RClone._execute_rclone_subcommand"
    )
    exec_subprocess.return_value = subprocess_return
    mocker.patch(
        "locations.models.rclone.RClone.remote_prefix",
        return_value="testremote:",
        new_callable=mocker.PropertyMock,
    )

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
