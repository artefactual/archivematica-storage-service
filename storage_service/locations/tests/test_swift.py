# -*- coding: utf-8 -*-
import os
import shutil

from django.test import TestCase
import vcr

from locations import models


class TestSwift(TestCase):

    fixtures = ['base.json', 'swift.json']

    def setUp(self):
        self.swift_object = models.Swift.objects.all()[0]

    def test_has_required_attributes(self):
        assert self.swift_object.auth_url
        assert self.swift_object.auth_version
        assert self.swift_object.username
        assert self.swift_object.password
        assert self.swift_object.container
        if self.swift_object.auth_version in ("2", "2.0", 2):
            assert self.swift_object.tenant

    @vcr.use_cassette('locations/fixtures/vcr_cassettes/swift_browse.yaml')
    def test_browse(self):
        resp = self.swift_object.browse('transfers/SampleTransfers')
        assert resp
        assert resp['directories'] == ['badNames', 'Images']
        assert resp['entries'] == ['badNames', 'BagTransfer.zip', 'Images']
        assert resp['properties']['BagTransfer.zip']['size'] == 13187
        assert resp['properties']['BagTransfer.zip']['timestamp'] == '2015-04-10T21:52:09.559240'

    @vcr.use_cassette('locations/fixtures/vcr_cassettes/swift_browse_unicode.yaml')
    def test_browse_unicode(self):
        resp = self.swift_object.browse('transfers/SampleTransfers/Images')
        assert resp
        assert resp['directories'] == ['pictures']
        assert resp['entries'] == ['799px-Euroleague-LE Roma vs Toulouse IC-27.bmp', 'BBhelmet.ai', 'G31DS.TIF', 'lion.svg', 'Nemastylis_geminiflora_Flower.PNG', 'oakland03.jp2', 'pictures', 'Vector.NET-Free-Vector-Art-Pack-28-Freedom-Flight.eps', 'WFPC01.GIF', u'エブリンの写真.jpg']
        assert resp['properties'][u'エブリンの写真.jpg']['size'] == 158131
        assert resp['properties'][u'エブリンの写真.jpg']['timestamp'] == '2015-04-10T21:56:43.264560'
