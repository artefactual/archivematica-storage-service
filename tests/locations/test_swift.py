import os
import pathlib
from unittest import mock

import pytest
import swiftclient

from archivematica.storage_service.locations import models
from archivematica.storage_service.locations.models.swift import Swift
from tests.factories import SpaceFactory


@pytest.fixture
def swift(make_space: SpaceFactory) -> Swift:
    """A Swift space of the Toronto region."""
    space = make_space(
        access_protocol=models.Space.SWIFT,
        path="/",
        staging_path="/var/archivematica/storage_service/",
    )

    return Swift.objects.create(
        space=space,
        auth_url="http://142.1.121.240:5000/v2.0/",
        auth_version="2",
        username="toronto_admin",
        password="torontoAdmin12",
        container="artefactual",
        tenant="toronto",
        region="RegionOne",
    )


def test_has_required_attributes(swift: Swift) -> None:
    assert swift.auth_url
    assert swift.auth_version
    assert swift.username
    assert swift.password
    assert swift.container
    if swift.auth_version in ("2", "2.0", 2):
        assert swift.tenant


@mock.patch(
    "swiftclient.client.Connection.get_container",
    side_effect=[
        (
            None,
            [
                {
                    "hash": "f9a8cd53314cd3319eee0699bda2c705",
                    "last_modified": "2015-04-10T21:52:09.559240",
                    "bytes": 13187,
                    "name": "transfers/SampleTransfers/BagTransfer.zip",
                    "content_type": "application/zip",
                },
                {"subdir": "transfers/SampleTransfers/Images/"},
                {"subdir": "transfers/SampleTransfers/badNames/"},
            ],
        )
    ],
)
def test_browse(_get_container: mock.MagicMock, swift: Swift) -> None:
    resp = swift.browse("transfers/SampleTransfers")
    assert resp
    assert resp["directories"] == ["badNames", "Images"]
    assert resp["entries"] == ["badNames", "BagTransfer.zip", "Images"]
    assert resp["properties"]["BagTransfer.zip"]["size"] == 13187
    assert (
        resp["properties"]["BagTransfer.zip"]["timestamp"]
        == "2015-04-10T21:52:09.559240"
    )


@mock.patch(
    "swiftclient.client.Connection.get_container",
    side_effect=[
        (
            None,
            [
                {
                    "hash": "4829f38a294d156345922db8abd5e91c",
                    "last_modified": "2015-04-10T21:56:43.176070",
                    "bytes": 1437654,
                    "name": "transfers/SampleTransfers/Images/799px-Euroleague-LE Roma vs Toulouse IC-27.bmp",
                    "content_type": "image/x-ms-bmp",
                },
                {
                    "hash": "c14bda842e2889a732e0f5f9d8c0ae73",
                    "last_modified": "2015-04-10T21:56:42.854240",
                    "bytes": 1080282,
                    "name": "transfers/SampleTransfers/Images/BBhelmet.ai",
                    "content_type": "application/postscript",
                },
                {
                    "hash": "1ea4939968f117de97b15437c6348847",
                    "last_modified": "2015-04-10T21:56:42.014940",
                    "bytes": 125968,
                    "name": "transfers/SampleTransfers/Images/G31DS.TIF",
                    "content_type": "image/tiff",
                },
                {
                    "hash": "0b0f9676ead317f643e9a58f0177d1e6",
                    "last_modified": "2015-04-10T21:56:43.695970",
                    "bytes": 2050617,
                    "name": "transfers/SampleTransfers/Images/Nemastylis_geminiflora_Flower.PNG",
                    "content_type": "image/png",
                },
                {
                    "hash": "8dd3a652970aa7f130414305b92ab8a8",
                    "last_modified": "2015-04-10T21:56:43.724420",
                    "bytes": 1041114,
                    "name": "transfers/SampleTransfers/Images/Vector.NET-Free-Vector-Art-Pack-28-Freedom-Flight.eps",
                    "content_type": "application/postscript",
                },
                {
                    "hash": "2eb15cb1834214b05d0083c691f9545f",
                    "last_modified": "2015-04-10T21:56:43.198720",
                    "bytes": 113318,
                    "name": "transfers/SampleTransfers/Images/WFPC01.GIF",
                    "content_type": "image/gif",
                },
                {
                    "hash": "e5913bebe296eb433fdade7400860e73",
                    "last_modified": "2015-04-10T21:56:43.355320",
                    "bytes": 18324,
                    "name": "transfers/SampleTransfers/Images/lion.svg",
                    "content_type": "image/svg+xml",
                },
                {
                    "hash": "04f7802b45838fed393d45afadaa9dcc",
                    "last_modified": "2015-04-10T21:56:42.578030",
                    "bytes": 527345,
                    "name": "transfers/SampleTransfers/Images/oakland03.jp2",
                    "content_type": "image/jp2",
                },
                {"subdir": "transfers/SampleTransfers/Images/pictures/"},
                {
                    "hash": "ac63a92ba5a94c337e740d6f189200d0",
                    "last_modified": "2015-04-10T21:56:43.264560",
                    "bytes": 158131,
                    "name": "transfers/SampleTransfers/Images/エブリンの写真.jpg",
                    "content_type": "image/jpeg",
                },
            ],
        )
    ],
)
def test_browse_unicode(_get_container: mock.MagicMock, swift: Swift) -> None:
    resp = swift.browse("transfers/SampleTransfers/Images")
    assert resp
    assert resp["directories"] == ["pictures"]
    assert resp["entries"] == [
        "799px-Euroleague-LE Roma vs Toulouse IC-27.bmp",
        "BBhelmet.ai",
        "G31DS.TIF",
        "lion.svg",
        "Nemastylis_geminiflora_Flower.PNG",
        "oakland03.jp2",
        "pictures",
        "Vector.NET-Free-Vector-Art-Pack-28-Freedom-Flight.eps",
        "WFPC01.GIF",
        "エブリンの写真.jpg",
    ]
    assert resp["properties"]["エブリンの写真.jpg"]["size"] == 158131
    assert (
        resp["properties"]["エブリンの写真.jpg"]["timestamp"]
        == "2015-04-10T21:56:43.264560"
    )


@mock.patch(
    "swiftclient.client.Connection.get_object", side_effect=[({}, b"%percent\n")]
)
def test_move_to_ss(
    _get_object: mock.MagicMock, swift: Swift, tmp_path: pathlib.Path
) -> None:
    test_file = tmp_path / "test" / "%percent.txt"
    assert not test_file.exists()
    # Test
    swift.move_to_storage_service(
        "transfers/SampleTransfers/badNames/objects/%percent.txt",
        str(test_file),
        None,
    )
    # Verify
    assert test_file.parent.is_dir()
    assert test_file.is_file()
    assert test_file.open().read() == "%percent\n"


@mock.patch(
    "swiftclient.client.Connection.get_object",
    side_effect=[swiftclient.exceptions.ClientException("error")],
)
@mock.patch(
    "swiftclient.client.Connection.get_container",
    side_effect=[
        ({}, []),
        ({}, []),
    ],
)
def test_move_to_ss_not_exist(
    _get_container: mock.MagicMock, _get_object: mock.MagicMock, swift: Swift
) -> None:
    test_file = "test/dne.txt"
    assert not os.path.exists(test_file)
    swift.move_to_storage_service(
        "transfers/SampleTransfers/does_not_exist.txt", test_file, None
    )
    # TODO is this what we want to happen?  Or should it fail louder?
    assert not os.path.exists(test_file)


@mock.patch(
    "swiftclient.client.Connection.get_object",
    side_effect=[
        swiftclient.exceptions.ClientException("error"),
        ({}, b"data\n"),
        ({}, b"test file\n"),
    ],
)
@mock.patch(
    "swiftclient.client.Connection.get_container",
    side_effect=[
        (
            {},
            [
                {
                    "hash": "6137cde4893c59f76f005a8123d8e8e6",
                    "last_modified": "2015-04-10T21:53:49.216490",
                    "bytes": 5,
                    "name": "transfers/SampleTransfers/badNames/objects/%/@at.txt",
                    "content_type": "text/plain",
                },
                {
                    "hash": "b05403212c66bdc8ccc597fedf6cd5fe",
                    "last_modified": "2015-04-15T00:13:56.534580",
                    "bytes": 10,
                    "name": "transfers/SampleTransfers/badNames/objects/%/control.txt",
                    "content_type": "text/plain",
                },
            ],
        ),
    ],
)
def test_move_to_ss_folder(
    _get_container: mock.MagicMock,
    _get_object: mock.MagicMock,
    swift: Swift,
    tmp_path: pathlib.Path,
) -> None:
    test_dir = tmp_path / "test" / "subdir"
    assert not test_dir.exists()
    swift.move_to_storage_service(
        "transfers/SampleTransfers/badNames/objects/%/",
        str(test_dir) + os.sep,
        None,
    )
    # Verify
    assert test_dir.is_dir()
    assert (test_dir / "@at.txt").is_file()
    assert (test_dir / "@at.txt").open().read() == "data\n"
    assert (test_dir / "control.txt").is_file()
    assert (test_dir / "control.txt").open().read() == "test file\n"


@mock.patch(
    "swiftclient.client.Connection.get_object",
    side_effect=[
        ({"etag": "badbadbadbadbadbadbadbadbadbadbadbad"}, b"%percent\n"),
    ],
)
def test_move_to_ss_bad_etag(
    _get_object: mock.MagicMock, swift: Swift, tmp_path: pathlib.Path
) -> None:
    test_file = tmp_path / "test" / "%percent.txt"
    assert not test_file.exists()
    # Test
    with pytest.raises(models.StorageException):
        swift.move_to_storage_service(
            "transfers/SampleTransfers/badNames/objects/%percent.txt",
            str(test_file),
            None,
        )


@mock.patch("swiftclient.client.Connection.put_object")
@mock.patch(
    "swiftclient.client.Connection.get_container",
    side_effect=[
        (
            None,
            [
                {
                    "hash": "f9a8cd53314cd3319eee0699bda2c705",
                    "last_modified": "2015-04-10T21:52:09.559240",
                    "bytes": 13187,
                    "name": "transfers/SampleTransfers/BagTransfer.zip",
                    "content_type": "application/zip",
                },
                {"subdir": "transfers/SampleTransfers/Images/"},
                {"subdir": "transfers/SampleTransfers/badNames/"},
                {
                    "hash": "b05403212c66bdc8ccc597fedf6cd5fe",
                    "last_modified": "2015-04-15T17:16:00.490720",
                    "bytes": 10,
                    "name": "transfers/SampleTransfers/test.txt",
                    "content_type": "text/plain",
                },
            ],
        )
    ],
)
@mock.patch("swiftclient.client.Connection.delete_object")
def test_move_from_ss(
    _delete_object: mock.MagicMock,
    _get_container: mock.MagicMock,
    _put_object: mock.MagicMock,
    swift: Swift,
    tmp_path: pathlib.Path,
) -> None:
    # create test.txt
    test_file = tmp_path / "test.txt"
    test_file.open("w").write("test file\n")
    # Test
    swift.move_from_storage_service(
        str(test_file), "transfers/SampleTransfers/test.txt"
    )
    # Verify
    resp = swift.browse("transfers/SampleTransfers/")
    assert "test.txt" in resp["entries"]
    assert resp["properties"]["test.txt"]["size"] == 10
    # Cleanup
    swift.delete_path("transfers/SampleTransfers/test.txt")


@mock.patch(
    "swiftclient.client.Connection.get_container",
    side_effect=[
        (
            None,
            [
                {
                    "hash": "f9a8cd53314cd3319eee0699bda2c705",
                    "last_modified": "2015-04-10T21:52:09.559240",
                    "bytes": 13187,
                    "name": "transfers/SampleTransfers/BagTransfer.zip",
                    "content_type": "application/zip",
                },
                {"subdir": "transfers/SampleTransfers/Images/"},
                {"subdir": "transfers/SampleTransfers/badNames/"},
                {
                    "hash": "e24ec0474163959117efba0b10a0da94",
                    "last_modified": "2015-04-15T17:28:06.751910",
                    "bytes": 12,
                    "name": "transfers/SampleTransfers/test.txt",
                    "content_type": "text/plain",
                },
            ],
        ),
        (
            None,
            [
                {
                    "hash": "f9a8cd53314cd3319eee0699bda2c705",
                    "last_modified": "2015-04-10T21:52:09.559240",
                    "bytes": 13187,
                    "name": "transfers/SampleTransfers/BagTransfer.zip",
                    "content_type": "application/zip",
                },
                {"subdir": "transfers/SampleTransfers/Images/"},
                {"subdir": "transfers/SampleTransfers/badNames/"},
            ],
        ),
    ],
)
@mock.patch("swiftclient.client.Connection.delete_object")
def test_delete_path(
    _delete_object: mock.MagicMock, _get_container: mock.MagicMock, swift: Swift
) -> None:
    # Setup
    test_file = "transfers/SampleTransfers/test.txt"
    resp = swift.browse("transfers/SampleTransfers/")
    assert "test.txt" in resp["entries"]
    # Test
    swift.delete_path(test_file)
    # Verify deleted
    resp = swift.browse("transfers/SampleTransfers/")
    assert "test.txt" not in resp["entries"]


@mock.patch(
    "swiftclient.client.Connection.get_container",
    side_effect=[
        (
            None,
            [
                {
                    "hash": "f9a8cd53314cd3319eee0699bda2c705",
                    "last_modified": "2015-04-10T21:52:09.559240",
                    "bytes": 13187,
                    "name": "transfers/SampleTransfers/BagTransfer.zip",
                    "content_type": "application/zip",
                },
                {"subdir": "transfers/SampleTransfers/Images/"},
                {"subdir": "transfers/SampleTransfers/badNames/"},
                {"subdir": "transfers/SampleTransfers/test/"},
            ],
        ),
        (
            None,
            [
                {
                    "hash": "e24ec0474163959117efba0b10a0da94",
                    "last_modified": "2015-04-15T17:31:00.963200",
                    "bytes": 12,
                    "name": "transfers/SampleTransfers/test/test.txt",
                    "content_type": "text/plain",
                }
            ],
        ),
        (
            None,
            [
                {
                    "hash": "f9a8cd53314cd3319eee0699bda2c705",
                    "last_modified": "2015-04-10T21:52:09.559240",
                    "bytes": 13187,
                    "name": "transfers/SampleTransfers/BagTransfer.zip",
                    "content_type": "application/zip",
                },
                {"subdir": "transfers/SampleTransfers/Images/"},
                {"subdir": "transfers/SampleTransfers/badNames/"},
            ],
        ),
    ],
)
@mock.patch("swiftclient.client.Connection.delete_object")
def test_delete_folder(
    _delete_object: mock.MagicMock, _get_container: mock.MagicMock, swift: Swift
) -> None:
    # Check that exists already
    test_file = "transfers/SampleTransfers/test/"
    resp = swift.browse("transfers/SampleTransfers/")
    assert "test" in resp["directories"]
    # Test
    swift.delete_path(test_file)
    # Verify deleted
    resp = swift.browse("transfers/SampleTransfers/")
    assert "test" not in resp["directories"]
