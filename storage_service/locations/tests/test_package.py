import os

from django.test import TestCase

from locations import models

THIS_DIR = os.path.dirname(os.path.abspath(__file__))

class TestPackage(TestCase):

    fixtures = ['base.json', 'package.json']

    def setUp(self):
        self.package = models.Package.objects.all()[0]
        self.mets_path = os.path.normpath(os.path.join(__file__, "..", "..", "fixtures"))
        self.test_location = models.Location.objects.get(uuid='615103f0-0ee0-4a12-ba17-43192d1143ea')
        # Set up locations to point to fixtures directory
        fixtures_dir = os.path.abspath(os.path.join(THIS_DIR, '..', 'fixtures', ''))
        self.test_location.relative_path = fixtures_dir[1:]
        self.test_location.save()
        ss_int = models.Location.objects.get(purpose='SS')
        ss_int.relative_path = fixtures_dir[1:]
        ss_int.save()

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
        success, failures, message = package.check_fixity()
        assert success is True
        assert failures == []
        assert message == ''

    def test_fixity_failure(self):
        """
        It should return error.
        It should return a list of errors.
        It should have an error message.
        """
        package = models.Package.objects.get(uuid='9f260047-a9b7-4a75-bb6a-e8d94c83edd2')
        success, failures, message = package.check_fixity()
        assert success is False
        # Failures are: missing file (dne.txt), bad checksum (dne.txt, test.txt, manifest-md5.txt)
        assert len(failures) == 4
        assert message

    def test_fixity_package_type(self):
        """ It should only fixity bags. """
        package = models.Package.objects.get(uuid='79245866-ca80-4f84-b904-a02b3e0ab621')
        success, failures, message = package.check_fixity()
        assert success is None
        assert failures == []
        assert 'package is not a bag' in message

