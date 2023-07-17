# from django.test import TestCase
# import vcr
#
# from locations import models
#
# THIS_DIR = os.path.dirname(os.path.abspath(__file__))
# FIXTURES_DIR = os.path.abspath(os.path.join(THIS_DIR, '..', 'fixtures'))
#
# class TestExample(TestCase):
#
#     fixtures = ['base.json', 'example.json']
#
#     def setUp(self):
#         self.example_object = models.Example.objects.all()[0]
#
#     @vcr.use_cassette(os.path.join(FIXTURES_DIR, 'vcr_cassettes', 'example_browse.yaml'))
#     def test_browse(self):
#         pass
#
#     @vcr.use_cassette(os.path.join(FIXTURES_DIR, 'vcr_cassettes', 'example_delete.yaml'))
#     def test_delete(self):
#         pass
#
#     @vcr.use_cassette(os.path.join(FIXTURES_DIR, 'vcr_cassettes', 'example_move_from_ss.yaml'))
#     def test_move_from_ss(self):
#         pass
#
#     @vcr.use_cassette(os.path.join(FIXTURES_DIR, 'vcr_cassettes', 'example_move_to_ss.yaml'))
#     def test_move_to_ss(self):
#         pass