import os
import re
import vcr

from django.test import TestCase

from locations import models

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
FIXTURES_DIR = os.path.abspath(os.path.join(THIS_DIR, '..', 'fixtures', ''))
DATETIME_TZ_REGEX = r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}.\d{6}\+\d{2}:\d{2}'

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
        assert re.match(DATETIME_TZ_REGEX, timestamp)

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
        assert re.match(DATETIME_TZ_REGEX, timestamp)

    def test_fixity_package_type(self):
        """ It should only fixity bags. """
        package = models.Package.objects.get(uuid='79245866-ca80-4f84-b904-a02b3e0ab621')
        success, failures, message, timestamp = package.check_fixity()
        assert success is None
        assert failures == []
        assert 'package is not a bag' in message
        assert timestamp is None

    @vcr.use_cassette(os.path.join(FIXTURES_DIR, 'vcr_cassettes', 'package_fixity_use_arkivum.yaml'))
    def test_fixity_use_arkivum(self):
        """ It should return Arkivum's fixity not generate its own. """
        package = models.Package.objects.get(uuid='e52c518d-fcf4-46cc-8581-bbc01aff7af3')
        package.misc_attributes.update({'arkivum_identifier': '5afe9428-c6d6-4d0f-9196-5e7fd028726d'})
        package.save()
        success, failures, message, timestamp = package.check_fixity(ignore_space=False)
        assert success is False
        assert message == 'Fixity check scheduled in Arkivum'
        assert failures == []
        assert timestamp is None

    @vcr.use_cassette(os.path.join(FIXTURES_DIR, 'vcr_cassettes', 'package_fixity_success_arkivum.yaml'))
    def test_fixity_success_arkivum(self):
        """ It should return Arkivum's fixity not generate its own. """
        package = models.Package.objects.get(uuid='e52c518d-fcf4-46cc-8581-bbc01aff7af3')
        package.misc_attributes.update({'arkivum_identifier': '5afe9428-c6d6-4d0f-9196-5e7fd028726d'})
        package.save()
        success, failures, message, timestamp = package.check_fixity(ignore_space=False)
        assert success is True
        assert message == ''
        assert failures == []
        assert timestamp == '2015-11-24'

    def test_fixity_ignore_space(self):
        """ It should do checksum locally if required. """
        package = models.Package.objects.get(uuid='e52c518d-fcf4-46cc-8581-bbc01aff7af3')
        success, failures, message, timestamp = package.check_fixity(ignore_space=True)
        assert success is True
        assert failures == []
        assert message == ''
        assert re.match(DATETIME_TZ_REGEX, timestamp)
