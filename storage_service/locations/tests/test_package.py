import os
import pytest
import shutil
import tempfile
import vcr

import mock

from django.contrib.messages import get_messages
from django.core.urlresolvers import reverse
from django.test import TestCase

from locations import models

import bagit

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
FIXTURES_DIR = os.path.abspath(os.path.join(THIS_DIR, "..", "fixtures", ""))


class TestPackage(TestCase):

    fixtures = ["base.json", "package.json", "arkivum.json", "callback.json"]

    def setUp(self):
        self.package = models.Package.objects.all()[0]
        self.mets_path = os.path.normpath(
            os.path.join(__file__, "..", "..", "fixtures")
        )
        self.test_location = models.Location.objects.get(
            uuid="615103f0-0ee0-4a12-ba17-43192d1143ea"
        )
        # Set up locations to point to fixtures directory
        self.test_location.relative_path = FIXTURES_DIR[1:]
        self.test_location.save()
        # SS int points at fixtures directory
        models.Location.objects.filter(purpose="SS").update(
            relative_path=FIXTURES_DIR[1:]
        )
        # Arkivum space points at fixtures directory
        models.Space.objects.filter(uuid="6fb34c82-4222-425e-b0ea-30acfd31f52e").update(
            path=FIXTURES_DIR
        )

        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def test_view_package_delete(self):
        self.client.login(username="test", password="test")
        url = reverse("package_delete", args=["00000000-0000-0000-0000-000000000000"])

        # It does only accept POST, i.e. GET returns a 405
        response = self.client.get(url, follow=True)
        assert response.status_code == 405

        # It returns a 404 when the UUID is unknown
        response = self.client.post(url, follow=True)
        assert response.status_code == 404

        def verify_redirect_message(response, message):
            assert response.status_code == 200
            assert response.redirect_chain == [("http://testserver/packages/", 302)]
            messages = list(get_messages(response.wsgi_request))
            assert len(messages) == 1
            assert str(messages[0]) == message

        # It returns an "error" message when the package type is not allowed.
        url = reverse("package_delete", args=[self.package.uuid])
        response = self.client.post(url, follow=True)
        verify_redirect_message(
            response, "Package of type Transfer cannot be deleted directly"
        )

        # It returns a "success" message when the package was deleted
        # successfully.
        models.Package.objects.filter(uuid=self.package.uuid).update(
            package_type=models.Package.DIP
        )
        response = self.client.post(url, follow=True)
        verify_redirect_message(response, "Package deleted successfully!")

        # It returns an "error" message when the package could not be deleted
        # and the underlying code raised an exception.
        with mock.patch(
            "locations.models.Package.delete_from_storage", side_effect=ValueError
        ):
            response = self.client.post(url, follow=True)
            verify_redirect_message(
                response,
                "Package deletion failed. Please contact an"
                " administrator or see logs for details.",
            )

        # It returns an "error" message when the package could not be deleted.
        with mock.patch(
            "locations.models.Package.delete_from_storage",
            return_value=(False, "Something went wrong"),
        ):
            response = self.client.post(url, follow=True)
            verify_redirect_message(
                response,
                "Package deletion failed. Please contact an"
                " administrator or see logs for details.",
            )

    def test_parsing_mets_data(self):
        mets_data = self.package._parse_mets(prefix=self.mets_path)
        assert mets_data["transfer_uuid"] == "de1b31fa-97dd-48e0-8417-03be78359531"
        assert mets_data["dashboard_uuid"] == "23879cf0-a21a-40ee-bc50-357186746d15"
        assert mets_data["creation_date"] == "2015-02-21T01:55:08"
        assert len(mets_data["files"]) == 11
        # This file's name was sanitized, so check to see if the correct name is used
        for item in mets_data["files"]:
            if item["file_uuid"] != "742f10b0-768a-4158-b255-94847a97c465":
                continue
            assert (
                item["path"]
                == "images-transfer-de1b31fa-97dd-48e0-8417-03be78359531/objects/pictures/Landing_zone.jpg"
            )

    def test_files_are_added_to_database(self):
        self.package.index_file_data_from_transfer_mets(prefix=self.mets_path)
        assert (
            self.package.file_set.count() == 12
        )  # 11 from this METS, plus the one the fixture is already assigned
        assert (
            self.package.file_set.get(
                name="images-transfer-de1b31fa-97dd-48e0-8417-03be78359531/objects/pictures/Landing_zone.jpg"
            ).source_id
            == "742f10b0-768a-4158-b255-94847a97c465"
        )

    def test_fixity_success(self):
        """
        It should return success.
        It should return no errors.
        It should have an empty message.
        """
        package = models.Package.objects.get(
            uuid="0d4e739b-bf60-4b87-bc20-67a379b28cea"
        )
        success, failures, message, timestamp = package.check_fixity()
        assert success is True
        assert failures == []
        assert message == ""
        assert timestamp is None

    def test_fixity_failure(self):
        """
        It should return error.
        It should return a list of errors.
        It should have an error message.
        """
        package = models.Package.objects.get(
            uuid="9f260047-a9b7-4a75-bb6a-e8d94c83edd2"
        )
        success, failures, message, timestamp = package.check_fixity()
        assert success is False
        assert len(failures) == 1
        assert isinstance(failures[0], bagit.FileMissing)
        assert message == "Bag validation failed"
        assert timestamp is None

    def test_fixity_package_type(self):
        """ It should only fixity bags. """
        package = models.Package.objects.get(
            uuid="79245866-ca80-4f84-b904-a02b3e0ab621"
        )
        success, failures, message, timestamp = package.check_fixity()
        assert success is None
        assert failures == []
        assert "package is not a bag" in message
        assert timestamp is None

    @vcr.use_cassette(
        os.path.join(
            FIXTURES_DIR, "vcr_cassettes", "package_fixity_scheduled_arkivum.yaml"
        )
    )
    def test_fixity_scheduled_arkivum(self):
        """ It should return success of None. """
        package = models.Package.objects.get(
            uuid="e52c518d-fcf4-46cc-8581-bbc01aff7af3"
        )
        package.misc_attributes.update(
            {"arkivum_identifier": "5afe9428-c6d6-4d0f-9196-5e7fd028726d"}
        )
        package.save()
        success, failures, message, timestamp = package.check_fixity(force_local=False)
        assert success is None
        assert message == "Arkivum fixity check in progress"
        assert failures == []
        assert timestamp is None

    @vcr.use_cassette(
        os.path.join(FIXTURES_DIR, "vcr_cassettes", "package_fixity_amber_arkivum.yaml")
    )
    def test_fixity_amber_arkivum(self):
        """ It should return success of None. """
        package = models.Package.objects.get(
            uuid="e52c518d-fcf4-46cc-8581-bbc01aff7af3"
        )
        package.misc_attributes.update(
            {"arkivum_identifier": "5afe9428-c6d6-4d0f-9196-5e7fd028726d"}
        )
        package.save()
        success, failures, message, timestamp = package.check_fixity(force_local=False)
        assert success is None
        assert message == "Arkivum fixity check in progress"
        assert failures == []
        assert timestamp == "2015-11-24T00:00:00"

    @vcr.use_cassette(
        os.path.join(
            FIXTURES_DIR, "vcr_cassettes", "package_fixity_success_arkivum.yaml"
        )
    )
    def test_fixity_success_arkivum(self):
        """ It should return Arkivum's successful fixity not generate its own. """
        package = models.Package.objects.get(
            uuid="e52c518d-fcf4-46cc-8581-bbc01aff7af3"
        )
        package.misc_attributes.update(
            {"arkivum_identifier": "5afe9428-c6d6-4d0f-9196-5e7fd028726d"}
        )
        package.save()
        success, failures, message, timestamp = package.check_fixity(force_local=False)
        assert success is True
        assert message == ""
        assert failures == []
        assert timestamp == "2015-11-24T00:00:00"

    @vcr.use_cassette(
        os.path.join(
            FIXTURES_DIR, "vcr_cassettes", "package_fixity_failure_arkivum.yaml"
        )
    )
    def test_fixity_failure_arkivum(self):
        """ It should return success of False from Arkivum. """
        package = models.Package.objects.get(
            uuid="e52c518d-fcf4-46cc-8581-bbc01aff7af3"
        )
        package.misc_attributes.update(
            {"arkivum_identifier": "5afe9428-c6d6-4d0f-9196-5e7fd028726d"}
        )
        package.save()
        success, failures, message, timestamp = package.check_fixity(force_local=False)
        assert success is False
        assert message == "invalid bag"
        assert len(failures) == 2
        assert {
            "filepath": "data/test/test1.txt",
            "reason": "Initial verification failed",
        } in failures
        assert {
            "reason": "Initial verification failed",
            "filepath": "manifest-md5.txt",
        } in failures
        assert timestamp is None

    def test_fixity_force_local(self):
        """ It should do checksum locally if required. """
        package = models.Package.objects.get(
            uuid="e52c518d-fcf4-46cc-8581-bbc01aff7af3"
        )
        success, failures, message, timestamp = package.check_fixity(force_local=True)
        assert success is True
        assert failures == []
        assert message == ""
        assert timestamp is None

    def test_extract_file_aip_from_uncompressed_aip(self):
        """ It should return an aip """
        package = models.Package.objects.get(
            uuid="0d4e739b-bf60-4b87-bc20-67a379b28cea"
        )
        basedir = package.get_base_directory()
        output_path, extract_path = package.extract_file(extract_path=self.tmp_dir)
        assert output_path == os.path.join(self.tmp_dir, basedir)
        assert os.path.join(output_path, "manifest-md5.txt")

    def test_extract_file_file_from_uncompressed_aip(self):
        """ It should return a single file from an uncompressed aip """
        package = models.Package.objects.get(
            uuid="0d4e739b-bf60-4b87-bc20-67a379b28cea"
        )
        basedir = package.get_base_directory()
        output_path, extract_path = package.extract_file(
            relative_path="working_bag/manifest-md5.txt", extract_path=self.tmp_dir
        )
        assert output_path == os.path.join(self.tmp_dir, basedir, "manifest-md5.txt")
        assert os.path.isfile(output_path)

    def test_extract_file_file_from_compressed_aip(self):
        """ It should return a single file from a 7zip compressed aip """
        package = models.Package.objects.get(
            uuid="88deec53-c7dc-4828-865c-7356386e9399"
        )
        basedir = package.get_base_directory()
        output_path, extract_path = package.extract_file(
            relative_path="working_bag/manifest-md5.txt", extract_path=self.tmp_dir
        )
        assert output_path == os.path.join(extract_path, basedir, "manifest-md5.txt")
        assert os.path.isfile(output_path)

    def test_extract_file_file_does_not_exist_compressed(self):
        """ It should raise an error because the requested file does not exist"""
        package = models.Package.objects.get(
            uuid="88deec53-c7dc-4828-865c-7356386e9399"
        )
        with pytest.raises(Exception) as e_info:
            output_path, extract_path = package.extract_file(
                relative_path="working_bag/manifest-sha512.txt",
                extract_path=self.tmp_dir,
            )
        assert e_info.value.args[0] == "Extraction error"

    def test_extract_file_aip_from_compressed_aip(self):
        """ It should return an aip """
        package = models.Package.objects.get(
            uuid="88deec53-c7dc-4828-865c-7356386e9399"
        )
        basedir = package.get_base_directory()
        output_path, extract_path = package.extract_file(extract_path=self.tmp_dir)
        assert output_path == os.path.join(self.tmp_dir, basedir)
        assert os.path.join(output_path, "manifest-md5.txt")

    def test_run_post_store_callbacks_aip(self):
        uuid = "0d4e739b-bf60-4b87-bc20-67a379b28cea"
        aip = models.Package.objects.get(uuid=uuid)
        with mock.patch("locations.models.Callback.execute") as mocked_execute:
            aip.run_post_store_callbacks()
            # Only `post_store_aip` callbacks are executed
            assert mocked_execute.call_count == 1

    def test_run_post_store_callbacks_aic(self):
        uuid = "0d4e739b-bf60-4b87-bc20-67a379b28cea"
        aic, _ = models.Package.objects.update_or_create(
            uuid=uuid, defaults={"package_type": models.Package.AIC}
        )
        with mock.patch("locations.models.Callback.execute") as mocked_execute:
            aic.run_post_store_callbacks()
            # Only enabled callbacks are executed
            assert mocked_execute.call_count == 1

    def test_run_post_store_callbacks_dip(self):
        uuid = "0d4e739b-bf60-4b87-bc20-67a379b28cea"
        dip, _ = models.Package.objects.update_or_create(
            uuid=uuid, defaults={"package_type": models.Package.DIP}
        )
        with mock.patch("locations.models.Callback.execute") as mocked_execute:
            dip.run_post_store_callbacks()
            # Placeholder is replaced by the UUID in URI and body
            url = "https://consumer.com/api/v1/dip/%s/stored" % uuid
            body = '{"download_url": "http://ss.com/api/v2/file/%s/download/"}' % uuid
            mocked_execute.assert_called_with(url, body)

    def test_replicate_aip(self):
        space_dir = tempfile.mkdtemp(dir=self.tmp_dir, prefix="space")
        replication_dir = tempfile.mkdtemp(dir=self.tmp_dir, prefix="replication")
        aip = models.Package.objects.get(uuid="0d4e739b-bf60-4b87-bc20-67a379b28cea")
        aip.current_location.space.staging_path = space_dir
        aip.current_location.space.save()
        aip.current_location.replicators.create(
            space=aip.current_location.space,
            relative_path=replication_dir,
            purpose=models.Location.REPLICATOR,
        )

        aip.create_replicas()
        replica = aip.replicated_package

        assert replica is not None
        # The relationship is a little bit broken here; one would think that the
        # _original_ AIP should have replicas, and the replicated AIP should not.
        assert aip.replicas.count() == 0
        assert replica.replicas.count() == 1


class TestTransferPackage(TestCase):
    """Test integration of transfer reading and indexing.

    It uses ``tiny_transfer``, a small transfer part of fixtures/."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.space = models.Space.objects.create(path="/", access_protocol="FS")
        self.location = models.Location.objects.create(space=self.space, purpose="TB")

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def _create_transfer_package(self, fixture_dir, name, make_bagit=False):
        src = os.path.join(FIXTURES_DIR, fixture_dir)
        dst = os.path.join(self.tmp_dir, name)
        shutil.copytree(src, dst)
        if make_bagit:
            bagit.make_bag(dst)
        return models.Package.objects.create(
            current_location=self.location, current_path=dst
        )

    def test_transfer_indexing(self):
        package = self._create_transfer_package("tiny_transfer", "test1")
        file_data = package._parse_mets(package.full_path)
        assert len(file_data["files"]) == 1
        assert file_data["dashboard_uuid"] == "f1d803b9-c429-441c-bc3a-d9d334ac71bc"
        assert file_data["creation_date"] == "2019-03-06T22:06:02"
        assert file_data["accession_id"] == "12345"
        assert file_data["transfer_uuid"] == "328f0967-94a0-4376-bf92-9224da033248"
        assert file_data["files"][0]["path"] == "test1/objects/foobar.bmp"
        package.index_file_data_from_transfer_mets()
        files = models.File.objects.filter(package=package)
        assert files.count() == 1
        assert files[0].name == "test1/objects/foobar.bmp"

    def test_transfer_bagit_indexing(self):
        """Test that the path reflects the BagIt directory structure."""
        package = self._create_transfer_package(
            "tiny_transfer", "test2", make_bagit=True
        )
        file_data = package._parse_mets(package.full_path)
        assert file_data["files"][0]["path"] == "test2/data/objects/foobar.bmp"
        package.index_file_data_from_transfer_mets()
        files = models.File.objects.filter(package=package)
        assert files[0].name == "test2/data/objects/foobar.bmp"
