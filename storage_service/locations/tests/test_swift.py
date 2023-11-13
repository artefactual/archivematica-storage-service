import os
from unittest import mock

import pytest
import swiftclient
from django.test import TestCase
from locations import models

from . import TempDirMixin


class TestSwift(TempDirMixin, TestCase):
    fixtures = ["base.json", "swift.json"]

    def setUp(self):
        super().setUp()
        self.swift_object = models.Swift.objects.first()

    def test_has_required_attributes(self):
        assert self.swift_object.auth_url
        assert self.swift_object.auth_version
        assert self.swift_object.username
        assert self.swift_object.password
        assert self.swift_object.container
        if self.swift_object.auth_version in ("2", "2.0", 2):
            assert self.swift_object.tenant

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
    def test_browse(self, _get_container):
        resp = self.swift_object.browse("transfers/SampleTransfers")
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
                        "name": "transfers/SampleTransfers/Images/\u30a8\u30d6\u30ea\u30f3\u306e\u5199\u771f.jpg",
                        "content_type": "image/jpeg",
                    },
                ],
            )
        ],
    )
    def test_browse_unicode(self, _get_container):
        resp = self.swift_object.browse("transfers/SampleTransfers/Images")
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
    def test_move_to_ss(self, _get_object):
        test_file = self.tmpdir / "test" / "%percent.txt"
        assert not test_file.exists()
        # Test
        self.swift_object.move_to_storage_service(
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
    def test_move_to_ss_not_exist(self, _get_container, _get_object):
        test_file = "test/dne.txt"
        assert not os.path.exists(test_file)
        self.swift_object.move_to_storage_service(
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
    def test_move_to_ss_folder(self, _get_container, _get_object):
        test_dir = self.tmpdir / "test" / "subdir"
        assert not test_dir.exists()
        self.swift_object.move_to_storage_service(
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
    def test_move_to_ss_bad_etag(self, _get_object):
        test_file = self.tmpdir / "test" / "%percent.txt"
        assert not test_file.exists()
        # Test
        with pytest.raises(models.StorageException):
            self.swift_object.move_to_storage_service(
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
    def test_move_from_ss(self, _delete_object, _get_container, _put_object):
        # create test.txt
        test_file = self.tmpdir / "test.txt"
        test_file.open("w").write("test file\n")
        # Test
        self.swift_object.move_from_storage_service(
            str(test_file), "transfers/SampleTransfers/test.txt"
        )
        # Verify
        resp = self.swift_object.browse("transfers/SampleTransfers/")
        assert "test.txt" in resp["entries"]
        assert resp["properties"]["test.txt"]["size"] == 10
        # Cleanup
        self.swift_object.delete_path("transfers/SampleTransfers/test.txt")

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
    def test_delete_path(self, _delete_object, _get_container):
        # Setup
        test_file = "transfers/SampleTransfers/test.txt"
        resp = self.swift_object.browse("transfers/SampleTransfers/")
        assert "test.txt" in resp["entries"]
        # Test
        self.swift_object.delete_path(test_file)
        # Verify deleted
        resp = self.swift_object.browse("transfers/SampleTransfers/")
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
    def test_delete_folder(self, _delete_object, _get_container):
        # Check that exists already
        test_file = "transfers/SampleTransfers/test/"
        resp = self.swift_object.browse("transfers/SampleTransfers/")
        assert "test" in resp["directories"]
        # Test
        self.swift_object.delete_path(test_file)
        # Verify deleted
        resp = self.swift_object.browse("transfers/SampleTransfers/")
        assert "test" not in resp["directories"]
