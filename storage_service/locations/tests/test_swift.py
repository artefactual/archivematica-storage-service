
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
