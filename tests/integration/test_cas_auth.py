import os
import re

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

if not django_settings.CAS_AUTHENTICATION:
    pytest.skip("Skipping CAS integration tests", allow_module_level=True)


def url_starting_with(prefix: str) -> re.Pattern[str]:
    return re.compile(f"^{re.escape(prefix)}")


def log_in_via_cas(
    page: Page, live_server: LiveServer, username: str, password: str = "test"
) -> None:
    page.goto(live_server.url)

    page.locator("#username").fill(username)
    page.locator("#password").fill(password)
    page.locator("button[name=submitBtn]").click()


def get_user_details(page: Page, live_server: LiveServer, user: User) -> list[str]:
    page.goto(
        f"{live_server.url}{reverse('administration:user_detail', args=[user.pk])}"
    )

    details_text = page.locator("dl").text_content()
    assert details_text is not None

    return [i.strip() for i in details_text.splitlines() if i.strip()]


@pytest.fixture
def check_role_attributes(settings: Settings) -> Settings:
    settings.CAS_CHECK_ADMIN_ATTRIBUTES = True
    settings.CAS_ADMIN_ATTRIBUTE = "memberOf"
    settings.CAS_ADMIN_ATTRIBUTE_VALUE = "administrators"
    settings.CAS_MANAGER_ATTRIBUTE = "memberOf"
    settings.CAS_MANAGER_ATTRIBUTE_VALUE = "managers"
    settings.CAS_REVIEWER_ATTRIBUTE = "memberOf"
    settings.CAS_REVIEWER_ATTRIBUTE_VALUE = "reviewers"

    return settings


@pytest.mark.django_db
def test_login_redirects_to_cas_server_login_page(
    page: Page, live_server: LiveServer, settings: Settings
) -> None:
    page.goto(live_server.url)

    expect(page).to_have_url(url_starting_with(f"{settings.CAS_SERVER_URL}login"))
    expect(page.locator("#username")).to_be_visible()


@pytest.mark.django_db
def test_cas_backend_creates_local_user(
    page: Page, live_server: LiveServer, django_user_model: type[User]
) -> None:
    log_in_via_cas(page, live_server, "demo")

    expect(page).to_have_url(f"{live_server.url}/")

    user = django_user_model.objects.get(username="demo")

    # The CAS server does not send a name or an email address, so the
    # corresponding definitions are rendered empty.
    assert get_user_details(page, live_server, user) == [
        "Username",
        "demo",
        "Name",
        "E-mail",
    ]
    assert roles.get_user_role(user) == roles.USER_ROLE_READER
    assert not user.is_superuser


@pytest.mark.django_db
def test_cas_backend_authenticates_existing_user(
    page: Page, live_server: LiveServer, django_user_model: type[User]
) -> None:
    user = django_user_model.objects.create(
        username="demo",
        email="demo@example.com",
        first_name="Demo",
        last_name="User",
    )

    log_in_via_cas(page, live_server, "demo")

    expect(page).to_have_url(f"{live_server.url}/")
    assert get_user_details(page, live_server, user) == [
        "Username",
        "demo",
        "Name",
        "Demo User",
        "E-mail",
        "demo@example.com",
    ]
    assert django_user_model.objects.filter(username="demo").count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize(
    "username,expected_role",
    [
        ("demo", roles.USER_ROLE_READER),
        ("reviewer", roles.USER_ROLE_REVIEWER),
        ("manager", roles.USER_ROLE_MANAGER),
        ("admin", roles.USER_ROLE_ADMIN),
    ],
)
def test_role_attributes_map_to_roles(
    page: Page,
    live_server: LiveServer,
    django_user_model: type[User],
    check_role_attributes: Settings,
    username: str,
    expected_role: str,
) -> None:
    # The manager user also belongs to the reviewers group, and the admin
    # user belongs to every group, so the highest role wins.
    log_in_via_cas(page, live_server, username)

    expect(page).to_have_url(f"{live_server.url}/")

    user = django_user_model.objects.get(username=username)

    assert roles.get_user_role(user) == expected_role
    assert user.is_superuser is (expected_role == roles.USER_ROLE_ADMIN)


@pytest.mark.django_db
def test_single_valued_role_attribute_grants_administrator_role(
    page: Page,
    live_server: LiveServer,
    django_user_model: type[User],
    check_role_attributes: Settings,
) -> None:
    # The sysadmin user is a member of a single CAS group, so the memberOf
    # attribute is handed over as a string instead of a list.
    log_in_via_cas(page, live_server, "sysadmin")

    expect(page).to_have_url(f"{live_server.url}/")

    user = django_user_model.objects.get(username="sysadmin")

    assert roles.get_user_role(user) == roles.USER_ROLE_ADMIN


@pytest.mark.django_db
def test_administrator_can_open_the_configuration_page(
    page: Page,
    live_server: LiveServer,
    django_user_model: type[User],
    check_role_attributes: Settings,
) -> None:
    log_in_via_cas(page, live_server, "admin")

    expect(page).to_have_url(f"{live_server.url}/")

    # The configuration page is only available to administrators; anyone
    # else gets a 403 at the same URL.
    response = page.goto(f"{live_server.url}{reverse('administration:configuration')}")

    assert response is not None
    assert response.status == 200
    expect(page.get_by_role("heading", name="Default Locations")).to_be_visible()


@pytest.mark.django_db
def test_role_change_applies_on_next_login(
    page: Page,
    live_server: LiveServer,
    django_user_model: type[User],
    check_role_attributes: Settings,
) -> None:
    django_user_model.objects.create(username="demo", is_superuser=True)

    # The demo user only belongs to the users group, so the administrator
    # role is taken away on this login.
    log_in_via_cas(page, live_server, "demo")

    expect(page).to_have_url(f"{live_server.url}/")

    user = django_user_model.objects.get(username="demo")

    assert roles.get_user_role(user) == roles.USER_ROLE_READER
    assert not user.is_superuser


@pytest.mark.django_db
def test_role_attributes_are_ignored_unless_the_check_is_on(
    page: Page, live_server: LiveServer, django_user_model: type[User]
) -> None:
    log_in_via_cas(page, live_server, "manager")

    expect(page).to_have_url(f"{live_server.url}/")

    user = django_user_model.objects.get(username="manager")

    # The receiver returns early, so the user gets the default role.
    assert roles.get_user_role(user) == roles.USER_ROLE_READER


@pytest.mark.django_db
def test_autoconfigure_email_sets_email_of_new_user(
    page: Page,
    live_server: LiveServer,
    django_user_model: type[User],
    settings: Settings,
) -> None:
    settings.CAS_AUTOCONFIGURE_EMAIL = True
    settings.CAS_EMAIL_DOMAIN = "example.com"

    log_in_via_cas(page, live_server, "demo")

    expect(page).to_have_url(f"{live_server.url}/")

    user = django_user_model.objects.get(username="demo")

    assert user.email == "demo@example.com"
    assert get_user_details(page, live_server, user) == [
        "Username",
        "demo",
        "Name",
        "E-mail",
        "demo@example.com",
    ]


@pytest.mark.django_db
def test_logging_out_logs_out_user_from_cas_server(
    page: Page, live_server: LiveServer, settings: Settings
) -> None:
    log_in_via_cas(page, live_server, "demo")

    expect(page).to_have_url(f"{live_server.url}/")

    # Logging out redirects the user to the CAS server logout page.
    page.get_by_role("button", name="Log out").click()
    expect(page).to_have_url(url_starting_with(f"{settings.CAS_SERVER_URL}logout"))

    # The CAS single sign-on session is over, so authenticating again
    # requires to submit the CAS login form.
    page.goto(live_server.url)
    expect(page).to_have_url(url_starting_with(f"{settings.CAS_SERVER_URL}login"))
    expect(page.locator("#username")).to_be_visible()
