import pathlib
import uuid
from unittest import mock
from urllib.parse import ParseResult
from urllib.parse import urlparse

import pytest
import pytest_django
from django.test import Client
from django.urls import reverse

from archivematica.storage_service.locations import models

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture
def pipeline() -> models.Pipeline:
    return models.Pipeline.objects.create(
        description="My pipeline",
        remote_name="127.0.0.1",
        api_username="user",
        api_key="key",
    )


@pytest.mark.django_db
def test_parse_and_fix_url(pipeline: models.Pipeline) -> None:
    res = pipeline.parse_and_fix_url(pipeline.remote_name)
    assert isinstance(res, ParseResult)
    assert res.geturl() == "http://127.0.0.1"


@pytest.mark.django_db
def test_parse_and_fix_url_with_empty_remote_name(pipeline: models.Pipeline) -> None:
    pipeline.remote_name = ""
    pipeline.save()

    res = pipeline.parse_and_fix_url(pipeline.remote_name)
    assert res == urlparse("")

    url = "https://archivematica-dashboard"
    assert pipeline.parse_and_fix_url(url) == urlparse(url)

    url = "https://foo@bar:ss.qa.usip.tld:1234/dev/"
    assert pipeline.parse_and_fix_url(url) == urlparse(url)


@pytest.mark.django_db
@mock.patch("requests.request")
def test_request_api(
    request: mock.Mock,
    pipeline: models.Pipeline,
    settings: pytest_django.fixtures.SettingsWrapper,
) -> None:
    method = "GET"
    url = "http://127.0.0.1/api/processing-configuration/default"
    headers = {"Authorization": f"ApiKey {pipeline.api_username}:{pipeline.api_key}"}

    pipeline._request_api(method, "processing-configuration/default")
    request.assert_called_with(
        method, url, allow_redirects=True, data=None, headers=headers, verify=True
    )

    settings.INSECURE_SKIP_VERIFY = True
    pipeline._request_api(method, "processing-configuration/default")
    request.assert_called_with(
        method,
        url,
        allow_redirects=True,
        data=None,
        headers=headers,
        verify=False,
    )


@pytest.mark.django_db
@mock.patch(
    "archivematica.storage_service.locations.models.Pipeline._request_api",
    side_effect=[
        mock.Mock(
            **{
                "status_code": 200,
                "json.return_value": {
                    "message": "Fetched unapproved transfers successfully.",
                    "results": [
                        {
                            "directory": "Foobar1",
                            "type": "standard",
                            "uuid": "090b7f5b-637b-400b-9014-3eb58986fe8f",
                        }
                    ],
                },
            }
        )
    ],
)
def test_list_unapproved_transfers(
    request_api: mock.Mock, pipeline: models.Pipeline
) -> None:
    result = pipeline.list_unapproved_transfers()

    assert isinstance(result, dict) is True
    assert result["message"] == "Fetched unapproved transfers successfully."
    assert len(result["results"]) == 1
    assert result["results"][0]["directory"] == "Foobar1"
    assert result["results"][0]["type"] == "standard"
    assert result["results"][0]["uuid"] == "090b7f5b-637b-400b-9014-3eb58986fe8f"


@pytest.mark.django_db
@mock.patch(
    "archivematica.storage_service.locations.models.Pipeline._request_api",
    side_effect=[
        mock.Mock(
            **{
                "status_code": 200,
                "json.return_value": {
                    "message": "Approval successful.",
                    "uuid": "090b7f5b-637b-400b-9014-3eb58986fe8f",
                },
            }
        )
    ],
)
def test_approve_transfer(request_api: mock.Mock, pipeline: models.Pipeline) -> None:
    result = pipeline.approve_transfer("Foobar1", "standard")

    assert result["message"] == "Approval successful."
    assert result["uuid"] == "090b7f5b-637b-400b-9014-3eb58986fe8f"


def test_view_create_pipeline(admin_client: Client) -> None:
    url = reverse("locations:pipeline_create")

    resp = admin_client.get(url, follow=True)
    form = resp.context["form"]

    assert resp.status_code == 200
    assert form.initial["enabled"] is True
    assert form.initial["create_default_locations"] is True


def test_view_create_pipeline_invalid_post(admin_client: Client) -> None:
    url = reverse("locations:pipeline_create")

    resp = admin_client.post(url, follow=True, data={})
    form = resp.context["form"]

    assert form.is_valid() is False


def test_view_create_pipeline_post(admin_client: Client) -> None:
    url = reverse("locations:pipeline_create")

    resp = admin_client.post(
        url, follow=True, data={"uuid": "0d9d6be9-2751-4e81-b85f-fe4e51a1f789"}
    )
    messages = list(resp.context["messages"])

    assert models.Pipeline.objects.filter(
        uuid="0d9d6be9-2751-4e81-b85f-fe4e51a1f789"
    ).exists()
    assert str(messages[0]) == "Pipeline saved."


def test_view_edit_pipeline(admin_client: Client, pipeline: models.Pipeline) -> None:
    url = reverse("locations:pipeline_edit", args=[pipeline.uuid])

    resp = admin_client.get(url, follow=True)
    form = resp.context["form"]

    assert form.initial == {
        "uuid": pipeline.uuid,
        "description": pipeline.description,
        "remote_name": pipeline.remote_name,
        "api_username": pipeline.api_username,
        "api_key": pipeline.api_key,
        "enabled": pipeline.enabled,
    }


def test_view_edit_pipeline_invalid_post(
    admin_client: Client, pipeline: models.Pipeline
) -> None:
    url = reverse("locations:pipeline_edit", args=[pipeline.uuid])

    resp = admin_client.post(url, follow=True, data={})
    form = resp.context["form"]

    assert form.is_valid() is False


def test_view_edit_pipeline_post(
    admin_client: Client, pipeline: models.Pipeline
) -> None:
    url = reverse("locations:pipeline_edit", args=[pipeline.uuid])
    description = "Pipeline 3ebf"
    remote_name = "localhost"
    api_username = "newapiusername"
    api_key = "newapikey"

    resp = admin_client.post(
        url,
        follow=True,
        data={
            "uuid": str(pipeline.uuid),
            "description": description,
            "remote_name": remote_name,
            "api_username": api_username,
            "api_key": api_key,
        },
    )
    messages = list(resp.context["messages"])

    pipeline.refresh_from_db()
    assert pipeline.description == description
    assert pipeline.remote_name == remote_name
    assert pipeline.api_username == api_username
    assert pipeline.api_key == api_key
    assert str(messages[0]) == "Pipeline saved."


def test_pipeline_detail_view_shows_pipeline_fields(
    admin_client: Client, pipeline: models.Pipeline
) -> None:
    response = admin_client.get(
        reverse("locations:pipeline_detail", kwargs={"uuid": pipeline.uuid})
    )
    assert response.status_code == 200

    content = response.content.decode()
    assert f"<dd>{pipeline.uuid}</dd>" in content
    assert f"<dd>{pipeline.description}</dd>" in content
    assert f"<dd>{pipeline.remote_name}</dd>" in content
    assert f"<dd> {pipeline.api_username} / {pipeline.api_key}</dd>" in content
    assert "No locations currently exist" in content


def test_pipeline_detail_view_warns_if_pipeline_does_not_exist(
    admin_client: Client, pipeline: models.Pipeline
) -> None:
    pipeline_uuid = uuid.uuid4()
    response = admin_client.get(
        reverse("locations:pipeline_detail", kwargs={"uuid": pipeline_uuid}),
        follow=True,
    )
    assert response.status_code == 200

    content = response.content.decode()
    assert f"Pipeline {pipeline_uuid} does not exist." in content
