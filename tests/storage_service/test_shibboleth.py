import pytest
import pytest_django
from django.conf import settings
from django.contrib.auth.models import User
from django.test import Client

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.skipif(
        not settings.SHIBBOLETH_AUTHENTICATION,
        reason="tests will only pass if Shibboleth is enabled",
    ),
]


@pytest.fixture(autouse=True)
def static_files_storage(settings: pytest_django.Settings) -> None:
    settings.STATICFILES_STORAGE = None


def test_with_no_shibboleth_headers(client: Client) -> None:
    response = client.get("/")

    # If no shibboleth headers, no user is created - so installer middleware
    # kicks in and redirects to welcome page
    assert response.status_code == 302
    assert settings.LOGIN_URL in response["Location"]


def test_auto_creates_user(client: Client) -> None:
    shib_headers = {
        "EPPN": "testuser",
        "GIVENNAME": "Test",
        "SN": "User",
        "MAIL": "test@example.com",
        "ENTITLEMENT": "preservation-user",
    }

    response = client.get("/", headers=shib_headers)

    assert response.status_code == 200
    user = response.context["user"]
    assert user.username == "testuser"
    assert user.get_full_name() == "Test User"
    assert user.email == "test@example.com"
    assert not user.has_usable_password()
    assert not user.is_superuser


def test_uses_existing_user(client: Client) -> None:
    user = User.objects.create(username="testuser")
    shib_headers = {
        "EPPN": "testuser",
        "GIVENNAME": "Test",
        "SN": "User",
        "MAIL": "test@example.com",
        "ENTITLEMENT": "preservation-user",
    }

    response = client.get("/", headers=shib_headers)

    assert response.status_code == 200
    assert response.context["user"] == user


def test_long_username(client: Client) -> None:
    long_email = "person-with-very-long-name@long-institution-name.ac.uk"
    shib_headers = {
        "EPPN": long_email,
        "GIVENNAME": "Test",
        "SN": "User",
        "MAIL": "test@example.com",
        "ENTITLEMENT": "preservation-user",
    }

    response = client.get("/", headers=shib_headers)

    assert response.status_code == 200
    assert response.context["user"].username == long_email


def test_creates_superuser_based_on_entitlement(client: Client) -> None:
    shib_headers = {
        "EPPN": "testuser",
        "GIVENNAME": "Test",
        "SN": "User",
        "MAIL": "test@example.com",
        "ENTITLEMENT": "preservation-admin;some-other-entitlement",
    }

    response = client.get("/", headers=shib_headers)

    assert response.status_code == 200
    assert response.context["user"].is_superuser
