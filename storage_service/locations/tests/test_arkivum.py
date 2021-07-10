import os
import requests
import shutil
import vcr

from django.test import TestCase

from locations import models
from . import TempDirMixin

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
FIXTURES_DIR = os.path.abspath(os.path.join(THIS_DIR, "..", "fixtures"))


def get_pkg_uuid_path(package_uuid):
    tmp = package_uuid.replace("-", "")
    return os.path.join(*(tmp[i : i + 4] for i in range(0, len(tmp), 4)))


class TestArkivum(TempDirMixin, TestCase):

    fixtures = ["base.json", "arkivum.json"]

    def setUp(self):
        super().setUp()
        self.arkivum_object = models.Arkivum.objects.first()
        self.arkivum_object.space.path = str(self.tmpdir)
        self.arkivum_object.space.staging_path = str(self.tmpdir)
        self.arkivum_object.space.save()
        self.arkivum_object.save()
        package_uuid = "c0f8498f-b92e-4a8b-8941-1b34ba062ed8"
        self.package = models.Package.objects.get(uuid=package_uuid)
        # Here we make sure that the test pointer file is where the package
        # expects it to be.
        self.package.pointer_file_location.space = self.arkivum_object.space

        self.package.pointer_file_location.relative_path = "arkivum/storage_service"

        pointer_fname = "pointer." + package_uuid + ".xml"
        pointer_src_path = os.path.join(FIXTURES_DIR, pointer_fname)
        pointer_dst_path = os.path.join(
            self.package.pointer_file_location.space.path,
            self.package.pointer_file_location.relative_path,
            get_pkg_uuid_path(package_uuid),
            pointer_fname,
        )
        os.makedirs(os.path.dirname(pointer_dst_path))
        shutil.copyfile(pointer_src_path, pointer_dst_path)
        self.uncompressed_package = models.Package.objects.get(
            uuid="e52c518d-fcf4-46cc-8581-bbc01aff7af3"
        )

        # Create filesystem to interact with
        shutil.copy(os.path.join(FIXTURES_DIR, "working_bag.zip"), str(self.tmpdir))
        self.arkivum_dir = self.tmpdir / "arkivum"
        (self.arkivum_dir / "aips").mkdir()
        (self.arkivum_dir / "ts").mkdir()
        (self.arkivum_dir / "test.txt").open("ab").write(b"test.txt contents")
        self.arkivum_dir = str(self.arkivum_dir)

    def test_has_required_attributes(self):
        assert self.arkivum_object.host
        # Both or neither of remote_user/remote_name
        assert bool(self.arkivum_object.remote_user) == bool(
            self.arkivum_object.remote_name
        )

    def test_browse(self):
        response = self.arkivum_object.browse(self.arkivum_dir)
        assert response
        assert set(response["directories"]) == {"aips", "ts", "storage_service"}
        assert set(response["entries"]) == {"aips", "test.txt", "ts", "storage_service"}
        assert response["properties"]["test.txt"]["size"] == 17
        assert response["properties"]["aips"]["object count"] == 0
        assert response["properties"]["ts"]["object count"] == 0

    @vcr.use_cassette(
        os.path.join(FIXTURES_DIR, "vcr_cassettes", "arkivum_delete.yaml")
    )
    def test_delete(self):
        # Verify exists
        url = "https://" + self.arkivum_object.host + "/files/ts"
        response = requests.get(url, verify=False)
        assert "unittest.txt" in [x["name"] for x in response.json()["files"]]
        # Delete file
        self.arkivum_object.delete_path("/ts/unittest.txt")
        # Verify deleted
        url = "https://" + self.arkivum_object.host + "/files/ts"
        response = requests.get(url, verify=False)
        assert "unittest.txt" not in [x["name"] for x in response.json()["files"]]

        # Delete folder
        # self.arkivum_object.delete_path('/ts/test/')
        # Verify deleted

    # def test_move_from_ss(self):
    #     # TODO need to fake filesystem interactions
    #     # Create test.txt
    #     open('unittest.txt', 'w').write('test file\n')
    #     # Upload
    #     self.arkivum_object.move_from_storage_service('unittest.txt', '/mnt/arkivum/test/unittest.txt')
    #     # Verify
    #     url = 'https://' + self.arkivum_object.host + '/files/'
    #     response = requests.get(url, verify=False)
    #     assert 'test' in [x['name'] for x in response.json()['files']]
    #     url += 'test'
    #     response = requests.get(url, verify=False)
    #     assert 'unittest.txt' in [x['name'] for x in response.json()['files']]
    #     # Cleanup
    #     os.remove('unittest.txt')
    #     shutil.rmtree('/mnt/arkivum/test')

    #     # TODO test folder in new test

    @vcr.use_cassette(
        os.path.join(FIXTURES_DIR, "vcr_cassettes", "arkivum_post_move_from_ss.yaml")
    )
    def test_post_move_from_ss(self):
        # POST to Arkivum about file
        self.arkivum_object.post_move_from_storage_service(
            str(self.tmpdir / "working_bag.zip"), self.package.full_path, self.package
        )
        assert self.package.misc_attributes["arkivum_identifier"] == (
            "a09f9c18-df2b-474f-8c7f-50eb3dedba2d"
        )

    # def test_move_to_ss(self):
    #     # Test file
    #     self.arkivum_object.move_to_storage_service('/mnt/arkivum/ts/test.txt', 'folder/test.txt', None)
    #     assert os.path.isdir('folder')
    #     assert os.path.isfile('folder/test.txt')
    #     assert open('folder/test.txt', 'r').read() == 'test file\n'
    #     # Cleanup
    #     os.remove('folder/test.txt')
    #     os.removedirs('folder')
    #     # Test folder
    #     self.arkivum_object.move_to_storage_service('/mnt/arkivum/ts/test/', 'folder/test/', None)
    #     assert os.path.isdir('folder')
    #     assert os.path.isdir('folder/test')
    #     assert os.path.isdir('folder/test/subfolder')
    #     assert os.path.isfile('folder/test/test.txt')
    #     assert os.path.isfile('folder/test/subfolder/test2.txt')
    #     assert open('folder/test/test.txt').read() == 'test file\n'
    #     assert open('folder/test/subfolder/test2.txt').read() == 'test file2\n'
    #     # Cleanup
    #     os.remove('folder/test/test.txt')
    #     os.remove('folder/test/subfolder/test2.txt')
    #     os.removedirs('folder/test/subfolder')

    @vcr.use_cassette(
        os.path.join(
            FIXTURES_DIR, "vcr_cassettes", "arkivum_update_package_status.yaml"
        )
    )
    def test_update_package_status_compressed(self):
        # Setup request_id
        self.package.misc_attributes.update(
            {"arkivum_identifier": "2e75c8ad-cded-4f7e-8ac7-85627a116e39"}
        )
        self.package.save()
        # Verify status is STAGING
        assert self.package.status == models.Package.STAGING
        # Test (response yellow)
        self.arkivum_object.update_package_status(self.package)
        # Verify is still staged
        assert self.package.status == models.Package.STAGING
        # Test (response green)
        self.arkivum_object.update_package_status(self.package)
        # Verify UPLOADED
        assert self.package.status == models.Package.UPLOADED
        # Test (response yellow)
        self.arkivum_object.update_package_status(self.package)
        # Verify what?

    @vcr.use_cassette(
        os.path.join(
            FIXTURES_DIR,
            "vcr_cassettes",
            "arkivum_update_package_status_uncompressed.yaml",
        )
    )
    def test_update_package_status_uncompressed(self):
        self.uncompressed_package.current_path = str(self.tmpdir)
        # Setup request_id
        self.uncompressed_package.misc_attributes.update(
            {"arkivum_identifier": "5afe9428-c6d6-4d0f-9196-5e7fd028726d"}
        )
        self.uncompressed_package.save()
        # Verify status is STAGING
        assert self.uncompressed_package.status == models.Package.STAGING
        # Test (response Scheduled)
        self.arkivum_object.update_package_status(self.uncompressed_package)
        # Verify is still staged
        assert self.uncompressed_package.status == models.Package.STAGING
        # Test (response yellow)
        self.arkivum_object.update_package_status(self.uncompressed_package)
        # Verify is still staged
        assert self.uncompressed_package.status == models.Package.STAGING
        # Test (response green)
        self.arkivum_object.update_package_status(self.uncompressed_package)
        # Verify UPLOADED
        assert self.uncompressed_package.status == models.Package.UPLOADED
