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

    def test_has_required_attributes(self):
        assert self.dataverse.host
        assert self.dataverse.api_key
