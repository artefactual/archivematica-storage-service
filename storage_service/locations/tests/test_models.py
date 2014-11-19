
from django.test import TestCase

from locations import models


class TestLockssomatic(TestCase):

    fixtures = ['base.json', 'lockssomatic.json']

    def setUp(self):
        self.lom_object = models.Lockssomatic.objects.all()[0]

    def test_service_doc_bad_url(self):
        self.lom_object.sd_iri = 'http://does-not-exist.com'
        assert self.lom_object.update_service_document() == False
        assert self.lom_object.au_size == 0
        assert self.lom_object.collection_iri == None
        assert self.lom_object.checksum_type == None

    def test_get_service_doc(self):
        # TODO mock response
        assert self.lom_object.au_size == None
        ret = self.lom_object.update_service_document()
        assert ret == True
        assert self.lom_object.au_size != 0
        assert self.lom_object.sd_iri  # is positive
        assert self.lom_object.collection_iri != ''
        assert self.lom_object.checksum_type != None

