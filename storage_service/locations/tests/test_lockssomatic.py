import os

from django.test import TestCase
import vcr

from locations import models

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
FIXTURES_DIR = os.path.abspath(os.path.join(THIS_DIR, "..", "fixtures"))


class TestLockssomatic(TestCase):

    fixtures = ["base.json", "lockssomatic.json"]

    def setUp(self):
        self.lom_object = models.Lockssomatic.objects.all()[0]

    @vcr.use_cassette(
        os.path.join(FIXTURES_DIR, "vcr_cassettes", "test_lockssomatic_bad_url.yaml")
    )
    def test_service_doc_bad_url(self):
        self.lom_object.sd_iri = "http://does-not-exist.com"
        assert self.lom_object.update_service_document() is False
        assert self.lom_object.au_size == 0
        assert self.lom_object.collection_iri is None
        assert self.lom_object.checksum_type is None
