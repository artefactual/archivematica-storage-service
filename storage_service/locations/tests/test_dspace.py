
import os

from django.test import TestCase
import vcr

from locations import models

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
FIXTURES_DIR = os.path.abspath(os.path.join(THIS_DIR, '..', 'fixtures'))

dspace_vcr = vcr.VCR(
    filter_headers=['authorization'],
)

class TestDSpace(TestCase):

    fixtures = ['base.json', 'dspace.json']

    def setUp(self):
        self.dspace_object = models.DSpace.objects.all()[0]

    def test_has_required_attributes(self):
        assert self.dspace_object.sd_iri
        assert self.dspace_object.user
        assert self.dspace_object.password
        assert self.dspace_object.sword_connection is None

    @dspace_vcr.use_cassette(os.path.join(FIXTURES_DIR, 'vcr_cassettes', 'dspace_browse.yaml'))
    def test_browse(self):
        pass

    @dspace_vcr.use_cassette(os.path.join(FIXTURES_DIR, 'vcr_cassettes', 'dspace_delete.yaml'))
    def test_delete(self):
        pass

    @dspace_vcr.use_cassette(os.path.join(FIXTURES_DIR, 'vcr_cassettes', 'dspace_move_from_ss.yaml'))
    def test_move_from_ss(self):
        pass

    @dspace_vcr.use_cassette(os.path.join(FIXTURES_DIR, 'vcr_cassettes', 'dspace_move_to_ss.yaml'))
    def test_move_to_ss(self):
        pass
