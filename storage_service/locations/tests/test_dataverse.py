# -*- coding: utf-8 -*-
from django.test import TestCase
import os
import shutil
import vcr

from locations import models

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
FIXTURES_DIR = os.path.abspath(os.path.join(THIS_DIR, '..', 'fixtures'))


class TestDataverse(TestCase):

    fixtures = ['base.json', 'dataverse.json']

    def setUp(self):
        self.dataverse = models.Dataverse.objects.all()[0]
        self.dataverse_location = models.Location.objects.get(space=self.dataverse.space)

        self.space = models.Space.objects.get(access_protocol='FS')
        self.space.staging_path = os.path.join(FIXTURES_DIR)  # Make staging path the fixtures dir
        self.dest_path = os.path.join(self.space.staging_path, 'dataverse/')

    def tearDown(self):
        try:
            shutil.rmtree(self.dest_path)
        except Exception:
            pass

    def test_has_required_attributes(self):
        assert self.dataverse.host
        assert self.dataverse.api_key

    @vcr.use_cassette(os.path.join(FIXTURES_DIR, 'vcr_cassettes', 'dataverse_browse_all.yaml'))
    def test_browse_all(self):
        """
        It should fetch a list of datasets.
        It should handle iteration.
        """
        resp = self.dataverse.browse('*')
        assert len(resp['directories']) == 15
        assert len(resp['entries']) == 15
        assert resp['entries'] == resp['directories']
        assert resp['entries'][0] == '82'
        assert resp['entries'][1] == '25'
        assert resp['entries'][14] == '14'
        assert len(resp['properties']) == 15
        assert resp['properties']['82']['verbose name'] == 'Ad hoc observational study of the trees outside my window'
        assert resp['properties']['25']['verbose name'] == 'Constitive leaf ORAC'
        assert resp['properties']['14']['verbose name'] == 'testjpg'

    @vcr.use_cassette(os.path.join(FIXTURES_DIR, 'vcr_cassettes', 'dataverse_browse_filter.yaml'))
    def test_browse_filter(self):
        """
        It should fetch a list of datasets.
        It should filter based on the provided query
        """
        resp = self.dataverse.browse('title:test*')
        assert len(resp['directories']) == 4
        assert len(resp['entries']) == 4
        assert resp['entries'] == resp['directories']
        assert resp['entries'][0] == '90'
        assert resp['entries'][1] == '93'
        assert resp['entries'][2] == '16'
        assert resp['entries'][3] == '14'
        assert len(resp['properties']) == 4
        assert resp['properties']['90']['verbose name'] == 'Metadata mapping test study'
        assert resp['properties']['93']['verbose name'] == 'Restricted Studies Test'
        assert resp['properties']['16']['verbose name'] == 'testdocx'
        assert resp['properties']['14']['verbose name'] == 'testjpg'

    @vcr.use_cassette(os.path.join(FIXTURES_DIR, 'vcr_cassettes', 'dataverse_move_to.yaml'))
    def test_move_to(self):
        """
        It should fetch the files listed in the dataset.
        It should fetch the bundle for tha dataset.
        """
        assert os.path.exists(self.dest_path) is False
        self.dataverse.space.move_to_storage_service('90', 'dataverse/', self.space)
        assert 'chelan 052.jpg' in os.listdir(self.dest_path)
        assert 'Weather_data.zip' in os.listdir(self.dest_path)
        assert 'metadata' in os.listdir(self.dest_path)
        assert 'agents.json' in os.listdir(os.path.join(self.dest_path, 'metadata'))
        assert 'dataset.json' in os.listdir(os.path.join(self.dest_path, 'metadata'))
