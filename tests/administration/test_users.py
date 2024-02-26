from unittest import skipIf

from administration import roles
from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


class TestUserManagement(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="admin",
            password="admin",
            email="admin@example.com",
            is_superuser=True,
        )
        self.client.login(username="admin", password="admin")

    def as_reader(self):
        self.user.set_role(roles.USER_ROLE_READER)

    def as_manager(self):
        self.user.set_role(roles.USER_ROLE_MANAGER)

    def test_list_users(self):
        """The user list is available to all users."""
        resp = self.client.get(reverse("administration:user_list"))

        self.assertContains(resp, "<td>admin@example.com</td>")

    @skipIf(not settings.ALLOW_USER_EDITS, "User edits are disabled")
    def test_create_user_as_admin(self):
        """Only administrators are allowed to create new users."""
        resp = self.client.post(
            reverse("administration:user_create"),
            {
                "username": "demo",
                "email": "demo@example.com",
                "role": "manager",
                "password1": "ck61Qc873.KxoZ5G",
                "password2": "ck61Qc873.KxoZ5G",
            },
        )

        self.assertRedirects(
            resp,
            reverse("administration:user_list"),
            status_code=302,
            target_status_code=200,
            fetch_redirect_response=True,
        )
        assert User.objects.filter(username="demo").exists() is True

    @skipIf(not settings.ALLOW_USER_EDITS, "User edits are disabled")
    def test_create_user_as_non_admin(self):
        """Only administrators are allowed to create new users."""
        self.as_reader()
        resp = self.client.post(
            reverse("administration:user_create"),
            {
                "username": "demo",
                "email": "demo@example.com",
                "role": "manager",
                "password1": "ck61Qc873.KxoZ5G",
                "password2": "ck61Qc873.KxoZ5G",
            },
        )

        self.assertRedirects(
            resp,
            reverse("administration:user_list"),
            status_code=302,
            target_status_code=200,
            fetch_redirect_response=True,
        )
        assert User.objects.filter(username="demo").exists() is False

    @skipIf(not settings.ALLOW_USER_EDITS, "User edits are disabled")
    def test_edit_user_promote_as_manager(self):
        """Only administrators are allowed to promote/demote users."""
        test = User.objects.create_user(
            username="test", password="ck61Qc873.KxoZ5G", email="test@example.com"
        )
        resp = self.client.post(
            reverse("administration:user_edit", kwargs={"id": test.pk}),
            {
                "user": "Edit User",
                "username": "test",
                "email": "test@example.com",
                "role": "manager",
            },
            follow=True,
        )

        assert list(resp.context["messages"])[0].message == "User information saved."
        test.refresh_from_db()
        assert test.get_role() == roles.USER_ROLE_MANAGER

    @skipIf(not settings.ALLOW_USER_EDITS, "User edits are disabled")
    def test_edit_user_promotion_requires_admin(self):
        """Only administrators are allowed to promote/demote users."""
        self.as_manager()
        test = User.objects.create_user(
            username="test", password="ck61Qc873.KxoZ5G", email="test@example.com"
        )
        resp = self.client.post(
            reverse("administration:user_edit", kwargs={"id": test.pk}),
            {
                "user": "Edit User",
                "username": "test",
                "email": "test@example.com",
                "role": "manager",
            },
        )

        self.assertRedirects(
            resp,
            reverse("administration:user_list"),
            status_code=302,
            target_status_code=200,
            fetch_redirect_response=True,
        )
        test.refresh_from_db()
        assert test.get_role() == roles.USER_ROLE_READER
