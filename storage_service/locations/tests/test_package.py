import os

from django.test import TestCase

from locations import models


class TestPackage(TestCase):

    fixtures = ['base.json', 'package.json']

    def setUp(self):
        self.package = models.Package.objects.all()[0]
        self.mets_path = os.path.normpath(os.path.join(__file__, "..", "..", "fixtures"))

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
