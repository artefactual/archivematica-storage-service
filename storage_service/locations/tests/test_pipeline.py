from django.test import TestCase
from django.utils.six.moves.urllib.parse import ParseResult, urlparse

from locations import models


class TestPipeline(TestCase):

    fixtures = ['base.json', 'pipelines.json']

    def test_parse_url(self):
        pipeline = models.Pipeline.objects.get(pk=1)
        res = pipeline.parse_url()
        assert isinstance(res, ParseResult)
        assert res.geturl() == 'http://127.0.0.1'

        pipeline = models.Pipeline.objects.get(pk=2)
        res = pipeline.parse_url()
        assert res == urlparse('')

        url = 'https://archivematica-dashboard'
        pipeline.remote_name = url
        assert pipeline.parse_url() == \
            urlparse(url)

        url = 'https://foo@bar:ss.qa.usip.tld:1234/dev/'
        pipeline.remote_name = url
        assert pipeline.parse_url() == \
            urlparse(url)
