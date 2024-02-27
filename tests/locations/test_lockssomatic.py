import pathlib
from unittest import mock

from django.test import TestCase
from locations import models

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"


class TestLockssomatic(TestCase):
    fixture_files = ["base.json", "lockssomatic.json"]
    fixtures = [FIXTURES_DIR / f for f in fixture_files]

    def setUp(self):
        self.lom_object = models.Lockssomatic.objects.all()[0]

    @mock.patch("httplib2.Http.request", side_effect=[(mock.Mock(status=200), "")])
    def test_service_doc_bad_url(self, _connection):
        self.lom_object.sd_iri = "http://does-not-exist.com"
        assert self.lom_object.update_service_document() is False
        assert self.lom_object.au_size == 0
        assert self.lom_object.collection_iri is None
        assert self.lom_object.checksum_type is None
