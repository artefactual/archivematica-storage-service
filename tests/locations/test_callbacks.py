import uuid
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


def mock_uuid():
    return uuid.UUID("e3e70682-c209-4cac-629f-6fbed82c07cd")


class TestCallbacksViews(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        User.objects.create_user(
            username="admin",
            password="admin",
            email="admin@example.com",
            is_superuser=True,
        )

    def setUp(self):
        self.client.login(username="admin", password="admin")

    def test_displays_no_callbacks_message(self):
        response = self.client.get(reverse("locations:callback_list"))
        self.assertContains(response, "No callbacks currently exist.")
        payload = response.context["callbacks_table_payload"]
        self.assertEqual(payload["kind"], "callbacks-list")
        self.assertEqual(payload["rows"], [])

    @mock.patch(
        "archivematica.storage_service.locations.models.event.fields.UUIDField.get_default",
        mock.Mock(side_effect=mock_uuid),
    )
    def _create_callback(self):
        response = self.client.post(
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
        self.assertContains(response, "Callback saved.")

    def test_displays_callbacks_table(self):
        self._create_callback()
        response = self.client.get(reverse("locations:callback_list"))
        self.assertNotContains(response, "No callbacks currently exist.")
        payload = response.context["callbacks_table_payload"]
        self.assertEqual(payload["kind"], "callbacks-list")
        self.assertEqual(
            [column["key"] for column in payload["columns"]],
            [
                "event",
                "uri",
                "method",
                "expectedResponse",
                "uuid",
                "enabled",
                "actions",
            ],
        )
        self.assertEqual(len(payload["rows"]), 1)

        row = payload["rows"][0]
        self.assertEqual(row["event"], "Post-store AIP")
        self.assertEqual(row["uri"], "http://localhost")
        self.assertEqual(row["method"], "get")
        self.assertEqual(row["expectedResponse"], 200)
        self.assertEqual(row["uuid"], "e3e70682-c209-4cac-629f-6fbed82c07cd")
        self.assertEqual(row["enabled"], "Disabled")
        self.assertIn('id="tables-callbacks-table-payload"', response.text)
