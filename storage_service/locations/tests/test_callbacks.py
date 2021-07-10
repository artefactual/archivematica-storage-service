import uuid

from django.contrib.auth.models import User
from django.test import TestCase
from unittest import mock


def mock_uuid():
    return uuid.UUID("e3e70682-c209-4cac-629f-6fbed82c07cd")


class TestCallbacksViews(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        User.objects.create_user(
            username="admin", password="admin", email="admin@example.com"
        )

    def setUp(self):
        self.client.login(username="admin", password="admin")
        self.callbacks_table_headers = [
            "<th>Event</th>",
            "<th>URI</th>",
            "<th>Method</th>",
            "<th>Expected response</th>",
            "<th>UUID</th>",
            "<th>Enabled</th>",
            "<th>Actions</th>",
        ]

    def test_displays_no_callbacks_message(self):
        response = self.client.get("/callbacks/")
        self.assertContains(response, "No callbacks currently exist.")
        for header in self.callbacks_table_headers:
            self.assertNotContains(response, header, html=True)

    @mock.patch("uuid.uuid4", mock_uuid)
    def _create_callback(self):
        response = self.client.post(
            "/callbacks/create/",
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
        response = self.client.get("/callbacks/")
        self.assertNotContains(response, "No callbacks currently exist.")
        for header in self.callbacks_table_headers:
            self.assertContains(response, header, html=True)
        callback_columns = [
            "<td>Post-store AIP</td>",
            "<td>http://localhost</td>",
            "<td>get</td>",
            "<td>200</td>",
            "<td>e3e70682-c209-4cac-629f-6fbed82c07cd</td>",
            "<td>Disabled</td>",
        ]
        for column in callback_columns:
            self.assertContains(response, column, html=True)
