# -*- coding: utf-8 -*-
from django.test import TestCase
import os
import shutil
import vcr

from locations import models

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
FIXTURES_DIR = os.path.abspath(os.path.join(THIS_DIR, '..', 'fixtures'))


class TestDataverse(TestCase):

    fixtures = ['base.json', 'dataverse.json', 'dataverse2.json']

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

    @vcr.use_cassette(os.path.join(FIXTURES_DIR, 'vcr_cassettes',
                      'dataverse_browse_filter.yaml'))
    def test_browse_datasets(self):
        """
        It should fetch a list of datasets.
        It should fetch a list of objects within a dataset.
        """
        dataverse = models.Dataverse.objects.get(
            agent_name='Archivematica Test Dataverse')
        location = dataverse.space.location_set.get(purpose='TS')

        # Get all datasets in a location
        resp = dataverse.browse(location.relative_path)
        assert len(resp['directories']) == 59
        assert len(resp['entries']) == 59
        assert resp['entries'] == resp['directories']
        assert resp['entries'][0] == '1016'
        assert resp['entries'][1] == '574'
        assert resp['entries'][2] == '577'
        assert resp['entries'][3] == '581'
        assert len(resp['properties']) == 59
        assert resp['properties']['1016']['verbose name'] == (
            '3D Laser Images of a road cut at Ivy Lea, Ontario (2007),'
            ' underground in Sudbury, Ontario (2007), underground in Thompson,'
            ' Manitoba (2009) [test]')
        assert resp['properties']['574']['verbose name'] == (
            'A study of my afternoon drinks ')
        assert resp['properties']['577']['verbose name'] == (
            'A study with restricted data')
        assert resp['properties']['581']['verbose name'] == (
            'A sub-dataverse dataset')

        # Get all objects in dataset 1016
        resp = dataverse.browse('{}/1016'.format(location.relative_path))
        assert resp['directories'] == []
        assert len(resp['entries']) == 55
        first4 = ['IvyLea_003.txt', 'IvyLea_004.txt', 'IvyLea_005.txt',
                  'IvyLea_006.txt']
        first4sizes = [47448936, 46736074, 47463997, 47723143]
        assert first4 == resp['entries'][:4]
        for idx, obj in enumerate(first4):
            assert resp['properties'][obj]['size'] == first4sizes[idx]

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
