from unittest import mock

import pytest
import pytest_django
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpRequest
from django.http import HttpResponse
from django.test import RequestFactory
from django.test.client import Client
from pytest_django.asserts import assertRedirects

from archivematica.storage_service.administration import roles
from archivematica.storage_service.common.backends import CustomCASBackend
from archivematica.storage_service.common.signals import _cas_user_role

TEST_CAS_USER = "casuser"
TEST_CAS_ADMIN_ATTRIBUTE = "usertype"
TEST_CAS_ADMIN_ATTRIBUTE_VALUE_POSITIVE = "admin"
TEST_CAS_ADMIN_ATTRIBUTE_VALUE_NEGATIVE = "regular"

TEST_CAS_ATTRIBUTES_STRING_POSITIVE = {
    TEST_CAS_ADMIN_ATTRIBUTE: TEST_CAS_ADMIN_ATTRIBUTE_VALUE_POSITIVE
}
TEST_CAS_ATTRIBUTES_STRING_NEGATIVE = {
    TEST_CAS_ADMIN_ATTRIBUTE: TEST_CAS_ADMIN_ATTRIBUTE_VALUE_NEGATIVE
}
TEST_CAS_ATTRIBUTES_LIST_POSITIVE = {
    TEST_CAS_ADMIN_ATTRIBUTE: [
        TEST_CAS_ADMIN_ATTRIBUTE_VALUE_POSITIVE,
        "attribute1",
        "attribute2",
    ]
}
TEST_CAS_ATTRIBUTES_LIST_NEGATIVE = {
    TEST_CAS_ADMIN_ATTRIBUTE: [
        TEST_CAS_ADMIN_ATTRIBUTE_VALUE_NEGATIVE,
        "attribute1",
        "attribute2",
    ]
}


def mock_verify(ticket: str, service: str) -> tuple[str, dict[str, str], None]:
    user = TEST_CAS_USER
    attributes = {
        "ticket": ticket,
        "service": service,
        TEST_CAS_ADMIN_ATTRIBUTE: TEST_CAS_ADMIN_ATTRIBUTE_VALUE_NEGATIVE,
    }
    pgtiou = None
    return user, attributes, pgtiou


def mock_verify_superuser(
    ticket: str, service: str
) -> tuple[str, dict[str, str], None]:
    user = TEST_CAS_USER
    attributes = {
        "ticket": ticket,
        "service": service,
        TEST_CAS_ADMIN_ATTRIBUTE: TEST_CAS_ADMIN_ATTRIBUTE_VALUE_POSITIVE,
    }
    pgtiou = None
    return user, attributes, pgtiou


pytestmark = [
    pytest.mark.django_db,
    pytest.mark.skipif(
        not settings.CAS_AUTHENTICATION, reason="tests will only pass if CAS is enabled"
    ),
]


def _authenticate_user(request: HttpRequest) -> None:
    """Helper function to authenticate a user using custom backend."""
    backend = CustomCASBackend()
    backend.authenticate(request, ticket="fake-ticket", service="fake-service")


def _create_request(rf: RequestFactory) -> HttpRequest:
    """Helper function to create request that will redirect to CAS."""
    request = rf.get("/")
    SessionMiddleware(lambda _request: HttpResponse()).process_request(request)
    return request


def test_redirect_for_login(client: Client) -> None:
    """Unauthenticated users should be redirected twice.

    After the initial redirect to LOGIN_URL, the user should be
    redirected again to the CAS server for authentication.
    """
    response = client.get("/")
    expected_redirect = settings.LOGIN_URL + "?next=/"
    assertRedirects(
        response, expected_redirect, status_code=302, target_status_code=302
    )


@mock.patch("cas.CASClientV2.verify_ticket", mock_verify)
def test_autoconfigure_email(
    settings: pytest_django.Settings, rf: RequestFactory
) -> None:
    """Test that email is autoconfigured from username and domain."""
    settings.CAS_AUTOCONFIGURE_EMAIL = True
    settings.CAS_EMAIL_DOMAIN = "artefactual.com"
    request = _create_request(rf)

    # Check that user doesn't already exist.
    assert not User.objects.filter(username=TEST_CAS_USER).exists()

    # Create the user and check its properties.
    _authenticate_user(request)
    user = User.objects.get(username=TEST_CAS_USER)
    assert user.username == TEST_CAS_USER
    assert user.email == "casuser@artefactual.com"


@mock.patch("cas.CASClientV2.verify_ticket", mock_verify_superuser)
def test_check_admin_attributes_superuser_new_user(
    settings: pytest_django.Settings, rf: RequestFactory
) -> None:
    """Test setting is_superuser for new users.

    If settings are properly configured and expected key-value is
    found in the CAS attributes, user.is_superuser should be True.
    """
    # Check that user doesn't already exist.
    assert not User.objects.filter(username=TEST_CAS_USER).exists()

    settings.CAS_CHECK_ADMIN_ATTRIBUTES = True
    settings.CAS_ADMIN_ATTRIBUTE = TEST_CAS_ADMIN_ATTRIBUTE
    settings.CAS_ADMIN_ATTRIBUTE_VALUE = TEST_CAS_ADMIN_ATTRIBUTE_VALUE_POSITIVE
    request = _create_request(rf)
    _authenticate_user(request)
    user = User.objects.get(username=TEST_CAS_USER)
    assert roles.role_user(user).get_role() == roles.USER_ROLE_ADMIN


@mock.patch("cas.CASClientV2.verify_ticket", mock_verify_superuser)
def test_check_admin_attributes_superuser_existing_user(
    settings: pytest_django.Settings, rf: RequestFactory
) -> None:
    """Test setting is_superuser for existing users.

    If settings are properly configured and expected key-value is
    found in the CAS attributes, user.is_superuser for an existing
    non-administrative user should be updated to True.
    """
    user = User.objects.create(username=TEST_CAS_USER)
    assert roles.role_user(user).get_role() == roles.USER_ROLE_READER

    # Authenticate again with CAS_CHECK_ADMIN_ATTRIBUTES enabled
    # and check that user.is_superuser has been updated to True.
    settings.CAS_CHECK_ADMIN_ATTRIBUTES = True
    settings.CAS_ADMIN_ATTRIBUTE = TEST_CAS_ADMIN_ATTRIBUTE
    settings.CAS_ADMIN_ATTRIBUTE_VALUE = TEST_CAS_ADMIN_ATTRIBUTE_VALUE_POSITIVE
    request = _create_request(rf)
    _authenticate_user(request)
    user = User.objects.get(username=TEST_CAS_USER)
    assert roles.role_user(user).get_role() == roles.USER_ROLE_ADMIN


@mock.patch("cas.CASClientV2.verify_ticket", mock_verify)
def test_check_admin_attributes_regular_new_user(
    settings: pytest_django.Settings, rf: RequestFactory
) -> None:
    """Test setting is_superuser for new users.

    If settings are properly configured and expected key-value is
    not found in the CAS attributes, user.is_superuser should be
    False.
    """
    # Check that user doesn't already exist.
    assert not User.objects.filter(username=TEST_CAS_USER).exists()

    settings.CAS_CHECK_ADMIN_ATTRIBUTES = True
    settings.CAS_ADMIN_ATTRIBUTE = TEST_CAS_ADMIN_ATTRIBUTE
    settings.CAS_ADMIN_ATTRIBUTE_VALUE = TEST_CAS_ADMIN_ATTRIBUTE_VALUE_POSITIVE
    request = _create_request(rf)
    _authenticate_user(request)
    user = User.objects.get(username=TEST_CAS_USER)
    assert roles.role_user(user).get_role() == roles.USER_ROLE_MANAGER


@mock.patch("cas.CASClientV2.verify_ticket", mock_verify_superuser)
def test_check_admin_attributes_regular_existing_user(
    settings: pytest_django.Settings, rf: RequestFactory
) -> None:
    """Test setting is_superuser for existing users.

    If settings are properly configured and expected key-value is
    not found in the CAS attributes, user.is_superuser for an
    existing administrative user should be updated to False.
    """
    # Create a new superuser.
    user = User.objects.create(username=TEST_CAS_USER, is_superuser=True)
    assert roles.role_user(user).get_role() == roles.USER_ROLE_ADMIN

    # Authenticate with CAS_ADMIN_ATTRIBUTE_VALUE set to a value
    # not present in the CAS attributes and check that
    # user.is_superuser has been updated to False.
    settings.CAS_CHECK_ADMIN_ATTRIBUTES = True
    settings.CAS_ADMIN_ATTRIBUTE = TEST_CAS_ADMIN_ATTRIBUTE
    settings.CAS_ADMIN_ATTRIBUTE_VALUE = "something else"
    request = _create_request(rf)
    _authenticate_user(request)
    user = User.objects.get(username=TEST_CAS_USER)
    assert roles.role_user(user).get_role() == roles.USER_ROLE_MANAGER


@pytest.mark.parametrize(
    "attributes,expected_role",
    [
        ({"usertype": "admin"}, roles.USER_ROLE_ADMIN),
        ({"usertype": "manager"}, roles.USER_ROLE_MANAGER),
        ({"usertype": "reviewer"}, roles.USER_ROLE_REVIEWER),
        ({}, roles.USER_ROLE_READER),
    ],
    ids=["admin", "manager", "reviewer", "reader"],
)
def test_cas_user_role(
    settings: pytest_django.Settings, attributes: dict[str, str], expected_role: str
) -> None:
    """Unit test for _cas_user_role helper."""
    settings.CAS_CHECK_ADMIN_ATTRIBUTES = True
    settings.CAS_ADMIN_ATTRIBUTE = "usertype"
    settings.CAS_ADMIN_ATTRIBUTE_VALUE = "admin"
    settings.CAS_MANAGER_ATTRIBUTE = "usertype"
    settings.CAS_MANAGER_ATTRIBUTE_VALUE = "manager"
    settings.CAS_REVIEWER_ATTRIBUTE = "usertype"
    settings.CAS_REVIEWER_ATTRIBUTE_VALUE = "reviewer"

    assert _cas_user_role(attributes) == expected_role
