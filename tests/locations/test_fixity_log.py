import pathlib

from django.test import TestCase
from locations import models

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"


class TestFixityLog(TestCase):
    fixture_files = ["base.json", "package.json", "fixity_log.json"]
    fixtures = [FIXTURES_DIR / f for f in fixture_files]

    def setUp(self):
        self.fl_object = models.FixityLog.objects.all()[0]

    def test_has_required_attributes(self):
        assert self.fl_object.package
        assert not self.fl_object.success
        assert self.fl_object.error_details
        assert self.fl_object.datetime_reported
