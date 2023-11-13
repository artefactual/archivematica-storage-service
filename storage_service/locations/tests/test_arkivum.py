import os
import shutil
from unittest import mock

import requests
from django.test import TestCase
from locations import models

from . import TempDirMixin

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
FIXTURES_DIR = os.path.abspath(os.path.join(THIS_DIR, "..", "fixtures"))


def get_pkg_uuid_path(package_uuid):
    tmp = package_uuid.replace("-", "")
    return os.path.join(*[tmp[i : i + 4] for i in range(0, len(tmp), 4)])


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
    def test_delete(self, requests_delete, requests_get):
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
    def test_post_move_from_ss(self, requests_post):
        # POST to Arkivum about file
        self.arkivum_object.post_move_from_storage_service(
            str(self.tmpdir / "working_bag.zip"), self.package.full_path, self.package
        )
        assert self.package.misc_attributes["arkivum_identifier"] == (
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
    def test_update_package_status_compressed(self, requests_get):
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
    def test_update_package_status_uncompressed(self, _requests_get):
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
