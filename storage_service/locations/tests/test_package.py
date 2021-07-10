import datetime
import os
import pytest
import shutil
import tempfile
import time
import vcr

from unittest import mock

from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse

from common import utils
from locations import models

import bagit

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
FIXTURES_DIR = os.path.abspath(os.path.join(THIS_DIR, "..", "fixtures", ""))

# Fixture files are not cleanly separated, with potential for
# enumeration of PKs across both:
#
#   * 13 Packages in package.json
#   * 2 packages in Arkivum.json
#
TOTAL_FIXTURE_PACKAGES = 15


def recursive_file_count(target_dir):
    """Return count of files in directory based on recursive walk."""
    return sum(len(files) for _, _, files in os.walk(target_dir))


def recursive_dir_count(target_dir):
    """Return count of dirs in directory based on recursive walk."""
    return sum(len(dirs) for _, dirs, _ in os.walk(target_dir))


class TestPackage(TestCase):

    fixtures = ["base.json", "package.json", "arkivum.json", "callback.json"]

    def setUp(self):
        packages = models.Package.objects.all()
        assert (
            len(packages) == TOTAL_FIXTURE_PACKAGES
        ), "Packages not loaded from fixtures correctly, got '{}' expected '{}'".format(
            len(packages), TOTAL_FIXTURE_PACKAGES
        )

        self.package = packages[0]
        self.mets_path = os.path.normpath(
            os.path.join(__file__, "..", "..", "fixtures")
        )

        # Set up locations to point to fixtures directory
        FIXTURE_DIR_NO_LEADING_SLASH = FIXTURES_DIR[1:]
        self._point_location_at_on_disk_storage(
            "615103f0-0ee0-4a12-ba17-43192d1143ea", FIXTURE_DIR_NO_LEADING_SLASH
        )

        # Arkivum space points at fixtures directory
        models.Space.objects.filter(uuid="6fb34c82-4222-425e-b0ea-30acfd31f52e").update(
            path=FIXTURES_DIR
        )

        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def _point_location_at_on_disk_storage(self, location_uuid, location_on_disk):
        """Give tests the opportunity to modify the location of on-disk
        storage.

        :param location_uuid: the UUID of a storage location in the
            test database.
        :param location_on_disk: a folder, e.g. pointer to a temporary
            location that the test may want to read from and write to.
        """
        self.test_location = models.Location.objects.get(uuid=location_uuid)
        self.test_location.relative_path = location_on_disk
        self.test_location.save()
        models.Location.objects.filter(
            purpose=models.Location.STORAGE_SERVICE_INTERNAL
        ).update(relative_path=location_on_disk)

    def test_model_delete_from_storage(self):
        """Test that the Space delete method is called once for the
        deletion of an AIP from the storage service.
        """

        # Package that exists in the storage service.
        package = models.Package.objects.get(
            uuid="88deec53-c7dc-4828-865c-7356386e9399"
        )

        # Assert that is hasn't been deleted already.
        assert package.status == "Uploaded"

        # Using our context manager make sure that the deletion happens
        # once for our source object.
        with mock.patch("locations.models.Space.delete_path") as mocked_delete:
            package.delete_from_storage()
            assert mocked_delete.called

        # Ensure that location properties are updated reflecting the
        # size remaining.
        assert package.current_location.used == -package.size
        assert package.current_location.space.used == -package.size

        # Ensure that the package status is accurately updated to
        # DELETED.
        assert package.status == models.Package.DELETED

    def test_model_delete_from_storage_and_replicas(self):
        """Test that Space delete method is called three times for a
        package with two replicas. Once for the original package. Twice
        for the two replicas.
        """

        # Package with two replicas in the storage service.
        package = models.Package.objects.get(
            uuid="f0dfdc4c-7ba1-4e3f-a972-f2c55d870d04"
        )

        # Given our test object, make sure the replicas have equivalent
        # status.
        replicas = package._find_replicas()
        assert package.status == models.Package.UPLOADED
        assert replicas[0].status == models.Package.UPLOADED
        assert replicas[1].status == models.Package.UPLOADED

        # Using our context manager make sure that the deletion can be
        # measured three times per our test parameters.
        with mock.patch("locations.models.Space.delete_path") as mocked_delete:
            package.delete_from_storage()
            assert mocked_delete.called
            assert mocked_delete.call_count == 3

        # Ensure locations sizes are updated to reflect the size
        # remaining.
        assert package.current_location.used == -package.size
        assert package.current_location.space.used == -package.size

        # Ensure that the replicas and the original package have an
        # updated status of DELETED.
        replicas = package._find_replicas(status=models.Package.DELETED)
        assert package.status == models.Package.DELETED
        assert replicas[0].status == models.Package.DELETED
        assert replicas[1].status == models.Package.DELETED

    def test_model_delete_failure_with_replicas(self):
        """If the deletion of an original package doesn't succeed for
        some reason, we don't want to proceed to delete the replicas
        associated with that package. That should be done as an
        independent action by the user, otherwise they are paired
        activities.
        """

        # Package with two replicas in the storage service.
        package = models.Package.objects.get(
            uuid="f0dfdc4c-7ba1-4e3f-a972-f2c55d870d04"
        )

        # Store our original space and location values to test after
        # our "failed" delete call.
        original_location_used = package.current_location.used
        original_space_used = package.current_location.space.used

        # Using our context manager attempt to delete our package but
        # make sure the correct behavior occurs when an exception is
        # raised, e.g. NotImplementedError for a space without a storage
        # service managed deletion capability.
        with mock.patch(
            "locations.models.Space.delete_path", side_effect=NotImplementedError
        ) as mocked_delete:
            package.delete_from_storage()
            assert mocked_delete.called
            assert mocked_delete.call_count == 1

        # Ensure locations sizes are the same as they were because no
        # deletion happened.
        assert package.current_location.used == original_location_used
        assert package.current_location.space.used == original_space_used

        # Ensure that the replicas and the original package have not
        # seen their status updated.
        replicas = package._find_replicas()
        assert package.status == models.Package.UPLOADED
        assert replicas[0].status == models.Package.UPLOADED
        assert replicas[1].status == models.Package.UPLOADED

    def test_view_package_delete(self):
        self.client.login(username="test", password="test")
        url = reverse(
            "locations:package_delete", args=["00000000-0000-0000-0000-000000000000"]
        )

        # It does only accept POST, i.e. GET returns a 405
        response = self.client.get(url, follow=True)
        assert response.status_code == 405

        # It returns a 404 when the UUID is unknown
        response = self.client.post(url, follow=True)
        assert response.status_code == 404

        def verify_redirect_message(response, message):
            assert response.status_code == 200
            assert response.redirect_chain == [("/packages/", 302)]
            messages = list(get_messages(response.wsgi_request))
            assert len(messages) == 1
            assert str(messages[0]) == message

        # It returns an "error" message when the package type is not allowed.
        url = reverse("locations:package_delete", args=[self.package.uuid])
        response = self.client.post(url, follow=True)
        verify_redirect_message(
            response, "Package of type Transfer cannot be deleted directly"
        )

        # It returns a "success" message when the package was deleted
        # successfully and updates its status
        models.Package.objects.filter(uuid=self.package.uuid).update(
            package_type=models.Package.DIP
        )
        response = self.client.post(url, follow=True)
        verify_redirect_message(response, "Package deleted successfully!")
        assert (
            models.Package.objects.get(uuid=self.package.uuid).status
            == models.Package.DELETED
        )

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
        # This file's name was changed ("filename change"), so check to see if
        # the correct name is used.
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
        uuid = "473a9398-0024-4804-81da-38946040c8af"
        aip = models.Package.objects.get(uuid=uuid)
        with mock.patch("locations.models.Callback.execute") as mocked_execute:
            aip.run_post_store_callbacks()
            # Only `post_store_aip` callbacks are executed
            assert mocked_execute.call_count == 1
            # Placeholders replaced in URI and body
            url = "http://consumer.com/api/v1/aip/%s/" % uuid
            body = '{"name": "tar_gz_package", "uuid": "%s"}' % uuid
            mocked_execute.assert_called_with(url, body)

    def test_run_post_store_callbacks_aip_tricky_name(self):
        uuid = "708f7a1d-dda4-46c7-9b3e-99e188eeb04c"
        aip = models.Package.objects.get(uuid=uuid)
        with mock.patch("locations.models.Callback.execute") as mocked_execute:
            aip.run_post_store_callbacks()
            # Only `post_store_aip` callbacks are executed
            assert mocked_execute.call_count == 1
            # Placeholders replaced in URI and body
            url = "http://consumer.com/api/v1/aip/%s/" % uuid
            body = '{"name": "a.bz2.tricky.7z.package", "uuid": "%s"}' % uuid
            mocked_execute.assert_called_with(url, body)

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

    @staticmethod
    def _test_bagit_structure(replica, replication_dir):
        """Ensure that the contents of a bag are consistent with the
        contents that were created during testing so that we know
        structure is preserved accurately.
        """
        bag_contents = [
            "tagmanifest-md5.txt",
            "bagit.txt",
            "manifest-md5.txt",
            "bag-info.txt",
            os.path.join("data", "test.txt"),
        ]
        expected_bag_path = os.path.join(
            replication_dir, utils.uuid_to_path(replica.uuid), "working_bag"
        )
        expected_bagit_structure = [
            os.path.join(expected_bag_path, bag_path) for bag_path in bag_contents
        ]
        found_structure = []
        for subdir, _, files in os.walk(replica.current_location.full_path):
            for file_ in files:
                found_structure.append(os.path.join(subdir, file_))
        assert set(found_structure) == set(
            expected_bagit_structure
        ), "unexpected bag structure found:"

    def test_replicate_aip_when_file(self):
        """Ensure that a replica can be created and its resulting
        properties are consistent for one of Archivematica's file-like
        AIP package types, e.g. 7z.
        """
        space_dir = tempfile.mkdtemp(dir=self.tmp_dir, prefix="space")
        replication_dir = tempfile.mkdtemp(dir=self.tmp_dir, prefix="replication")
        aip = models.Package.objects.get(uuid="88deec53-c7dc-4828-865c-7356386e9399")
        aip.current_location.space.staging_path = space_dir
        aip.current_location.space.save()
        aip.current_location.replicators.create(
            space=aip.current_location.space,
            relative_path=replication_dir,
            purpose=models.Location.REPLICATOR,
        )
        assert aip.replicas.count() == 0
        aip.create_replicas()
        assert aip.replicas.count() == 1
        replica = aip.replicas.first()
        assert replica is not None
        assert replica.origin_pipeline == aip.origin_pipeline
        assert replica.replicas.count() == 0
        package_name = "working_bag.7z"
        dest_dir = os.path.join(replication_dir, utils.uuid_to_path(replica.uuid))
        repl_file_path = os.path.join(
            replication_dir, utils.uuid_to_path(replica.uuid), package_name
        )
        assert package_name in os.listdir(dest_dir)
        assert os.path.isfile(repl_file_path)

    def test_replicate_aip(self):
        """Ensure that a replica can be created and its resulting
        properties and folder structure are consistent for a regular,
        non-packed bag in Archivematica, e.g. Uncompressed and not 7z
        etc.
        """
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
        assert aip.replicas.count() == 0
        aip.create_replicas()
        assert aip.replicas.count() == 1
        replica = aip.replicas.first()
        assert replica is not None
        assert replica.origin_pipeline == aip.origin_pipeline
        assert replica.replicas.count() == 0
        self._test_bagit_structure(aip.replicas.first(), replication_dir)

    def test_replicate_aic(self):
        """Ensure that replication works for AICs as well as AIPs."""
        space_dir = tempfile.mkdtemp(dir=self.tmp_dir, prefix="space")
        replication_dir = tempfile.mkdtemp(dir=self.tmp_dir, prefix="replication")
        aic = models.Package.objects.get(uuid="4781e745-96bc-4b06-995c-ee59fddf856d")
        aic.current_location.space.staging_path = space_dir
        aic.current_location.space.save()
        aic.current_location.replicators.create(
            space=aic.current_location.space,
            relative_path=replication_dir,
            purpose=models.Location.REPLICATOR,
        )
        assert aic.replicas.count() == 0

        def create_temporary_pointer(path):
            """Create temporary copy of pointer file at path."""
            temp_path = os.path.join(self.tmp_dir, "temp_pointer.xml")
            shutil.copy2(path, temp_path)
            return temp_path

        pointer = create_temporary_pointer(
            os.path.join(
                FIXTURES_DIR, "pointer.4781e745-96bc-4b06-995c-ee59fddf856d.xml"
            )
        )
        with mock.patch.object(models.Package, "full_pointer_file_path", pointer):
            aic.create_replicas()
            assert aic.replicas.count() == 1
            replica = aic.replicas.first()
            assert replica is not None
            assert replica.origin_pipeline == aic.origin_pipeline
            assert replica.status == models.Package.UPLOADED
            assert replica.replicas.count() == 0

    def test_replicate_aip_twice(self):
        """Ensure that multiple replicas can be created and its
        resulting properties and folder structure are consistent for a
        regular, non-packed bag in Archivematica, e.g. Uncompressed and
        not 7z etc. Make sure the properties correctly indicate two
        replicas.
        """
        space_dir = tempfile.mkdtemp(dir=self.tmp_dir, prefix="space")
        replication_dir = tempfile.mkdtemp(dir=self.tmp_dir, prefix="replication")
        replication_dir2 = tempfile.mkdtemp(dir=self.tmp_dir, prefix="replication")
        aip = models.Package.objects.get(uuid="0d4e739b-bf60-4b87-bc20-67a379b28cea")
        aip.current_location.space.staging_path = space_dir
        aip.current_location.space.save()
        aip.current_location.replicators.create(
            space=aip.current_location.space,
            relative_path=replication_dir,
            purpose=models.Location.REPLICATOR,
        )
        aip.current_location.replicators.create(
            space=aip.current_location.space,
            relative_path=replication_dir2,
            purpose=models.Location.REPLICATOR,
        )

        assert aip.replicas.count() == 0

        aip.create_replicas()

        assert aip.replicas.count() == 2
        assert aip.replicas.first() != aip.replicas.last()

        assert aip.replicas.first().replicas.count() == 0
        assert aip.replicas.last().replicas.count() == 0

        self._test_bagit_structure(aip.replicas.first(), replication_dir)
        self._test_bagit_structure(aip.replicas.last(), replication_dir2)

    @mock.patch("locations.models.gpg._gpg_encrypt")
    def test_replicate_aip_gpg_encrypted(self, mock_encrypt):
        """Ensure that a replica is created correctly for a replication
        space created with a GPG encryption and ensure that the calls
        made to correct it look correct and the replica's properties are
        consistent.
        """
        mock_encrypt.return_value = ("/a/fake/path", mock.Mock())

        space_dir = tempfile.mkdtemp(dir=self.tmp_dir, prefix="space")
        replication_dir = tempfile.mkdtemp(dir=self.tmp_dir, prefix="replication")
        gpg_dir = tempfile.mkdtemp(dir=self.tmp_dir, prefix="gpg")
        gpg_space = models.Space.objects.create(
            access_protocol=models.Space.GPG, path="/", staging_path=gpg_dir
        )
        models.GPG.objects.create(space=gpg_space)

        aip = models.Package.objects.get(uuid="0d4e739b-bf60-4b87-bc20-67a379b28cea")
        aip.current_location.space.staging_path = space_dir
        aip.current_location.space.save()

        aip.current_location.replicators.create(
            space=gpg_space,
            relative_path=replication_dir,
            purpose=models.Location.REPLICATOR,
        )

        assert aip.replicas.count() == 0
        aip.create_replicas()
        replica = aip.replicas.first()

        assert aip.replicas.count() == 1
        assert replica is not None
        assert mock_encrypt.call_args_list == [
            mock.call(os.path.join(replica.full_path, ""), "")
        ]
        self._test_bagit_structure(replica, replication_dir)

    def test_replicate_aip_offline_staging_uncompressed(self):
        """Ensure that a replica is created and stored correctly as a tarball."""
        space_dir = tempfile.mkdtemp(dir=self.tmp_dir, prefix="space")
        replication_dir = tempfile.mkdtemp(dir=self.tmp_dir, prefix="replication")
        staging_dir = tempfile.mkdtemp(dir=self.tmp_dir, prefix="offline")
        replica_space = models.Space.objects.create(
            access_protocol=models.Space.OFFLINE_REPLICA_STAGING,
            path="/",
            staging_path=staging_dir,
        )
        models.OfflineReplicaStaging.objects.create(space=replica_space)

        aip = models.Package.objects.get(uuid="0d4e739b-bf60-4b87-bc20-67a379b28cea")
        aip.current_location.space.staging_path = space_dir
        aip.current_location.space.save()

        staging_files_count_initial = recursive_file_count(staging_dir)
        staging_dirs_count_initial = recursive_dir_count(staging_dir)

        aip.current_location.replicators.create(
            space=replica_space,
            relative_path=replication_dir,
            purpose=models.Location.REPLICATOR,
        )

        assert aip.replicas.count() == 0

        aip.create_replicas()
        replica = aip.replicas.first()

        assert aip.replicas.count() == 1
        assert replica is not None
        expected_replica_path = os.path.join(replication_dir, "working_bag.tar")
        assert os.path.exists(expected_replica_path)
        assert replica.current_path == expected_replica_path

        assert staging_files_count_initial == recursive_file_count(staging_dir)
        assert staging_dirs_count_initial == recursive_dir_count(staging_dir)

    def test_replicate_aip_offline_staging_compressed(self):
        """Ensure that a replica is created and stored correctly as-is."""
        space_dir = tempfile.mkdtemp(dir=self.tmp_dir, prefix="space")
        replication_dir = tempfile.mkdtemp(dir=self.tmp_dir, prefix="replication")
        staging_dir = tempfile.mkdtemp(dir=self.tmp_dir, prefix="offline")
        replica_space = models.Space.objects.create(
            access_protocol=models.Space.OFFLINE_REPLICA_STAGING,
            path="/",
            staging_path=staging_dir,
        )
        models.OfflineReplicaStaging.objects.create(space=replica_space)

        aip = models.Package.objects.get(uuid="88deec53-c7dc-4828-865c-7356386e9399")
        aip.current_location.space.staging_path = space_dir
        aip.current_location.space.save()

        staging_files_count_initial = recursive_file_count(staging_dir)
        staging_dirs_count_initial = recursive_dir_count(staging_dir)

        aip.current_location.replicators.create(
            space=replica_space,
            relative_path=replication_dir,
            purpose=models.Location.REPLICATOR,
        )

        assert aip.replicas.count() == 0

        aip.create_replicas()
        replica = aip.replicas.first()

        assert aip.replicas.count() == 1
        assert replica is not None
        expected_replica_path = os.path.join(replication_dir, "working_bag.7z")
        assert os.path.exists(expected_replica_path)
        assert replica.current_path == expected_replica_path

        assert staging_files_count_initial == recursive_file_count(staging_dir)
        assert staging_dirs_count_initial == recursive_dir_count(staging_dir)

    def test_deletion_and_creation_of_replicas_compressed(self):
        """Ensure that when it is requested a replica be created, then
        existing replicas are checked for and deleted if necessary, e.g.
        during a reingest process. Ensure that a new replica is created
        in its place which reflects the original's updated structure.
        """
        AIP_UUID = "f0dfdc4c-7ba1-4e3f-a972-f2c55d870d04"
        OLD_REPLICAS = [
            "2f62b030-c3f4-4ac1-950f-fe47d0ddcd14",
            "577f74bd-a283-49e0-b4e2-f8abb81d2566",
        ]

        space_dir = tempfile.mkdtemp(dir=self.tmp_dir, prefix="space")
        replication_dir = tempfile.mkdtemp(dir=self.tmp_dir, prefix="replication")
        aip = models.Package.objects.get(uuid=AIP_UUID)
        aip.current_location.space.staging_path = space_dir
        aip.current_location.space.save()
        aip.current_location.replicators.create(
            space=aip.current_location.space,
            relative_path=replication_dir,
            purpose=models.Location.REPLICATOR,
        )

        # Previous replicas for this package should be 2. Ensure that
        # is correct and ensure that status for both is UPLOADED.
        previous_replicas = models.Package.objects.filter(
            replicated_package=AIP_UUID
        ).all()
        uploaded_repl = [
            repl for repl in previous_replicas if repl.status == models.Package.UPLOADED
        ]
        assert (
            len(set(uploaded_repl)) == len(set(previous_replicas)) == len(OLD_REPLICAS)
        )

        with mock.patch("locations.models.Space.move_rsync") as _:
            aip.create_replicas()

        # The replication process in the storage service will create
        # only as many new replicas as there are enabled locations so
        # in this scenario we will see two existing replicas deleted
        # and one new replica created.
        all_replicas = models.Package.objects.filter(replicated_package=AIP_UUID).all()
        uploaded_repl = [
            repl for repl in all_replicas if repl.status == models.Package.UPLOADED
        ]
        deleted_repl = [
            repl for repl in all_replicas if repl.status == models.Package.DELETED
        ]

        # Make sure our counts are correct, 3 total, 2 deleted, 1 new
        # (uploaded).
        assert len(set(all_replicas)) == 3
        assert len(set(deleted_repl)) == len(OLD_REPLICAS)
        assert len(uploaded_repl) == 1

        # Make sure the previous replicas we expected to be deleted were
        # marked as deleted.
        deleted_uuids = []
        for package in deleted_repl:
            deleted_uuids.append(package.uuid)
        assert set(deleted_uuids) == set(OLD_REPLICAS)

        # Finally make sure the database has given us a new UUID for the
        # new replica.
        assert uploaded_repl[0].uuid not in OLD_REPLICAS

    @staticmethod
    def _create_mutable_fixture_for_replication(package_name, files):
        """Create a mutable fixture to test replication updates
        file-level structures correctly during its replication routines
        and perform other more sophisticated testing.

        :param package_name: Name of the package directory.
        :param files: A list of files to write into the package
            directory.
        :return: Location of what would be the AIPstore for storage
            service functions to find any packages we create here.
        """
        DATA_TO_WRITE = "data"
        tmp_dir = tempfile.mkdtemp()
        aip_dir = os.path.join(tmp_dir, package_name)
        os.mkdir(aip_dir)
        for f in files:
            with open(os.path.join(aip_dir, f), "w") as test_file:
                test_file.write(DATA_TO_WRITE)
        return tmp_dir

    def test_deletion_and_creation_of_replicas_uncompressed(self):
        """Ensure that an uncompressed package is created properly.
        Because replication seeks to also update the package we try
        adding new files, e.g. it could be through enabling
        normalization during partial-reingest. Through these tests we
        also verify some properties about those files which support the
        storage service's preservation functions.
        """
        PACKAGE = "working_bag"
        FILES = ["file_one", "file_two", "file_three"]
        AIP_LOC = "615103f0-0ee0-4a12-ba17-43192d1143ea"

        new_aip_store = self._create_mutable_fixture_for_replication(PACKAGE, FILES)
        self._point_location_at_on_disk_storage(AIP_LOC, new_aip_store)

        original_dir = os.path.join(new_aip_store, PACKAGE)

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

        # Make sure there is no existing date polluting the tests.
        assert aip.replicas.count() == 0

        # Create the replica and assert some properties about it and
        # the original AIP's relationships.
        aip.create_replicas()
        assert aip.replicas.count() == 1
        replica = aip.replicas.first()
        assert replica is not None
        assert replica.origin_pipeline == aip.origin_pipeline
        assert replica.replicas.count() == 0

        # Ensure that our first replication was created as expected.
        first_repl_uuid = replica.uuid
        first_expected_repl = os.path.join(
            replication_dir, utils.uuid_to_path(first_repl_uuid), PACKAGE
        )
        assert set(os.listdir(first_expected_repl)) == set(FILES)
        assert replica.status == models.Package.UPLOADED

        # Add some new data to our original package and create some
        # properties that we can then measure.
        FILE_TO_ADD = "new_normalization"
        DATA_TO_ADD = "new data"
        new_file = os.path.join(original_dir, FILE_TO_ADD)
        with open(new_file, "w") as normalize_example:
            normalize_example.write(DATA_TO_ADD)
        # Because we have a mutable store to play with, we can have
        # some more fun, so lets test preservation of dates during
        # replication.
        TEST_DATETIME = datetime.datetime(
            year=1970, month=1, day=1, hour=22, minute=13, second=0
        )
        DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"
        DATE_STRING = "1970-01-01T22:13:00"
        mod_time = time.mktime(TEST_DATETIME.timetuple())
        os.utime(new_file, (mod_time, mod_time))

        # Create the replica and ensure the first one no-longer exists.
        aip.create_replicas()
        assert not os.path.isdir(first_expected_repl)

        # We're only creating a second version of a replica so last() is
        # available as a shortcut to get to it.
        replica = aip.replicas.last()
        second_repl_uuid = replica.uuid
        second_expected_repl = os.path.join(
            replication_dir, utils.uuid_to_path(second_repl_uuid), PACKAGE
        )

        # Ensure the replicated directory structure is what we expect.
        assert set(os.listdir(second_expected_repl)) == set(FILES + [FILE_TO_ADD])

        # Make sure the replicated statuses are correct.
        assert aip.replicas.first().status == models.Package.DELETED
        assert aip.replicas.last().status == models.Package.UPLOADED

        new_replicated_file = os.path.join(second_expected_repl, FILE_TO_ADD)
        repl_file_timestamp = os.path.getmtime(new_replicated_file)

        # Ensure the timestamp is preserved.
        pretty_timestamp = datetime.datetime.fromtimestamp(
            repl_file_timestamp
        ).strftime(DATE_FORMAT)
        assert pretty_timestamp == TEST_DATETIME.strftime(DATE_FORMAT)
        assert pretty_timestamp == DATE_STRING

        # Ensure data was copied as expected.
        assert os.path.getsize(new_replicated_file) == len(DATA_TO_ADD)

    def test_clear_local_tempdirs(self):
        """Ensure package's local tempdirs are deleted.

        Tempdirs associated with other packages should be retained.
        """
        ss_internal = models.Location.active.get(
            purpose=models.Location.STORAGE_SERVICE_INTERNAL
        )
        space_dir = tempfile.mkdtemp(dir=self.tmp_dir, prefix="space")
        ss_internal_dir = tempfile.mkdtemp(dir=space_dir, prefix="int")
        ss_internal.space.path = space_dir
        ss_internal.relative_path = os.path.basename(ss_internal_dir)

        aip1 = models.Package.objects.get(uuid="0d4e739b-bf60-4b87-bc20-67a379b28cea")
        aip2 = models.Package.objects.get(uuid="6aebdb24-1b6b-41ab-b4a3-df9a73726a34")

        def mock_fetch_local_path(package):
            tempdir = tempfile.mkdtemp(dir=ss_internal.full_path)
            package.local_tempdirs.append(tempdir)
            return tempdir

        # Create temporary directories.
        tempdir_to_delete = mock_fetch_local_path(aip1)
        tempdir_to_retain = mock_fetch_local_path(aip2)
        assert os.path.exists(tempdir_to_delete)
        assert os.path.exists(tempdir_to_retain)
        assert (
            len(aip1.local_tempdirs) == 1
            and aip1.local_tempdirs[0] == tempdir_to_delete
        )
        assert (
            len(aip2.local_tempdirs) == 1
            and aip2.local_tempdirs[0] == tempdir_to_retain
        )

        # Remove temporary directories for first AIP.
        with mock.patch(
            "locations.models.package._get_ss_internal_full_path",
            return_value=ss_internal.full_path,
        ):
            aip1.clear_local_tempdirs()
        assert not os.path.exists(tempdir_to_delete)
        assert os.path.exists(tempdir_to_retain)
        assert len(aip1.local_tempdirs) == 0
        assert (
            len(aip2.local_tempdirs) == 1
            and aip2.local_tempdirs[0] == tempdir_to_retain
        )


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
