import hmac
import uuid
from hashlib import sha1
from unittest import mock

import pytest
import pytest_django
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse
from tastypie.models import ApiKey

from archivematica.storage_service.administration import roles


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
    django_user_model: type[User],
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


@pytest.fixture
def user(django_user_model: type[User]) -> User:
    return django_user_model.objects.create_user(
        username="test", password="ck61Qc873.KxoZ5G", email="test@example.com"
    )


@pytest.mark.django_db
def test_edit_user_promote_as_manager(
    admin_client: Client,
    settings: pytest_django.fixtures.SettingsWrapper,
    user: User,
) -> None:
    """Only administrators are allowed to promote/demote users."""
    resp = admin_client.post(
        reverse("administration:user_edit", kwargs={"id": user.pk}),
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
    user.refresh_from_db()
    assert user.get_role() == roles.USER_ROLE_MANAGER


@pytest.mark.django_db
def test_edit_user_promotion_requires_admin(
    admin_client: Client,
    settings: pytest_django.fixtures.SettingsWrapper,
    django_user_model: type[User],
    user: User,
) -> None:
    """Only administrators are allowed to promote/demote users."""
    as_manager(django_user_model.objects.get(username="admin"))

    resp = admin_client.post(
        reverse("administration:user_edit", kwargs={"id": user.pk}),
        {
            "user": "Edit User",
            "username": "test",
            "email": "test@example.com",
            "role": "manager",
        },
        follow=True,
    )
    assert resp.status_code == 200

    user.refresh_from_db()
    assert user.get_role() == roles.USER_ROLE_READER


@pytest.fixture
def admin_user_apikey(admin_client: Client, django_user_model: type[User]) -> ApiKey:
    return ApiKey.objects.create(user=django_user_model.objects.get(username="admin"))


@pytest.mark.django_db
def test_user_edit_view_updates_password(
    admin_client: Client,
    settings: pytest_django.fixtures.SettingsWrapper,
    django_user_model: type[User],
    admin_user_apikey: ApiKey,
) -> None:
    user = django_user_model.objects.get(username="admin")
    assert user.check_password("password")
    new_password = "ck61Qc873.KxoZ5G"

    response = admin_client.post(
        reverse("administration:user_edit", kwargs={"id": user.pk}),
        {
            "new_password1": new_password,
            "new_password2": new_password,
            "password": "1",
        },
        follow=True,
    )
    assert response.status_code == 200

    user.refresh_from_db()
    assert user.check_password(new_password)
    assert "Password changed" in response.content.decode()


@pytest.mark.django_db
def test_user_edit_view_regenerates_api_key(
    admin_client: Client,
    settings: pytest_django.fixtures.SettingsWrapper,
    django_user_model: type[User],
    admin_user_apikey: ApiKey,
) -> None:
    user = django_user_model.objects.get(username="admin")
    assert user.check_password("password")
    new_password = "ck61Qc873.KxoZ5G"
    expected_uuid = uuid.uuid4()
    expected_key = hmac.new(expected_uuid.bytes, digestmod=sha1).hexdigest()

    with mock.patch("uuid.uuid4", return_value=expected_uuid):
        response = admin_client.post(
            reverse("administration:user_edit", kwargs={"id": user.pk}),
            {
                "new_password1": new_password,
                "new_password2": new_password,
                "password": "1",
            },
            follow=True,
        )
        assert response.status_code == 200

    user.refresh_from_db()
    assert user.check_password(new_password)
    assert "Password changed" in response.content.decode()

    admin_user_apikey.refresh_from_db()
    assert admin_user_apikey.key == expected_key
