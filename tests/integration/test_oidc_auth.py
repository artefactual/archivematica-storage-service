import os
from typing import Generator
from typing import Type

import pytest
from django.contrib.auth.models import Group
from django.contrib.auth.models import User
from django.urls import reverse
from playwright.sync_api import Page
from pytest_django.fixtures import SettingsWrapper
from pytest_django.live_server_helper import LiveServer
from pytest_django.plugin import DjangoDbBlocker

if "RUN_INTEGRATION_TESTS" not in os.environ:
    pytest.skip("Skipping integration tests", allow_module_level=True)


@pytest.fixture(scope="module", autouse=True)
def recreate_user_groups(
    django_db_setup: None, django_db_blocker: DjangoDbBlocker
) -> Generator[None, None, None]:
    """Recreate user groups added during the 0030_user_groups migration.

    This ensures that tests dependent on these user groups can execute
    correctly after transactional rollbacks executed by the live_server
    fixture which do not restore migration data.
    """
    yield

    with django_db_blocker.unblock():
        Group.objects.get_or_create(name="Managers")
        Group.objects.get_or_create(name="Reviewers")


@pytest.fixture
def user(django_user_model: Type[User]) -> User:
    user = django_user_model.objects.create(
        username="foobar",
        email="foobar@example.com",
        first_name="Foo",
        last_name="Bar",
    )
    user.set_password("foobar1A,")
    user.save()

    return user


@pytest.mark.django_db
def test_oidc_backend_creates_local_user(
    page: Page,
    live_server: LiveServer,
    django_user_model: Type[User],
) -> None:
    page.goto(live_server.url)

    page.get_by_role("link", name="Log in with OpenID Connect").click()
    page.get_by_label("Username or email").fill("demo@example.com")
    page.get_by_label("Password", exact=True).fill("demo")
    page.get_by_role("button", name="Sign In").click()

    assert page.url == f"{live_server.url}/"

    user = django_user_model.objects.get(
        username="demo@example.com", first_name="Demo", last_name="User"
    )

    page.get_by_role("link", name="Administration").click()
    page.get_by_role("link", name="View").click()

    assert (
        page.url
        == f"{live_server.url}{reverse('administration:user_detail', args=[user.pk])}"
    )
    assert [
        i.strip() for i in page.locator("dl").text_content().splitlines() if i.strip()
    ] == [
        "Username",
        "demo@example.com",
        "Name",
        "Demo User",
        "E-mail",
        "demo@example.com",
    ]


@pytest.mark.django_db
def test_local_authentication_backend_authenticates_existing_user(
    page: Page, live_server: LiveServer, user: User
) -> None:
    page.goto(live_server.url)

    page.get_by_label("Username").fill("foobar")
    page.get_by_label("Password").fill("foobar1A,")
    page.get_by_text("Log in", exact=True).click()

    assert page.url == f"{live_server.url}/"

    page.get_by_role("link", name="Administration").click()
    page.get_by_role("link", name="View").click()

    assert (
        page.url
        == f"{live_server.url}{reverse('administration:user_detail', args=[user.pk])}"
    )
    assert [
        i.strip() for i in page.locator("dl").text_content().splitlines() if i.strip()
    ] == [
        "Username",
        "foobar",
        "Name",
        "Foo Bar",
        "E-mail",
        "foobar@example.com",
    ]


@pytest.mark.django_db
def test_removing_model_authentication_backend_disables_local_authentication(
    page: Page,
    live_server: LiveServer,
    user: User,
    settings: SettingsWrapper,
) -> None:
    disabled_backends = ["django.contrib.auth.backends.ModelBackend"]
    settings.AUTHENTICATION_BACKENDS = [
        b for b in settings.AUTHENTICATION_BACKENDS if b not in disabled_backends
    ]

    page.goto(live_server.url)

    page.get_by_label("Username").fill("foobar")
    page.get_by_label("Password").fill("foobar1A,")
    page.get_by_text("Log in", exact=True).click()

    assert page.url == f"{live_server.url}{settings.LOGIN_URL}"
    assert (
        "Your username and password didn't match."
        in page.locator("p").text_content().strip()
    )


@pytest.mark.django_db
def test_setting_login_url_redirects_to_oidc_login_page(
    page: Page,
    live_server: LiveServer,
    user: User,
    settings: SettingsWrapper,
) -> None:
    page.goto(live_server.url)
    assert page.url == f"{live_server.url}{reverse('login')}?next=/"

    settings.LOGIN_URL = reverse("oidc_authentication_init")

    page.goto(live_server.url)

    assert page.url.startswith(settings.OIDC_OP_AUTHORIZATION_ENDPOINT)
