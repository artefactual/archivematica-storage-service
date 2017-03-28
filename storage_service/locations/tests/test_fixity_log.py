from django.test import TestCase

from locations import models


class TestFixityLog(TestCase):

    fixtures = ['base.json', 'package.json', 'fixity_log.json']

    def setUp(self):
        self.fl_object = models.FixityLog.objects.all()[0]
        #self.auth = requests.auth.HTTPBasicAuth(self.ds_object.user, self.ds_object.password)

    def test_has_required_attributes(self):
        assert self.fl_object.package
        assert self.fl_object.success
        assert self.fl_object.error_details
        assert self.fl_object.datetime_reported
