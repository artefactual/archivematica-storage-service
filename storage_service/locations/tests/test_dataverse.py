# -*- coding: utf-8 -*-
from django.test import TestCase
import os
import vcr

from locations import models

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
FIXTURES_DIR = os.path.abspath(os.path.join(THIS_DIR, '..', 'fixtures'))

class TestDataverse(TestCase):

    fixtures = ['base.json', 'dataverse.json']

    def setUp(self):
        self.dataverse = models.Dataverse.objects.all()[0]
        self.dataverse_location = models.Location.objects.get(space=self.dataverse.space)

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
        assert resp['entries'][0] == 'Ad hoc observational study of the trees outside my window'
        assert resp['entries'][1] == 'Constitive leaf ORAC'
        assert resp['entries'][14] == 'testjpg'
        assert len(resp['properties']) == 0

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
        assert resp['entries'][0] == 'Metadata mapping test study'
        assert resp['entries'][1] == 'Restricted Studies Test'
        assert resp['entries'][2] == 'testdocx'
        assert resp['entries'][3] == 'testjpg'
        assert len(resp['properties']) == 0
