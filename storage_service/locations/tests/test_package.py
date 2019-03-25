# -*- coding: utf-8 -*-

import os
import pytest
import shutil
import tempfile
import vcr

import mock

from django.contrib.messages import get_messages
from django.core.urlresolvers import reverse
from django.test import TestCase

from common.compression_management import PackageExtractException
from locations import models

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
FIXTURES_DIR = os.path.abspath(os.path.join(THIS_DIR, '..', 'fixtures', ''))


class TestPackage(TestCase):

    fixtures = ['base.json', 'package.json', 'arkivum.json']

    def setUp(self):
        self.package = models.Package.objects.all()[0]
        self.mets_path = os.path.normpath(os.path.join(__file__, "..", "..", "fixtures"))
        self.test_location = models.Location.objects.get(uuid='615103f0-0ee0-4a12-ba17-43192d1143ea')
        # Set up locations to point to fixtures directory
        self.test_location.relative_path = FIXTURES_DIR[1:]
        self.test_location.save()
        # SS int points at fixtures directory
        models.Location.objects.filter(purpose='SS').update(relative_path=FIXTURES_DIR[1:])
        # Arkivum space points at fixtures directory
        models.Space.objects.filter(uuid='6fb34c82-4222-425e-b0ea-30acfd31f52e').update(path=FIXTURES_DIR)
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def test_view_package_delete(self):
        self.client.login(username="test", password="test")
        url = reverse(
            'package_delete', args=["00000000-0000-0000-0000-000000000000"])

        # It does only accept POST, i.e. GET returns a 405
        response = self.client.get(url, follow=True)
        assert response.status_code == 405

        # It returns a 404 when the UUID is unknown
        response = self.client.post(url, follow=True)
        assert response.status_code == 404

        def verify_redirect_message(response, message):
            assert response.status_code == 200
            assert response.redirect_chain == [
                ('http://testserver/packages/', 302)]
            messages = list(get_messages(response.wsgi_request))
            assert len(messages) == 1
            assert str(messages[0]) == message

        # It returns an "error" message when the package type is not allowed.
        url = reverse(
            'package_delete', args=[self.package.uuid])
        response = self.client.post(url, follow=True)
        verify_redirect_message(
            response, "Package of type Transfer cannot be deleted directly")

        # It returns a "success" message when the package was deleted
        # successfully.
        models.Package.objects.filter(
            uuid=self.package.uuid).update(package_type=models.Package.DIP)
        response = self.client.post(url, follow=True)
        verify_redirect_message(response, "Package deleted successfully!")

        # It returns an "error" message when the package could not be deleted
        # and the underlying code raised an exception.
        with mock.patch('locations.models.Package.delete_from_storage',
                        side_effect=ValueError):
            response = self.client.post(url, follow=True)
            verify_redirect_message(
                response, "Package deletion failed. Please contact an"
                          " administrator or see logs for details.")

        # It returns an "error" message when the package could not be deleted.
        with mock.patch('locations.models.Package.delete_from_storage',
                        return_value=(False, "Something went wrong")):
            response = self.client.post(url, follow=True)
            verify_redirect_message(
                response, "Package deletion failed. Please contact an"
                          " administrator or see logs for details.")

    def test_parsing_mets_data(self):
        mets_data = self.package._parse_mets(prefix=self.mets_path)
        assert mets_data['transfer_uuid'] == 'de1b31fa-97dd-48e0-8417-03be78359531'
        assert mets_data['dashboard_uuid'] == '23879cf0-a21a-40ee-bc50-357186746d15'
        assert mets_data['creation_date'] == '2015-02-21T01:55:08'
        assert len(mets_data['files']) == 11
        # This file's name was sanitized, so check to see if the correct name is used
        assert mets_data['files'][9]['file_uuid'] == '742f10b0-768a-4158-b255-94847a97c465'
        assert mets_data['files'][9]['path'] == 'images-transfer-de1b31fa-97dd-48e0-8417-03be78359531/objects/pictures/Landing_zone.jpg'

    def test_files_are_added_to_database(self):
        self.package.index_file_data_from_transfer_mets(prefix=self.mets_path)
        assert self.package.file_set.count() == 12  # 11 from this METS, plus the one the fixture is already assigned
        assert self.package.file_set.get(name='images-transfer-de1b31fa-97dd-48e0-8417-03be78359531/objects/pictures/Landing_zone.jpg').source_id == '742f10b0-768a-4158-b255-94847a97c465'

    def test_fixity_success(self):
        """
        It should return success.
        It should return no errors.
        It should have an empty message.
        """
        package = models.Package.objects.get(uuid='0d4e739b-bf60-4b87-bc20-67a379b28cea')
        success, failures, message, timestamp = package.check_fixity()
        assert success is True
        assert failures == []
        assert message == ''
        assert timestamp is None

    def test_fixity_failure(self):
        """
        It should return error.
        It should return a list of errors.
        It should have an error message.
        """
        package = models.Package.objects.get(uuid='9f260047-a9b7-4a75-bb6a-e8d94c83edd2')
        success, failures, message, timestamp = package.check_fixity()
        assert success is False
        # Failures are: missing file (dne.txt), bad checksum (dne.txt, test.txt, manifest-md5.txt)
        assert len(failures) == 4
        assert message == 'invalid bag'
        assert timestamp is None

    def test_fixity_package_type(self):
        """ It should only fixity bags. """
        package = models.Package.objects.get(uuid='79245866-ca80-4f84-b904-a02b3e0ab621')
        success, failures, message, timestamp = package.check_fixity()
        assert success is None
        assert failures == []
        assert 'package is not a bag' in message
        assert timestamp is None

    @vcr.use_cassette(os.path.join(FIXTURES_DIR, 'vcr_cassettes', 'package_fixity_scheduled_arkivum.yaml'))
    def test_fixity_scheduled_arkivum(self):
        """ It should return success of None. """
        package = models.Package.objects.get(uuid='e52c518d-fcf4-46cc-8581-bbc01aff7af3')
        package.misc_attributes.update({'arkivum_identifier': '5afe9428-c6d6-4d0f-9196-5e7fd028726d'})
        package.save()
        success, failures, message, timestamp = package.check_fixity(force_local=False)
        assert success is None
        assert message == 'Arkivum fixity check in progress'
        assert failures == []
        assert timestamp is None

    @vcr.use_cassette(os.path.join(FIXTURES_DIR, 'vcr_cassettes', 'package_fixity_amber_arkivum.yaml'))
    def test_fixity_amber_arkivum(self):
        """ It should return success of None. """
        package = models.Package.objects.get(uuid='e52c518d-fcf4-46cc-8581-bbc01aff7af3')
        package.misc_attributes.update({'arkivum_identifier': '5afe9428-c6d6-4d0f-9196-5e7fd028726d'})
        package.save()
        success, failures, message, timestamp = package.check_fixity(force_local=False)
        assert success is None
        assert message == 'Arkivum fixity check in progress'
        assert failures == []
        assert timestamp == '2015-11-24T00:00:00'

    @vcr.use_cassette(os.path.join(FIXTURES_DIR, 'vcr_cassettes', 'package_fixity_success_arkivum.yaml'))
    def test_fixity_success_arkivum(self):
        """ It should return Arkivum's successful fixity not generate its own. """
        package = models.Package.objects.get(uuid='e52c518d-fcf4-46cc-8581-bbc01aff7af3')
        package.misc_attributes.update({'arkivum_identifier': '5afe9428-c6d6-4d0f-9196-5e7fd028726d'})
        package.save()
        success, failures, message, timestamp = package.check_fixity(force_local=False)
        assert success is True
        assert message == ''
        assert failures == []
        assert timestamp == '2015-11-24T00:00:00'

    @vcr.use_cassette(os.path.join(FIXTURES_DIR, 'vcr_cassettes', 'package_fixity_failure_arkivum.yaml'))
    def test_fixity_failure_arkivum(self):
        """ It should return success of False from Arkivum. """
        package = models.Package.objects.get(uuid='e52c518d-fcf4-46cc-8581-bbc01aff7af3')
        package.misc_attributes.update({'arkivum_identifier': '5afe9428-c6d6-4d0f-9196-5e7fd028726d'})
        package.save()
        success, failures, message, timestamp = package.check_fixity(force_local=False)
        assert success is False
        assert message == 'invalid bag'
        assert len(failures) == 2
        assert {"filepath": "data/test/test1.txt", "reason": "Initial verification failed"} in failures
        assert {"reason": "Initial verification failed", "filepath": "manifest-md5.txt"} in failures
        assert timestamp is None

    def test_fixity_force_local(self):
        """ It should do checksum locally if required. """
        package = models.Package.objects.get(uuid='e52c518d-fcf4-46cc-8581-bbc01aff7af3')
        success, failures, message, timestamp = package.check_fixity(force_local=True)
        assert success is True
        assert failures == []
        assert message == ''
        assert timestamp is None

    def test_extract_file_aip_from_uncompressed_aip(self):
        """ It should return an aip """
        package = models.Package.objects.get(uuid='0d4e739b-bf60-4b87-bc20-67a379b28cea')
        basedir = package.get_base_directory()
        output_path, extract_path = package.extract_file(extract_path=self.tmp_dir)
        assert output_path == os.path.join(self.tmp_dir, basedir)
        assert os.path.join(output_path, 'manifest-md5.txt')

    def test_extract_file_file_from_uncompressed_aip(self):
        """ It should return a single file from an uncompressed aip """
        package = models.Package.objects.get(uuid='0d4e739b-bf60-4b87-bc20-67a379b28cea')
        basedir = package.get_base_directory()
        output_path, extract_path = package.extract_file(relative_path='working_bag/manifest-md5.txt', extract_path=self.tmp_dir)
        assert output_path == os.path.join(self.tmp_dir, basedir, 'manifest-md5.txt')
        assert os.path.isfile(output_path)

    def test_extract_file_file_from_compressed_aip(self):
        """ It should return a single file from a 7zip compressed aip """
        package = models.Package.objects.get(uuid='88deec53-c7dc-4828-865c-7356386e9399')
        basedir = package.get_base_directory()
        output_path, extract_path = package.extract_file(relative_path='working_bag/manifest-md5.txt', extract_path=self.tmp_dir)
        assert output_path == os.path.join(extract_path, basedir, 'manifest-md5.txt')
        assert os.path.isfile(output_path)

    def test_extract_file_file_does_not_exist_compressed(self):
        """ It should raise an error because the requested file does not exist"""
        package = models.Package.objects.get(uuid='88deec53-c7dc-4828-865c-7356386e9399')
        file_manifest_doesnt_exist = 'working_bag/manifest-sha512.txt'
        try:
            output_path, extract_path = package.extract_file(relative_path=file_manifest_doesnt_exist, extract_path=self.tmp_dir)
        except PackageExtractException as err:
            assert "Extraction error: no files extracted" in err

    def test_extract_file_aip_from_compressed_aip(self):
        """ It should return an aip """
        package = models.Package.objects.get(uuid='88deec53-c7dc-4828-865c-7356386e9399')
        basedir = package.get_base_directory()
        output_path, extract_path = package.extract_file(extract_path=self.tmp_dir)
        assert output_path == os.path.join(self.tmp_dir, basedir)
        assert os.path.join(output_path, 'manifest-md5.txt')
