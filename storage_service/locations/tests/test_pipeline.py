from urllib.parse import ParseResult, urlparse
import os

from django.test import TestCase
from django.urls import reverse

from locations import models

from unittest import mock
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


class TestPipelineViews(TestCase):

    fixtures = ["base.json", "pipelines.json"]

    def setUp(self):
        self.client.login(username="test", password="test")

    def test_view_create_pipeline(self):
        url = reverse("locations:pipeline_create")

        resp = self.client.get(url, follow=True)
        form = resp.context["form"]

        assert resp.status_code == 200
        assert form.initial["enabled"] is True
        assert form.initial["create_default_locations"] is True

    def test_view_create_pipeline_invalid_post(self):
        url = reverse("locations:pipeline_create")

        resp = self.client.post(url, follow=True, data={})
        form = resp.context["form"]

        assert form.is_valid() is False

    def test_view_create_pipeline_post(self):
        url = reverse("locations:pipeline_create")

        resp = self.client.post(
            url, follow=True, data={"uuid": "0d9d6be9-2751-4e81-b85f-fe4e51a1f789"}
        )
        messages = list(resp.context["messages"])

        self.assertRedirects(resp, reverse("locations:pipeline_list"))
        assert models.Pipeline.objects.filter(
            uuid="0d9d6be9-2751-4e81-b85f-fe4e51a1f789"
        ).exists()
        assert str(messages[0]) == "Pipeline saved."

    def test_view_edit_pipeline(self):
        url = reverse(
            "locations:pipeline_edit", args=["b25f6b71-3ebf-4fcc-823c-1feb0a2553dd"]
        )

        resp = self.client.get(url, follow=True)
        form = resp.context["form"]

        assert form.initial["enabled"] is True
        assert "create_default_locations" not in form.initial

    def test_view_edit_pipeline_invalid_post(self):
        url = reverse(
            "locations:pipeline_edit", args=["b25f6b71-3ebf-4fcc-823c-1feb0a2553dd"]
        )

        resp = self.client.post(url, follow=True, data={})
        form = resp.context["form"]

        assert form.is_valid() is False

    def test_view_edit_pipeline_post(self):
        url = reverse(
            "locations:pipeline_edit", args=["b25f6b71-3ebf-4fcc-823c-1feb0a2553dd"]
        )

        resp = self.client.post(
            url,
            follow=True,
            data={
                "uuid": "b25f6b71-3ebf-4fcc-823c-1feb0a2553dd",
                "description": "Pipeline 3ebf",
            },
        )
        messages = list(resp.context["messages"])

        self.assertRedirects(resp, reverse("locations:pipeline_list"))
        assert (
            models.Pipeline.objects.get(
                uuid="b25f6b71-3ebf-4fcc-823c-1feb0a2553dd"
            ).description
            == "Pipeline 3ebf"
        )
        assert str(messages[0]) == "Pipeline saved."
