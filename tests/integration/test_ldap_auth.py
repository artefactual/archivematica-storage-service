import os

import pytest
from django.conf import settings as django_settings
from django.contrib.auth.models import User
from django.urls import reverse
from playwright.sync_api import Page
from playwright.sync_api import expect
from pytest_django.live_server_helper import LiveServer

from archivematica.storage_service.administration import roles

if "RUN_INTEGRATION_TESTS" not in os.environ:
    pytest.skip("Skipping integration tests", allow_module_level=True)

if not django_settings.LDAP_AUTHENTICATION:
    pytest.skip("Skipping LDAP integration tests", allow_module_level=True)


def log_in_via_ldap(
    page: Page, live_server: LiveServer, username: str, password: str = "test"
) -> None:
    page.goto(live_server.url)

    page.get_by_label("Username").fill(username)
    page.get_by_label("Password").fill(password)
    page.get_by_text("Log in", exact=True).click()


def get_user_details(page: Page, live_server: LiveServer, user: User) -> list[str]:
    page.goto(
        f"{live_server.url}{reverse('administration:user_detail', args=[user.pk])}"
    )

    details_text = page.locator("dl").text_content()
    assert details_text is not None

    return [i.strip() for i in details_text.splitlines() if i.strip()]


@pytest.mark.django_db
def test_ldap_backend_creates_local_user_and_maps_profile_attributes(
    page: Page, live_server: LiveServer, django_user_model: type[User]
) -> None:
    log_in_via_ldap(page, live_server, "demo")

    expect(page).to_have_url(f"{live_server.url}/")

    user = django_user_model.objects.get(username="demo")

    assert get_user_details(page, live_server, user) == [
        "Username",
        "demo",
        "Name",
        "Demo User",
        "E-mail",
        "demo@example.com",
    ]
    assert user.is_active
    assert not user.is_staff
    assert not user.is_superuser
    assert roles.get_user_role(user) == roles.USER_ROLE_READER


@pytest.mark.django_db
def test_ldap_backend_updates_existing_user_attributes(
    page: Page, live_server: LiveServer, django_user_model: type[User]
) -> None:
    user = django_user_model.objects.create(
        username="manager",
        first_name="Outdated",
        last_name="Profile",
        email="old@example.com",
    )

    log_in_via_ldap(page, live_server, "manager")

    expect(page).to_have_url(f"{live_server.url}/")

    user.refresh_from_db()

    assert (user.first_name, user.last_name, user.email) == (
        "Manager",
        "User",
        "manager@example.com",
    )
    assert django_user_model.objects.filter(username="manager").count() == 1


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
def test_group_membership_maps_to_roles(
    page: Page,
    live_server: LiveServer,
    django_user_model: type[User],
    username: str,
    expected_role: str,
) -> None:
    # The manager user also belongs to the reviewers group, and the admin
    # user belongs to every group, so the highest role wins.
    log_in_via_ldap(page, live_server, username)

    expect(page).to_have_url(f"{live_server.url}/")

    user = django_user_model.objects.get(username=username)

    assert roles.get_user_role(user) == expected_role
    # The administrators group maps to both Django flags.
    assert user.is_superuser is (expected_role == roles.USER_ROLE_ADMIN)
    assert user.is_staff is (expected_role == roles.USER_ROLE_ADMIN)


@pytest.mark.django_db
def test_administrator_can_open_the_configuration_page(
    page: Page, live_server: LiveServer, django_user_model: type[User]
) -> None:
    log_in_via_ldap(page, live_server, "admin")

    expect(page).to_have_url(f"{live_server.url}/")

    # The configuration page is only available to administrators; anyone
    # else gets a 403 at the same URL.
    response = page.goto(f"{live_server.url}{reverse('administration:configuration')}")

    assert response is not None
    assert response.status == 200
    expect(page.get_by_role("heading", name="Default Locations")).to_be_visible()


@pytest.mark.django_db
def test_role_change_applies_on_next_login(
    page: Page, live_server: LiveServer, django_user_model: type[User]
) -> None:
    user = django_user_model.objects.create(username="reviewer")
    roles.set_user_role(user, roles.USER_ROLE_MANAGER)

    log_in_via_ldap(page, live_server, "reviewer")

    expect(page).to_have_url(f"{live_server.url}/")

    user = django_user_model.objects.get(username="reviewer")

    # The LDAP groups are read again on every login, so the manager role
    # given locally is replaced by the role of the reviewers group.
    assert roles.get_user_role(user) == roles.USER_ROLE_REVIEWER


@pytest.mark.django_db
@pytest.mark.parametrize("username", ["disabled", "outsider"])
def test_required_and_denied_groups_reject_login(
    page: Page,
    live_server: LiveServer,
    django_user_model: type[User],
    username: str,
) -> None:
    log_in_via_ldap(page, live_server, username)

    expect(page).to_have_url(f"{live_server.url}{reverse('login')}")
    expect(page.get_by_text("Your username and password didn't match")).to_be_visible()
    assert not django_user_model.objects.filter(username=username).exists()


@pytest.mark.django_db
def test_wrong_password_is_rejected(
    page: Page, live_server: LiveServer, django_user_model: type[User]
) -> None:
    log_in_via_ldap(page, live_server, "demo", "wrong-password")

    expect(page).to_have_url(f"{live_server.url}{reverse('login')}")
    expect(page.get_by_text("Your username and password didn't match")).to_be_visible()
    assert not django_user_model.objects.filter(username="demo").exists()


@pytest.mark.django_db
def test_logout_ends_local_ldap_session(page: Page, live_server: LiveServer) -> None:
    log_in_via_ldap(page, live_server, "demo")

    expect(page).to_have_url(f"{live_server.url}/")

    page.get_by_role("button", name="Log out").click()

    expect(page).to_have_url(f"{live_server.url}{reverse('login')}")

    # The local session is over, so the login form is served again.
    page.goto(live_server.url)

    expect(page).to_have_url(f"{live_server.url}{reverse('login')}?next=/")
