
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
        self.dspace_object = models.DSpace.objects.get(id=1)

    def tearDown(self):
        try:
            os.remove(os.path.join(FIXTURES_DIR, 'test.txt'))
        except OSError:
            pass

    def test_has_required_attributes(self):
        assert self.dspace_object.sd_iri
        assert self.dspace_object.user
        assert self.dspace_object.password
        assert self.dspace_object.sword_connection is None

    @dspace_vcr.use_cassette(os.path.join(FIXTURES_DIR, 'vcr_cassettes', 'dspace_get_sword_connection.yaml'))
    def test_get_sword_connection(self):
        assert self.dspace_object.sword_connection is None
        self.dspace_object._get_sword_connection()
        assert self.dspace_object.sword_connection is not None
        # Format is [ ( 'string', [collections] )]
        assert self.dspace_object.sword_connection.workspaces[0][1][0].title == 'Test collection'

    @dspace_vcr.use_cassette(os.path.join(FIXTURES_DIR, 'vcr_cassettes', 'dspace_browse.yaml'))
    def test_browse(self):
        pass

    @dspace_vcr.use_cassette(os.path.join(FIXTURES_DIR, 'vcr_cassettes', 'dspace_delete.yaml'))
    def test_delete(self):
        pass

    @dspace_vcr.use_cassette(os.path.join(FIXTURES_DIR, 'vcr_cassettes', 'dspace_move_from_ss.yaml'))
    def test_move_from_ss(self):
        # Create test.txt
        with open(os.path.join(FIXTURES_DIR, 'test.txt'), 'w') as f:
            f.write('test file\n')
        package = models.Package.objects.get(uuid='1056123d-8a16-49c2-ac51-8e5fa367d8b5')

        # Upload
        self.dspace_object.move_from_storage_service(os.path.join(FIXTURES_DIR, 'test.txt'), 'irrelevent', package=package)

        # Verify
        assert package.current_path == 'http://demo.dspace.org/swordv2/statement/86.atom'
        assert package.misc_attributes['handle'] == '123456789/35'
        # FIXME How to verify?

    @dspace_vcr.use_cassette(os.path.join(FIXTURES_DIR, 'vcr_cassettes', 'dspace_move_to_ss.yaml'))
    def test_move_to_ss(self):
        pass
