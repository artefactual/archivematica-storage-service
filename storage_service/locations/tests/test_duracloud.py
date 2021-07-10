from lxml import etree
import os
import shutil
import requests

from django.test import TestCase
import vcr

from locations import models
from . import TempDirMixin

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
FIXTURES_DIR = os.path.abspath(os.path.join(THIS_DIR, "..", "fixtures"))


class TestDuracloud(TempDirMixin, TestCase):

    fixtures = ["base.json", "duracloud.json"]

    def setUp(self):
        super().setUp()
        self.ds_object = models.Duracloud.objects.first()
        self.auth = requests.auth.HTTPBasicAuth(
            self.ds_object.user, self.ds_object.password
        )
        # Set the staging path of the space to a temporary directory.
        models.Space.objects.filter(uuid="6fb34c82-4222-425e-b0ea-30acfd31f52e").update(
            staging_path=str(self.tmpdir)
        )

    def test_has_required_attributes(self):
        assert self.ds_object.host
        assert self.ds_object.user
        assert self.ds_object.password
        assert self.ds_object.duraspace

    def test_generate_duracloud_request_includes_auth_headers(self):
        request = self.ds_object.generate_duracloud_request(
            "http://domain.tld:8000/tmp"
        )

        assert (
            request.headers.get("Authorization") == "Basic dHJpYWx1c2VyMjYzOnNzNnVtZkho"
        )

    @vcr.use_cassette(
        os.path.join(FIXTURES_DIR, "vcr_cassettes", "duracloud_browse.yaml")
    )
    def test_browse(self):
        resp = self.ds_object.browse("SampleTransfers")
        assert resp
        assert resp["directories"] == ["Images", "Multimedia", "OCRImage"]
        assert resp["entries"] == [
            "BagTransfer.zip",
            "Images",
            "Multimedia",
            "OCRImage",
        ]
        assert resp["properties"]["Images"]["object count"] == 10
        assert resp["properties"]["Multimedia"]["object count"] == 7
        assert resp["properties"]["OCRImage"]["object count"] == 1
        resp = self.ds_object.browse("SampleTransfers/Images")
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
        ]
        assert resp["properties"]["pictures"]["object count"] == 2

    @vcr.use_cassette(
        os.path.join(FIXTURES_DIR, "vcr_cassettes", "duracloud_browse_split_files.yaml")
    )
    def test_browse_split_files(self):
        # Hide split files
        resp = self.ds_object.browse("chunked")
        assert resp
        assert resp["directories"] == []
        assert resp["entries"] == ["chunked_image.jpg"]

    @vcr.use_cassette(
        os.path.join(FIXTURES_DIR, "vcr_cassettes", "duracloud_delete_file.yaml")
    )
    def test_delete_file(self):
        # Verify exists
        response = requests.head(
            "https://archivematica.duracloud.org/durastore/testing/delete/delete.svg",
            auth=self.auth,
        )
        assert response.status_code == 200
        # Delete file
        self.ds_object.delete_path("delete/delete.svg")
        # Verify deleted
        response = requests.head(
            "https://archivematica.duracloud.org/durastore/testing/delete/delete.svg",
            auth=self.auth,
        )
        assert response.status_code == 404

    @vcr.use_cassette(
        os.path.join(FIXTURES_DIR, "vcr_cassettes", "duracloud_delete_folder.yaml")
    )
    def test_delete_folder(self):
        # Verify exists
        response = requests.head(
            "https://archivematica.duracloud.org/durastore/testing/delete/delete/delete.svg",
            auth=self.auth,
        )
        assert response.status_code == 200
        response = requests.head(
            "https://archivematica.duracloud.org/durastore/testing/delete/delete.svg",
            auth=self.auth,
        )
        assert response.status_code == 200
        # Delete folder
        # BUG If delete_path is a folder but provided without a trailing /, will deleted a file with the same name.
        self.ds_object.delete_path("delete/delete/")
        # Verify deleted
        response = requests.head(
            "https://archivematica.duracloud.org/durastore/testing/delete/delete/delete.svg",
            auth=self.auth,
        )
        assert response.status_code == 404
        # Verify that file with same prefix not deleted
        response = requests.head(
            "https://archivematica.duracloud.org/durastore/testing/delete/delete.svg",
            auth=self.auth,
        )
        assert response.status_code == 200

    @vcr.use_cassette(
        os.path.join(
            FIXTURES_DIR, "vcr_cassettes", "duracloud_delete_percent_encoding.yaml"
        )
    )
    def test_delete_percent_encoding(self):
        # Verify exists
        response = requests.head(
            "https://archivematica.duracloud.org/durastore/testing/delete/delete%20%23.svg",
            auth=self.auth,
        )
        assert response.status_code == 200
        # Delete file
        self.ds_object.delete_path("delete/delete #.svg")
        # Verify deleted
        response = requests.head(
            "https://archivematica.duracloud.org/durastore/testing/delete/delete%20%23.svg",
            auth=self.auth,
        )
        assert response.status_code == 404

    @vcr.use_cassette(
        os.path.join(
            FIXTURES_DIR, "vcr_cassettes", "duracloud_delete_chunked_file.yaml"
        )
    )
    def test_delete_chunked_file(self):
        # Ensure file exists
        response = requests.head(
            "https://archivematica.duracloud.org/durastore/testing/delete/delete.svg",
            auth=self.auth,
        )
        assert response.status_code == 404
        response = requests.head(
            "https://archivematica.duracloud.org/durastore/testing/delete/delete.svg.dura-manifest",
            auth=self.auth,
        )
        assert response.status_code == 200
        response = requests.head(
            "https://archivematica.duracloud.org/durastore/testing/delete/delete.svg.dnd",
            auth=self.auth,
        )
        assert response.status_code == 200
        # Delete file
        self.ds_object.delete_path("delete/delete.svg")
        # Verify deleted
        response = requests.head(
            "https://archivematica.duracloud.org/durastore/testing/delete/delete.svg",
            auth=self.auth,
        )
        assert response.status_code == 404
        response = requests.head(
            "https://archivematica.duracloud.org/durastore/testing/delete/delete.svg.dura-manifest",
            auth=self.auth,
        )
        assert response.status_code == 404
        response = requests.head(
            "https://archivematica.duracloud.org/durastore/testing/delete/delete.svg.dura-chunk-0000",
            auth=self.auth,
        )
        assert response.status_code == 404
        response = requests.head(
            "https://archivematica.duracloud.org/durastore/testing/delete/delete.svg.dura-chunk-0001",
            auth=self.auth,
        )
        assert response.status_code == 404
        # Verify file with same prefix not deleted
        response = requests.head(
            "https://archivematica.duracloud.org/durastore/testing/delete/delete.svg.dnd",
            auth=self.auth,
        )
        assert response.status_code == 200

    @vcr.use_cassette(
        os.path.join(FIXTURES_DIR, "vcr_cassettes", "duracloud_move_from_ss_file.yaml")
    )
    def test_move_from_ss_file(self):
        # Create test.txt
        testfile = self.tmpdir / "test.txt"
        testfile.open("w").write("test file\n")
        # Upload
        self.ds_object.move_from_storage_service(str(testfile), "test/test.txt")
        # Verify
        response = requests.get(
            "https://archivematica.duracloud.org/durastore/testing/test/test.txt",
            auth=self.auth,
        )
        assert response.status_code == 200
        assert response.text == "test file\n"
        # Cleanup
        requests.delete(
            "https://"
            + self.ds_object.host
            + "/durastore/"
            + self.ds_object.duraspace
            + "/test/test.txt",
            auth=self.auth,
        )

    @vcr.use_cassette(
        os.path.join(
            FIXTURES_DIR, "vcr_cassettes", "duracloud_move_from_ss_folder.yaml"
        )
    )
    def test_move_from_ss_folder(self):
        # Create test folder
        testdir = self.tmpdir / "test"
        (testdir / "subfolder").mkdir(parents=True)
        (testdir / "test.txt").open("w").write("test file\n")
        (testdir / "subfolder" / "test2.txt").open("w").write("test file2\n")
        # Upload
        self.ds_object.move_from_storage_service(str(testdir) + os.sep, "test/foo/")
        # Verify
        response = requests.get(
            "https://archivematica.duracloud.org/durastore/testing/test/foo/test.txt",
            auth=self.auth,
        )
        assert response.status_code == 200
        assert response.text == "test file\n"
        response = requests.get(
            "https://archivematica.duracloud.org/durastore/testing/test/foo/subfolder/test2.txt",
            auth=self.auth,
        )
        assert response.status_code == 200
        assert response.text == "test file2\n"
        # Cleanup
        requests.delete(
            "https://"
            + self.ds_object.host
            + "/durastore/"
            + self.ds_object.duraspace
            + "/test/foo/test.txt",
            auth=self.auth,
        )
        requests.delete(
            "https://"
            + self.ds_object.host
            + "/durastore/"
            + self.ds_object.duraspace
            + "/test/foo/subfolder/test2.txt",
            auth=self.auth,
        )

    @vcr.use_cassette(
        os.path.join(
            FIXTURES_DIR,
            "vcr_cassettes",
            "duracloud_move_from_ss_percent_encoding.yaml",
        )
    )
    def test_move_from_ss_percent_encoding(self):
        # Create bad #name.txt
        testfile = self.tmpdir / "bad #name.txt"
        testfile.open("w").write("test file\n")
        # Upload
        self.ds_object.move_from_storage_service(str(testfile), "test/bad #name.txt")
        # Verify
        response = requests.get(
            "https://archivematica.duracloud.org/durastore/testing/test/bad%20%23name.txt",
            auth=self.auth,
        )
        assert response.status_code == 200
        assert response.text == "bad #name file\n"
        # Cleanup
        requests.delete(
            "https://"
            + self.ds_object.host
            + "/durastore/"
            + self.ds_object.duraspace
            + "/test/bad%20%23name.txt",
            auth=self.auth,
        )

    @vcr.use_cassette(
        os.path.join(
            FIXTURES_DIR, "vcr_cassettes", "duracloud_move_from_ss_chunked.yaml"
        )
    )
    def test_move_from_ss_chunked_file(self):
        shutil.copy(os.path.join(FIXTURES_DIR, "chunk_file.txt"), str(self.tmpdir))
        file_path = str(self.tmpdir / "chunk_file.txt")
        self.ds_object.CHUNK_SIZE = 10 * 1024  # Set testing chunk size
        self.ds_object.BUFFER_SIZE = 1
        # Upload
        self.ds_object.move_from_storage_service(
            file_path, "chunked/chunked #image.txt"
        )
        # Verify
        response = requests.get(
            "https://archivematica.duracloud.org/durastore/testing/chunked/chunked%20%23image.txt",
            auth=self.auth,
        )
        assert response.status_code == 404
        response = requests.get(
            "https://archivematica.duracloud.org/durastore/testing/chunked/chunked%20%23image.txt.dura-manifest",
            auth=self.auth,
        )
        assert response.status_code == 200
        # Verify manifest
        root = etree.fromstring(response.content)
        assert (
            root.find("header/sourceContent").attrib["contentId"]
            == "chunked/chunked #image.txt"
        )
        assert root.find("header/sourceContent/byteSize").text == "11037"
        assert (
            root.find("header/sourceContent/md5").text
            == "e7aba5d09b490b9f91c65867754ae190"
        )
        assert (
            root.find("chunks")[0].attrib["chunkId"]
            == "chunked/chunked #image.txt.dura-chunk-0000"
        )
        assert root.find("chunks")[0].find("byteSize").text == "10240"
        assert (
            root.find("chunks")[0].find("md5").text
            == "2147aa269812cac6204ad66ec953ccfe"
        )
        assert (
            root.find("chunks")[1].attrib["chunkId"]
            == "chunked/chunked #image.txt.dura-chunk-0001"
        )
        assert root.find("chunks")[1].find("byteSize").text == "797"
        assert (
            root.find("chunks")[1].find("md5").text
            == "aa9d2932a31f4b81cbfd1bcdb2c75020"
        )
        response = requests.get(
            "https://archivematica.duracloud.org/durastore/testing/chunked/chunked%20%23image.txt.dura-chunk-0000",
            auth=self.auth,
        )
        assert response.status_code == 200
        response = requests.get(
            "https://archivematica.duracloud.org/durastore/testing/chunked/chunked%20%23image.txt.dura-chunk-0001",
            auth=self.auth,
        )
        assert response.status_code == 200
        # Cleanup
        requests.delete(
            "https://"
            + self.ds_object.host
            + "/durastore/"
            + self.ds_object.duraspace
            + "/chunked/chunked%20%23image.txt.dura-manifest",
            auth=self.auth,
        )
        requests.delete(
            "https://"
            + self.ds_object.host
            + "/durastore/"
            + self.ds_object.duraspace
            + "/chunked/chunked%20%23image.txt.dura-chunk-0000",
            auth=self.auth,
        )
        requests.delete(
            "https://"
            + self.ds_object.host
            + "/durastore/"
            + self.ds_object.duraspace
            + "/chunked/chunked%20%23image.txt.dura-chunk-0001",
            auth=self.auth,
        )

    @vcr.use_cassette(
        os.path.join(
            FIXTURES_DIR, "vcr_cassettes", "duracloud_move_from_ss_chunked_resume.yaml"
        )
    )
    def test_move_from_ss_chunked_resume(self):
        # Setup
        shutil.copy(os.path.join(FIXTURES_DIR, "chunk_file.txt"), str(self.tmpdir))
        file_path = str(self.tmpdir / "chunk_file.txt")
        self.ds_object.CHUNK_SIZE = 10 * 1024  # Set testing chunk size
        self.ds_object.BUFFER_SIZE = 1
        requests.put(
            "https://"
            + self.ds_object.host
            + "/durastore/"
            + self.ds_object.duraspace
            + "/chunked/chunked_image.txt.dura-chunk-0000",
            auth=self.auth,
            data="Placeholder",
        )
        # Verify initial state
        response = requests.get(
            "https://archivematica.duracloud.org/durastore/testing/chunked/chunked_image.txt",
            auth=self.auth,
        )
        assert response.status_code == 404
        response = requests.get(
            "https://archivematica.duracloud.org/durastore/testing/chunked/chunked_image.txt.dura-manifest",
            auth=self.auth,
        )
        assert response.status_code == 404
        response = requests.get(
            "https://archivematica.duracloud.org/durastore/testing/chunked/chunked_image.txt.dura-chunk-0000",
            auth=self.auth,
        )
        assert response.status_code == 200
        response = requests.get(
            "https://archivematica.duracloud.org/durastore/testing/chunked/chunked_image.txt.dura-chunk-0001",
            auth=self.auth,
        )
        assert response.status_code == 404
        # Upload
        self.ds_object.move_from_storage_service(
            str(file_path), "chunked/chunked_image.txt", resume=True
        )
        # Verify
        response = requests.get(
            "https://archivematica.duracloud.org/durastore/testing/chunked/chunked_image.txt",
            auth=self.auth,
        )
        assert response.status_code == 404
        response = requests.get(
            "https://archivematica.duracloud.org/durastore/testing/chunked/chunked_image.txt.dura-manifest",
            auth=self.auth,
        )
        assert response.status_code == 200
        # Verify manifest
        root = etree.fromstring(response.content)
        assert (
            root.find("header/sourceContent").attrib["contentId"]
            == "chunked/chunked_image.txt"
        )
        assert root.find("header/sourceContent/byteSize").text == "11037"
        assert (
            root.find("header/sourceContent/md5").text
            == "e7aba5d09b490b9f91c65867754ae190"
        )
        assert (
            root.find("chunks")[0].attrib["chunkId"]
            == "chunked/chunked_image.txt.dura-chunk-0000"
        )
        assert root.find("chunks")[0].find("byteSize").text == "10240"
        assert (
            root.find("chunks")[0].find("md5").text
            == "2147aa269812cac6204ad66ec953ccfe"
        )
        assert (
            root.find("chunks")[1].attrib["chunkId"]
            == "chunked/chunked_image.txt.dura-chunk-0001"
        )
        assert root.find("chunks")[1].find("byteSize").text == "797"
        assert (
            root.find("chunks")[1].find("md5").text
            == "aa9d2932a31f4b81cbfd1bcdb2c75020"
        )
        response = requests.get(
            "https://archivematica.duracloud.org/durastore/testing/chunked/chunked_image.txt.dura-chunk-0000",
            auth=self.auth,
        )
        assert response.status_code == 200
        assert response.text == "Placeholder"
        response = requests.get(
            "https://archivematica.duracloud.org/durastore/testing/chunked/chunked_image.txt.dura-chunk-0001",
            auth=self.auth,
        )
        assert response.status_code == 200
        # Cleanup
        requests.delete(
            "https://"
            + self.ds_object.host
            + "/durastore/"
            + self.ds_object.duraspace
            + "/chunked/chunked_image.txt.dura-manifest",
            auth=self.auth,
        )
        requests.delete(
            "https://"
            + self.ds_object.host
            + "/durastore/"
            + self.ds_object.duraspace
            + "/chunked/chunked_image.txt.dura-chunk-0000",
            auth=self.auth,
        )
        requests.delete(
            "https://"
            + self.ds_object.host
            + "/durastore/"
            + self.ds_object.duraspace
            + "/chunked/chunked_image.txt.dura-chunk-0001",
            auth=self.auth,
        )

    @vcr.use_cassette(
        os.path.join(FIXTURES_DIR, "vcr_cassettes", "duracloud_move_to_ss_file.yaml")
    )
    def test_move_to_ss_file(self):
        tmpdir = self.tmpdir / "move_to_ss_file_dir"
        tmpfile = tmpdir / "test.txt"
        # Test file
        self.ds_object.move_to_storage_service("test/test.txt", str(tmpfile), None)
        assert tmpdir.is_dir()
        assert tmpfile.is_file()
        assert tmpfile.open().read() == "test file\n"

    @vcr.use_cassette(
        os.path.join(FIXTURES_DIR, "vcr_cassettes", "duracloud_move_to_ss_folder.yaml")
    )
    def test_move_to_ss_folder(self):
        tmpdir = self.tmpdir / "move_to_ss_file_dir"
        # Test folder
        self.ds_object.move_to_storage_service(
            "test/foo/", str(tmpdir / "test") + os.sep, None
        )
        assert tmpdir.is_dir()
        assert (tmpdir / "test").is_dir()
        assert (tmpdir / "test" / "subfolder").is_dir()
        assert (tmpdir / "test" / "test.txt").is_file()
        assert (tmpdir / "test" / "test.txt").open().read() == "test file\n"
        assert (tmpdir / "test" / "subfolder" / "test2.txt").is_file()
        assert (
            tmpdir / "test" / "subfolder" / "test2.txt"
        ).open().read() == "test file2\n"

    @vcr.use_cassette(
        os.path.join(
            FIXTURES_DIR, "vcr_cassettes", "duracloud_move_to_ss_folder_globbing.yaml"
        )
    )
    def test_move_to_ss_folder_globbing(self):
        tmpdir = self.tmpdir / "move_to_ss_folder_globbing_dir"
        # Test with globbing
        self.ds_object.move_to_storage_service(
            "test/foo/.", str(tmpdir / "test") + os.sep, None
        )
        assert tmpdir.is_dir()
        assert (tmpdir / "test").is_dir()
        assert (tmpdir / "test" / "subfolder").is_dir()
        assert (tmpdir / "test" / "test.txt").is_file()
        assert (tmpdir / "test" / "test.txt").open().read() == "test file\n"
        assert (tmpdir / "test" / "subfolder" / "test2.txt").is_file()
        assert (
            tmpdir / "test" / "subfolder" / "test2.txt"
        ).open().read() == "test file2\n"

    @vcr.use_cassette(
        os.path.join(
            FIXTURES_DIR, "vcr_cassettes", "duracloud_move_to_ss_percent_encoding.yaml"
        )
    )
    def test_move_to_ss_percent_encoding(self):
        testdir = self.tmpdir / "move_to_ss_percent_dir"
        testfile = testdir / "bad #name.txt"
        # Move to SS with # in path & filename
        self.ds_object.move_to_storage_service(
            "test/bad #name/bad #name.txt", str(testfile), None
        )
        # Verify
        assert testdir.is_dir()
        assert testfile.is_file()
        assert testfile.open().read() == "test file\n"

    @vcr.use_cassette(
        os.path.join(
            FIXTURES_DIR, "vcr_cassettes", "duracloud_move_to_ss_chunked_file.yaml"
        )
    )
    def test_move_to_ss_chunked_file(self):
        testdir = self.tmpdir / "move_to_ss_chunked"
        testfile = testdir / "chunked #image.jpg"
        # chunked #image.jpg is actually chunked
        self.ds_object.move_to_storage_service(
            "chunked/chunked #image.jpg", str(testfile), None
        )
        # Verify
        assert testdir.is_dir()
        assert not (testdir / "chunked #image.jpg.dura-manifest").exists()
        assert not (testdir / "chunked #image.jpg.dura-chunk-0000").exists()
        assert not (testdir / "chunked #image.jpg.dura-chunk-0001").exists()
        assert testfile.is_file()
        assert testfile.stat().st_size == 158131
