import os
import pathlib
import shutil
from unittest import mock

import pytest
import requests

from archivematica.storage_service.locations import models
from archivematica.storage_service.locations.models.arkivum import Arkivum

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"
PACKAGE_UUID = "c0f8498f-b92e-4a8b-8941-1b34ba062ed8"


def get_pkg_uuid_path(package_uuid):
    tmp = package_uuid.replace("-", "")
    return os.path.join(*[tmp[i : i + 4] for i in range(0, len(tmp), 4)])


@pytest.fixture
def arkivum(arkivum: Arkivum, tmp_path: pathlib.Path) -> Arkivum:
    """The Arkivum space of the fixtures, with its paths in the temporary
    directory.
    """
    arkivum.space.path = str(tmp_path)
    arkivum.space.staging_path = str(tmp_path)
    arkivum.space.save()
    arkivum.save()

    return arkivum


@pytest.fixture
def package(
    arkivum: Arkivum,
    arkivum_compressed_package: models.Package,
    tmp_path: pathlib.Path,
) -> models.Package:
    """The compressed package of the fixtures, with its pointer file where the
    package expects it in the Arkivum space.
    """
    result = arkivum_compressed_package
    pointer_file_location = result.pointer_file_location
    assert pointer_file_location is not None
    pointer_file_location.space = arkivum.space
    pointer_file_location.relative_path = "arkivum/storage_service"

    pointer_fname = f"pointer.{PACKAGE_UUID}.xml"
    pointer_dst_path = pathlib.Path(
        pointer_file_location.space.path,
        pointer_file_location.relative_path,
        get_pkg_uuid_path(PACKAGE_UUID),
        pointer_fname,
    )
    pointer_dst_path.parent.mkdir(parents=True)
    shutil.copyfile(FIXTURES_DIR / pointer_fname, pointer_dst_path)

    return result


@pytest.fixture
def uncompressed_package(
    arkivum_uncompressed_package: models.Package,
) -> models.Package:
    return arkivum_uncompressed_package


@pytest.fixture
def compressed_bag_path(tmp_path: pathlib.Path) -> pathlib.Path:
    """A copy of the compressed bag fixture in the temporary directory."""
    return pathlib.Path(shutil.copy(FIXTURES_DIR / "working_bag.zip", tmp_path))


@pytest.fixture
def arkivum_dir(package: models.Package, tmp_path: pathlib.Path) -> str:
    """The directory of the Arkivum space, which holds the pointer file of the
    package and some content to browse.
    """
    result = tmp_path / "arkivum"
    (result / "aips").mkdir()
    (result / "ts").mkdir()
    (result / "test.txt").open("ab").write(b"test.txt contents")

    return str(result)


def test_has_required_attributes(arkivum: Arkivum) -> None:
    assert arkivum.host
    # Both or neither of remote_user/remote_name
    assert bool(arkivum.remote_user) == bool(arkivum.remote_name)


def test_browse(arkivum: Arkivum, arkivum_dir: str) -> None:
    response = arkivum.browse(arkivum_dir)
    assert response
    assert set(response["directories"]) == {"aips", "ts", "storage_service"}
    assert set(response["entries"]) == {"aips", "test.txt", "ts", "storage_service"}
    assert response["properties"]["test.txt"]["size"] == 17
    assert response["properties"]["aips"]["object count"] == 0
    assert response["properties"]["ts"]["object count"] == 0


@mock.patch(
    "requests.get",
    side_effect=[
        mock.Mock(
            **{
                "status_code": 200,
                "json.return_value": {
                    "files": [
                        {"name": "test"},
                        {"name": "test.txt"},
                        {"name": "unittest.txt"},
                    ],
                },
            }
        ),
        mock.Mock(
            **{
                "status_code": 200,
                "json.return_value": {
                    "files": [{"name": "test"}, {"name": "test.txt"}],
                },
            }
        ),
    ],
)
@mock.patch("requests.delete", side_effect=[mock.Mock(status_code=204)])
def test_delete(
    requests_delete: mock.MagicMock,
    requests_get: mock.MagicMock,
    arkivum: Arkivum,
) -> None:
    # Verify exists
    url = "https://" + arkivum.host + "/files/ts"
    response = requests.get(url, verify=False)
    assert "unittest.txt" in [x["name"] for x in response.json()["files"]]
    # Delete file
    arkivum.delete_path("/ts/unittest.txt")
    # Verify deleted
    url = "https://" + arkivum.host + "/files/ts"
    response = requests.get(url, verify=False)
    assert "unittest.txt" not in [x["name"] for x in response.json()["files"]]


@mock.patch(
    "requests.post",
    side_effect=[
        mock.Mock(
            **{
                "status_code": 202,
                "json.return_value": {"id": "a09f9c18-df2b-474f-8c7f-50eb3dedba2d"},
            }
        )
    ],
)
def test_post_move_from_ss(
    requests_post: mock.MagicMock,
    arkivum: Arkivum,
    package: models.Package,
    compressed_bag_path: pathlib.Path,
) -> None:
    # POST to Arkivum about file
    arkivum.post_move_from_storage_service(
        str(compressed_bag_path), package.full_path, package
    )
    assert package.misc_attributes["arkivum_identifier"] == (
        "a09f9c18-df2b-474f-8c7f-50eb3dedba2d"
    )


@mock.patch(
    "requests.get",
    side_effect=[
        mock.Mock(
            **{
                "status_code": 200,
                "json.return_value": {
                    "fileInformation": {"replicationState": "yellow"},
                },
            }
        ),
        mock.Mock(
            **{
                "status_code": 200,
                "json.return_value": {
                    "fileInformation": {"replicationState": "green"},
                },
            }
        ),
        mock.Mock(
            **{
                "status_code": 200,
                "json.return_value": {
                    "fileInformation": {"replicationState": "yellow"},
                },
            }
        ),
    ],
)
def test_update_package_status_compressed(
    requests_get: mock.MagicMock,
    arkivum: Arkivum,
    package: models.Package,
    compressed_bag_path: pathlib.Path,
) -> None:
    # Setup request_id
    package.misc_attributes.update(
        {"arkivum_identifier": "2e75c8ad-cded-4f7e-8ac7-85627a116e39"}
    )
    package.save()
    # Verify status is STAGING
    assert package.status == models.Package.STAGING
    # Test (response yellow)
    arkivum.update_package_status(package)
    # Verify is still staged
    assert package.status == models.Package.STAGING
    # Test (response green)
    arkivum.update_package_status(package)
    # Verify UPLOADED
    assert package.status == models.Package.UPLOADED
    # Test (response yellow)
    arkivum.update_package_status(package)
    # Verify what?


@mock.patch(
    "requests.get",
    side_effect=[
        mock.Mock(
            **{
                "status_code": 200,
                "json.return_value": {
                    "id": "5afe9428-c6d6-4d0f-9196-5e7fd028726d",
                    "status": "Scheduled",
                },
            }
        ),
        mock.Mock(
            **{
                "status_code": 200,
                "json.return_value": {},
            }
        ),
        mock.Mock(
            **{
                "status_code": 200,
                "json.return_value": {
                    "processed": 18,
                    "replicationState": "red",
                    "fixityLastChecked": "2015-11-24",
                    "replicationStates": {"red": 18},
                    "id": "5afe9428-c6d6-4d0f-9196-5e7fd028726d",
                    "passed": "18",
                    "status": "Completed",
                },
            }
        ),
        mock.Mock(
            **{
                "status_code": 200,
                "json.return_value": {
                    "processed": 18,
                    "replicationState": "green",
                    "fixityLastChecked": "2015-11-24",
                    "replicationStates": {"green": 18},
                    "id": "5afe9428-c6d6-4d0f-9196-5e7fd028726d",
                    "passed": "18",
                    "status": "Completed",
                },
            }
        ),
    ],
)
def test_update_package_status_uncompressed(
    _requests_get: mock.MagicMock,
    arkivum: Arkivum,
    uncompressed_package: models.Package,
    tmp_path: pathlib.Path,
) -> None:
    uncompressed_package.current_path = str(tmp_path)
    # Setup request_id
    uncompressed_package.misc_attributes.update(
        {"arkivum_identifier": "5afe9428-c6d6-4d0f-9196-5e7fd028726d"}
    )
    uncompressed_package.save()
    # Verify status is STAGING
    assert uncompressed_package.status == models.Package.STAGING
    # Test (response Scheduled)
    arkivum.update_package_status(uncompressed_package)
    # Verify is still staged
    assert uncompressed_package.status == models.Package.STAGING
    # Test (response yellow)
    arkivum.update_package_status(uncompressed_package)
    # Verify is still staged
    assert uncompressed_package.status == models.Package.STAGING
    # Test (response green)
    arkivum.update_package_status(uncompressed_package)
    # Verify UPLOADED
    assert uncompressed_package.status == models.Package.UPLOADED
