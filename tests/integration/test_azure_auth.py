"""Integration tests for OpenID Connect authentication through Azure.

The Storage Service is configured with AZURE_TENANT_ID, which derives the
provider endpoints from https://login.microsoftonline.com. In the Compose
network that hostname is an alias of the entra-local service, an emulator of
Microsoft Entra ID that serves a self-signed certificate: the Storage Service
trusts it through REQUESTS_CA_BUNDLE and the browser is told to ignore HTTPS
errors.
"""

import os
import re
from urllib.parse import parse_qs
from urllib.parse import urlparse

import pytest
from django.conf import settings as django_settings
from django.contrib.auth.models import User
from django.urls import reverse
from playwright.sync_api import Page
from playwright.sync_api import expect
from pytest_django import Settings
from pytest_django.live_server_helper import LiveServer

from archivematica.storage_service.administration import roles

if "RUN_INTEGRATION_TESTS" not in os.environ:
    pytest.skip("Skipping integration tests", allow_module_level=True)

# The Azure settings only exist when OIDC authentication is enabled, so read
# the tenant with a default to skip this module under the other authentication
# configurations instead of failing their collection.
if not getattr(django_settings, "AZURE_TENANT_ID", ""):
    pytest.skip("Skipping Azure integration tests", allow_module_level=True)

# The emulator serves a self-signed certificate for login.microsoftonline.com.
pytestmark = pytest.mark.browser_context_args(ignore_https_errors=True)

AZURE_LOGIN_URL = f"https://login.microsoftonline.com/{django_settings.AZURE_TENANT_ID}"


def url_starting_with(prefix: str) -> re.Pattern[str]:
    return re.compile(f"^{re.escape(prefix)}")


def click_oidc_login_link(page: Page, live_server: LiveServer) -> None:
    page.goto(live_server.url)
    page.get_by_role("link", name="Log in with OpenID Connect").click()


def log_in_via_azure(
    page: Page, live_server: LiveServer, username: str, password: str
) -> None:
    click_oidc_login_link(page, live_server)

    expect(page).to_have_url(
        url_starting_with(f"{AZURE_LOGIN_URL}/oauth2/v2.0/authorize")
    )
    page.get_by_label("Username").fill(username)
    page.get_by_label("Password").fill(password)
    page.get_by_role("button", name="Sign in").click()


def get_user_details(page: Page, live_server: LiveServer, user: User) -> list[str]:
    page.goto(
        f"{live_server.url}{reverse('administration:user_detail', args=[user.pk])}"
    )

    details_text = page.locator("dl").text_content()
    assert details_text is not None

    return [i.strip() for i in details_text.splitlines() if i.strip()]


@pytest.mark.django_db
def test_login_link_redirects_to_azure_login_page(
    page: Page, live_server: LiveServer, settings: Settings
) -> None:
    # The tenant setting derives the endpoints of the Microsoft identity
    # platform, and the login link sends the browser to its authorization
    # endpoint, which shows the sign-in form.
    assert (
        settings.OIDC_OP_AUTHORIZATION_ENDPOINT
        == f"{AZURE_LOGIN_URL}/oauth2/v2.0/authorize"
    )
    assert settings.OIDC_OP_TOKEN_ENDPOINT == f"{AZURE_LOGIN_URL}/oauth2/v2.0/token"
    assert settings.OIDC_OP_JWKS_ENDPOINT == f"{AZURE_LOGIN_URL}/discovery/v2.0/keys"

    click_oidc_login_link(page, live_server)

    expect(page).to_have_url(url_starting_with(settings.OIDC_OP_AUTHORIZATION_ENDPOINT))
    expect(page.get_by_label("Username")).to_be_visible()
    expect(page.get_by_label("Password")).to_be_visible()

    # OIDC_RP_SCOPES is not exposed as a setting, so the request carries the
    # library default. The emulator configuration relies on it: without a
    # resource scope, Microsoft Entra ID issues the access token for Microsoft
    # Graph, whose v1.0 tokens carry the name claims that the backend maps
    # (see the entra-local services of the Compose file).
    query = parse_qs(urlparse(page.url).query)
    assert set(query["scope"][0].split()) == {"openid", "email"}


@pytest.mark.django_db
def test_oidc_backend_creates_local_user(
    page: Page, live_server: LiveServer, django_user_model: type[User]
) -> None:
    log_in_via_azure(page, live_server, "demo@example.com", "demo")

    expect(page).to_have_url(f"{live_server.url}/")

    # The email address of the ID token is the username and the names come
    # from the given_name and family_name claims of the access token.
    user = django_user_model.objects.get(username="demo@example.com")
    assert get_user_details(page, live_server, user) == [
        "Username",
        "demo@example.com",
        "Name",
        "Demo User",
        "E-mail",
        "demo@example.com",
    ]

    # The Azure configuration does not set roles from token claims, so new
    # users get the default role.
    assert roles.get_user_role(user) == roles.USER_ROLE_READER


@pytest.mark.django_db
def test_oidc_backend_authenticates_existing_user(
    page: Page, live_server: LiveServer, django_user_model: type[User]
) -> None:
    # Users are matched by email address, so a user created with a different
    # username is reused instead of duplicated.
    user = django_user_model.objects.create(
        username="demo",
        email="demo@example.com",
        first_name="Demo",
        last_name="User",
    )

    log_in_via_azure(page, live_server, "demo@example.com", "demo")

    expect(page).to_have_url(f"{live_server.url}/")
    assert get_user_details(page, live_server, user) == [
        "Username",
        "demo",
        "Name",
        "Demo User",
        "E-mail",
        "demo@example.com",
    ]

    assert django_user_model.objects.filter(email="demo@example.com").count() == 1


@pytest.mark.django_db
def test_azure_login_keeps_locally_assigned_role(
    page: Page, live_server: LiveServer, django_user_model: type[User]
) -> None:
    # The Azure configuration does not set roles from token claims, so the
    # role assigned locally survives the login.
    user = django_user_model.objects.create(
        username="demo@example.com", email="demo@example.com"
    )
    roles.set_user_role(user, roles.USER_ROLE_MANAGER)

    log_in_via_azure(page, live_server, "demo@example.com", "demo")

    expect(page).to_have_url(f"{live_server.url}/")

    user.refresh_from_db()
    assert roles.get_user_role(user) == roles.USER_ROLE_MANAGER


@pytest.mark.django_db
def test_logging_out_keeps_the_azure_session(
    page: Page, live_server: LiveServer, django_user_model: type[User]
) -> None:
    log_in_via_azure(page, live_server, "demo@example.com", "demo")

    expect(page).to_have_url(f"{live_server.url}/")

    # Logging out ends the local session and redirects to the login page.
    page.get_by_role("button", name="Log out").click()
    expect(page).to_have_url(f"{live_server.url}{reverse('login')}?next=/")

    # The Azure settings define no logout endpoint, so the session of the
    # identity provider is still active and logging in again requires no
    # credentials.
    page.get_by_role("link", name="Log in with OpenID Connect").click()

    expect(page).to_have_url(f"{live_server.url}/")
    assert django_user_model.objects.filter(username="demo@example.com").count() == 1
