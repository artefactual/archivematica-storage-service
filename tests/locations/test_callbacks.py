import uuid
from unittest import mock

import pytest
from django.test import Client
from django.urls import reverse
from pytest_django.asserts import assertContains
from pytest_django.asserts import assertNotContains

# The form creates the callback with this UUID.
CALLBACK_UUID = uuid.uuid4()


def mock_uuid() -> uuid.UUID:
    return CALLBACK_UUID


@pytest.mark.django_db
def test_displays_no_callbacks_message(admin_client: Client) -> None:
    response = admin_client.get(reverse("locations:callback_list"))
    assertContains(response, "No callbacks currently exist.")
    payload = response.context["callbacks_table_payload"]
    assert payload["kind"] == "callbacks-list"
    assert payload["rows"] == []


@mock.patch(
    "archivematica.storage_service.locations.models.event.fields.UUIDField.get_default",
    mock.Mock(side_effect=mock_uuid),
)
def _create_callback(admin_client: Client) -> None:
    response = admin_client.post(
        reverse("locations:callback_create"),
        {
            "uri": "http://localhost",
            "event": "post_store_aip",
            "method": "get",
            "body": "ping!",
            "enabled": False,
            "expected_status": 200,
        },
        follow=True,
    )
    assertContains(response, "Callback saved.")


@pytest.mark.django_db
def test_displays_callbacks_table(admin_client: Client) -> None:
    _create_callback(admin_client)
    response = admin_client.get(reverse("locations:callback_list"))
    assertNotContains(response, "No callbacks currently exist.")
    payload = response.context["callbacks_table_payload"]
    assert payload["kind"] == "callbacks-list"
    assert [column["key"] for column in payload["columns"]] == [
        "event",
        "uri",
        "method",
        "expectedResponse",
        "uuid",
        "enabled",
        "actions",
    ]
    assert len(payload["rows"]) == 1

    row = payload["rows"][0]
    assert row["event"] == "Post-store AIP"
    assert row["uri"] == "http://localhost"
    assert row["method"] == "get"
    assert row["expectedResponse"] == 200
    assert row["uuid"] == str(CALLBACK_UUID)
    assert row["enabled"] == "Disabled"
    assert 'id="tables-callbacks-table-payload"' in response.text
