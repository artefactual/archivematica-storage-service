from typing import Type

import pytest
import pytest_django
from administration import roles
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse


def as_reader(user: User) -> None:
    user.set_role(roles.USER_ROLE_READER)


def as_manager(user: User) -> None:
    user.set_role(roles.USER_ROLE_MANAGER)


@pytest.mark.django_db
def test_list_users(admin_client: Client) -> None:
    """The user list is available to all users."""
    resp = admin_client.get(reverse("administration:user_list"))

    assert "<td>admin@example.com</td>" in resp.content.decode()


@pytest.fixture
def settings(
    settings: pytest_django.fixtures.SettingsWrapper,
) -> pytest_django.fixtures.SettingsWrapper:
    settings.ALLOW_USER_EDITS = True

    return settings


@pytest.mark.django_db
def test_create_user_as_admin(
    admin_client: Client, settings: pytest_django.fixtures.SettingsWrapper
) -> None:
    """Only administrators are allowed to create new users."""
    resp = admin_client.post(
        reverse("administration:user_create"),
        {
            "username": "demo",
            "email": "demo@example.com",
            "role": "manager",
            "password1": "ck61Qc873.KxoZ5G",
            "password2": "ck61Qc873.KxoZ5G",
        },
        follow=True,
    )
    assert resp.status_code == 200

    assert "<td>demo@example.com</td>" in resp.content.decode()
    assert User.objects.filter(username="demo").exists()


@pytest.mark.django_db
def test_create_user_as_non_admin(
    admin_client: Client,
    settings: pytest_django.fixtures.SettingsWrapper,
    django_user_model: Type[User],
) -> None:
    """Only administrators are allowed to create new users."""
    as_reader(django_user_model.objects.get(username="admin"))

    resp = admin_client.post(
        reverse("administration:user_create"),
        {
            "username": "demo",
            "email": "demo@example.com",
            "role": "manager",
            "password1": "ck61Qc873.KxoZ5G",
            "password2": "ck61Qc873.KxoZ5G",
        },
        follow=True,
    )
    assert resp.status_code == 200

    assert "<td>demo@example.com</td>" not in resp.content.decode()
    assert not User.objects.filter(username="demo").exists()


@pytest.mark.django_db
def test_edit_user_promote_as_manager(
    admin_client: Client,
    settings: pytest_django.fixtures.SettingsWrapper,
    django_user_model: Type[User],
) -> None:
    """Only administrators are allowed to promote/demote users."""
    test = django_user_model.objects.create_user(
        username="test", password="ck61Qc873.KxoZ5G", email="test@example.com"
    )
    resp = admin_client.post(
        reverse("administration:user_edit", kwargs={"id": test.pk}),
        {
            "user": "Edit User",
            "username": "test",
            "email": "test@example.com",
            "role": "manager",
        },
        follow=True,
    )
    assert resp.status_code == 200

    assert list(resp.context["messages"])[0].message == "User information saved."
    test.refresh_from_db()
    assert test.get_role() == roles.USER_ROLE_MANAGER


@pytest.mark.django_db
def test_edit_user_promotion_requires_admin(
    admin_client: Client,
    settings: pytest_django.fixtures.SettingsWrapper,
    django_user_model: Type[User],
) -> None:
    """Only administrators are allowed to promote/demote users."""
    as_manager(django_user_model.objects.get(username="admin"))
    test = django_user_model.objects.create_user(
        username="test", password="ck61Qc873.KxoZ5G", email="test@example.com"
    )

    resp = admin_client.post(
        reverse("administration:user_edit", kwargs={"id": test.pk}),
        {
            "user": "Edit User",
            "username": "test",
            "email": "test@example.com",
            "role": "manager",
        },
        follow=True,
    )
    assert resp.status_code == 200

    test.refresh_from_db()
    assert test.get_role() == roles.USER_ROLE_READER
