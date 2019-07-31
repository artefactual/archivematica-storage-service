from __future__ import absolute_import
import os

from django.test import TestCase
from django.utils.six.moves.urllib.parse import ParseResult, urlparse

from locations import models

import mock
import vcr


THIS_DIR = os.path.dirname(os.path.abspath(__file__))
FIXTURES_DIR = os.path.abspath(os.path.join(THIS_DIR, "..", "fixtures"))


class TestPipeline(TestCase):

    fixtures = ["base.json", "pipelines.json"]

    def test_parse_and_fix_url(self):
        pipeline = models.Pipeline.objects.get(pk=1)
        res = pipeline.parse_and_fix_url(pipeline.remote_name)
        assert isinstance(res, ParseResult)
        assert res.geturl() == "http://127.0.0.1"

        pipeline = models.Pipeline.objects.get(pk=2)
        res = pipeline.parse_and_fix_url(pipeline.remote_name)
        assert res == urlparse("")

        url = "https://archivematica-dashboard"
        assert pipeline.parse_and_fix_url(url) == urlparse(url)

        url = "https://foo@bar:ss.qa.usip.tld:1234/dev/"
        assert pipeline.parse_and_fix_url(url) == urlparse(url)

    @mock.patch("requests.request")
    def test_request_api(self, request):
        pipeline = models.Pipeline.objects.get(pk=1)

        method = "GET"
        url = "http://127.0.0.1/api/processing-configuration/default"
        headers = {"Authorization": "ApiKey None:None"}

        pipeline._request_api(method, "processing-configuration/default")
        request.assert_called_with(
            method, url, allow_redirects=True, data=None, headers=headers, verify=True
        )

        with self.settings(INSECURE_SKIP_VERIFY=True):
            pipeline._request_api(method, "processing-configuration/default")
            request.assert_called_with(
                method,
                url,
                allow_redirects=True,
                data=None,
                headers=headers,
                verify=False,
            )

    @vcr.use_cassette(
        os.path.join(
            FIXTURES_DIR, "vcr_cassettes", "pipeline_list_unapproved_transfers.yaml"
        )
    )
    def test_list_unapproved_transfers(self):
        pipeline = models.Pipeline.objects.get(pk=3)
        result = pipeline.list_unapproved_transfers()

        assert isinstance(result, dict) is True
        assert result["message"] == "Fetched unapproved transfers successfully."
        assert len(result["results"]) == 1
        assert result["results"][0]["directory"] == "Foobar1"
        assert result["results"][0]["type"] == "standard"
        assert result["results"][0]["uuid"] == "090b7f5b-637b-400b-9014-3eb58986fe8f"

    @vcr.use_cassette(
        os.path.join(FIXTURES_DIR, "vcr_cassettes", "pipeline_approve_transfer.yaml")
    )
    def test_approve_transfer(self):
        pipeline = models.Pipeline.objects.get(pk=3)
        result = pipeline.approve_transfer("Foobar1", "standard")

        assert result["message"] == "Approval successful."
        assert result["uuid"] == "090b7f5b-637b-400b-9014-3eb58986fe8f"
