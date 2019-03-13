# -*- coding: utf-8 -*-
import os
import shutil

from django.test import TestCase
import pytest
import vcr

from locations import models

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
FIXTURES_DIR = os.path.abspath(os.path.join(THIS_DIR, "..", "fixtures"))


class TestSwift(TestCase):

    fixtures = ["base.json", "swift.json"]

    def setUp(self):
        self.swift_object = models.Swift.objects.all()[0]

    def tearDown(self):
        if os.path.exists("test"):
            shutil.rmtree("test")
        if os.path.exists("test.txt"):
            os.remove("test.txt")

    def test_has_required_attributes(self):
        assert self.swift_object.auth_url
        assert self.swift_object.auth_version
        assert self.swift_object.username
        assert self.swift_object.password
        assert self.swift_object.container
        if self.swift_object.auth_version in ("2", "2.0", 2):
            assert self.swift_object.tenant

    @vcr.use_cassette(os.path.join(FIXTURES_DIR, "vcr_cassettes", "swift_browse.yaml"))
    def test_browse(self):
        resp = self.swift_object.browse("transfers/SampleTransfers")
        assert resp
        assert resp["directories"] == ["badNames", "Images"]
        assert resp["entries"] == ["badNames", "BagTransfer.zip", "Images"]
        assert resp["properties"]["BagTransfer.zip"]["size"] == 13187
        assert (
            resp["properties"]["BagTransfer.zip"]["timestamp"]
            == "2015-04-10T21:52:09.559240"
        )

    @vcr.use_cassette(
        os.path.join(FIXTURES_DIR, "vcr_cassettes", "swift_browse_unicode.yaml")
    )
    def test_browse_unicode(self):
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
            u"エブリンの写真.jpg",
        ]
        assert resp["properties"][u"エブリンの写真.jpg"]["size"] == 158131
        assert (
            resp["properties"][u"エブリンの写真.jpg"]["timestamp"]
            == "2015-04-10T21:56:43.264560"
        )

    @vcr.use_cassette(os.path.join(FIXTURES_DIR, "vcr_cassettes", "swift_move_to.yaml"))
    def test_move_to_ss(self):
        test_file = "test/%percent.txt"
        # Not here already
        try:
            os.remove(test_file)
        except OSError:
            pass
        assert not os.path.exists(test_file)
        # Test
        self.swift_object.move_to_storage_service(
            "transfers/SampleTransfers/badNames/objects/%percent.txt", test_file, None
        )
        # Verify
        assert os.path.isdir("test")
        assert os.path.isfile(test_file)
        assert open(test_file, "r").read() == "%percent\n"

    @vcr.use_cassette(
        os.path.join(FIXTURES_DIR, "vcr_cassettes", "swift_move_to_not_exist.yaml")
    )
    def test_move_to_ss_not_exist(self):
        test_file = "test/dne.txt"
        assert not os.path.exists(test_file)
        self.swift_object.move_to_storage_service(
            "transfers/SampleTransfers/does_not_exist.txt", test_file, None
        )
        # TODO is this what we want to happen?  Or should it fail louder?
        assert not os.path.exists(test_file)

    @vcr.use_cassette(
        os.path.join(FIXTURES_DIR, "vcr_cassettes", "swift_move_to_folder.yaml")
    )
    def test_move_to_ss_folder(self):
        test_dir = "test/subdir/"
        try:
            shutil.rmtree(test_dir)
        except (OSError, shutil.Error):
            pass
        assert not os.path.exists(test_dir)
        self.swift_object.move_to_storage_service(
            "transfers/SampleTransfers/badNames/objects/%/", test_dir, None
        )
        # Verify
        assert os.path.isdir(test_dir)
        assert os.path.isfile(os.path.join(test_dir, "@at.txt"))
        assert open(os.path.join(test_dir, "@at.txt"), "r").read() == "data\n"
        assert os.path.isfile(os.path.join(test_dir, "control.txt"))
        assert open(os.path.join(test_dir, "control.txt"), "r").read() == "test file\n"

    @vcr.use_cassette(
        os.path.join(FIXTURES_DIR, "vcr_cassettes", "swift_move_to_bad_etag.yaml")
    )
    def test_move_to_ss_bad_etag(self):
        test_file = "test/%percent.txt"
        # Not here already
        try:
            os.remove(test_file)
        except OSError:
            pass
        assert not os.path.exists(test_file)
        # Test
        with pytest.raises(models.StorageException):
            self.swift_object.move_to_storage_service(
                "transfers/SampleTransfers/badNames/objects/%percent.txt",
                test_file,
                None,
            )

    @vcr.use_cassette(
        os.path.join(FIXTURES_DIR, "vcr_cassettes", "swift_move_from.yaml")
    )
    def test_move_from_ss(self):
        # create test.txt
        open("test.txt", "w").write("test file\n")
        # Test
        self.swift_object.move_from_storage_service(
            "test.txt", "transfers/SampleTransfers/test.txt"
        )
        # Verify
        resp = self.swift_object.browse("transfers/SampleTransfers/")
        assert "test.txt" in resp["entries"]
        assert resp["properties"]["test.txt"]["size"] == 10
        # Cleanup
        self.swift_object.delete_path("transfers/SampleTransfers/test.txt")

    @vcr.use_cassette(os.path.join(FIXTURES_DIR, "vcr_cassettes", "swift_delete.yaml"))
    def test_delete_path(self):
        # Setup
        test_file = "transfers/SampleTransfers/test.txt"
        resp = self.swift_object.browse("transfers/SampleTransfers/")
        assert "test.txt" in resp["entries"]
        # Test
        self.swift_object.delete_path(test_file)
        # Verify deleted
        resp = self.swift_object.browse("transfers/SampleTransfers/")
        assert "test.txt" not in resp["entries"]

    @vcr.use_cassette(
        os.path.join(FIXTURES_DIR, "vcr_cassettes", "swift_delete_folder.yaml")
    )
    def test_delete_folder(self):
        # Check that exists already
        test_file = "transfers/SampleTransfers/test/"
        resp = self.swift_object.browse("transfers/SampleTransfers/")
        assert "test" in resp["directories"]
        # Test
        self.swift_object.delete_path(test_file)
        # Verify deleted
        resp = self.swift_object.browse("transfers/SampleTransfers/")
        assert "test" not in resp["directories"]
