import os
import re

import pytest
from django.conf import settings as django_settings
from django.contrib.auth.models import User
from django.urls import reverse
from playwright.sync_api import Browser
from playwright.sync_api import Page
from playwright.sync_api import expect
from pytest_django.live_server_helper import LiveServer
from tastypie.models import ApiKey

from archivematica.storage_service.administration import roles

if "RUN_INTEGRATION_TESTS" not in os.environ:
    pytest.skip("Skipping integration tests", allow_module_level=True)

if not django_settings.SHIBBOLETH_AUTHENTICATION:
    pytest.skip("Skipping Shibboleth integration tests", allow_module_level=True)

# The Storage Service does not speak SAML: it trusts the request headers that a
# Shibboleth service provider in front of it sets. Most tests below play the
# service provider themselves by sending those headers to the live server. The
# last section drives a real SAML login through the shibboleth-sp service,
# which authenticates against Keycloak and proxies to the live server.
SP_URL = os.environ.get("SHIBBOLETH_SP_URL", "http://shibboleth-sp:8000")

LOGOUT_TARGET = "/logged-out/"


def url_starting_with(prefix: str) -> re.Pattern[str]:
    return re.compile(f"^{re.escape(prefix)}")


def shibboleth_headers(
    username: str = "demo",
    first_name: str = "Demo",
    entitlements: str = "preservation-user",
) -> dict[str, str]:
    """Headers mod_shib exports after a login, for the attributes the Storage
    Service maps: eppn, givenName, sn, mail and entitlement."""
    return {
        "eppn": f"{username}@example.com",
        "givenName": first_name,
        "sn": "User",
        "mail": f"{username}@example.com",
        "entitlement": entitlements,
    }


def get_user_details(page: Page, base_url: str, user: User) -> list[str]:
    page.goto(f"{base_url}{reverse('administration:user_detail', args=[user.pk])}")

    details_text = page.locator("dl").text_content()
    assert details_text is not None

    return [item.strip() for item in details_text.splitlines() if item.strip()]


def logout_form_action(page: Page) -> str | None:
    return (
        page.get_by_role("button", name="Log out").locator("..").get_attribute("action")
    )


def log_in_via_keycloak(page: Page, username: str, password: str = "test") -> None:
    page.get_by_label("Username or email", exact=True).fill(username)
    page.get_by_label("Password", exact=True).fill(password)
    page.get_by_role("button", name="Sign In").click()
    # Keycloak posts the assertion to the service provider, which redirects
    # back into the application.
    expect(page).to_have_url(f"{SP_URL}/")


@pytest.fixture
def user(django_user_model: type[User]) -> User:
    user = django_user_model.objects.create(
        username="foobar",
        email="foobar@example.com",
        first_name="Foo",
        last_name="Bar",
    )
    user.set_password("foobar1A,")
    user.save()

    return user


@pytest.fixture
def user_apikey(user: User) -> ApiKey:
    return ApiKey.objects.create(user=user)


@pytest.mark.django_db
def test_headers_create_local_user_with_mapped_attributes(
    page: Page, live_server: LiveServer, django_user_model: type[User]
) -> None:
    page.set_extra_http_headers(shibboleth_headers())
    page.goto(live_server.url)

    expect(page).to_have_url(f"{live_server.url}/")

    user = django_user_model.objects.get(username="demo@example.com")

    assert get_user_details(page, live_server.url, user) == [
        "Username",
        "demo@example.com",
        "Name",
        "Demo User",
        "E-mail",
        "demo@example.com",
    ]
    assert not user.has_usable_password()
    assert roles.get_user_role(user) == roles.USER_ROLE_READER


@pytest.mark.django_db
def test_headers_update_an_existing_user(
    page: Page, live_server: LiveServer, django_user_model: type[User]
) -> None:
    existing = django_user_model.objects.create(
        username="demo@example.com", first_name="Old", email="old@example.com"
    )

    page.set_extra_http_headers(shibboleth_headers())
    page.goto(live_server.url)

    expect(page).to_have_url(f"{live_server.url}/")

    assert get_user_details(page, live_server.url, existing) == [
        "Username",
        "demo@example.com",
        "Name",
        "Demo User",
        "E-mail",
        "demo@example.com",
    ]
    assert django_user_model.objects.get(username="demo@example.com").pk == existing.pk


@pytest.mark.django_db
def test_headers_preserve_a_long_username(
    page: Page, live_server: LiveServer, django_user_model: type[User]
) -> None:
    # The username is the principal name as released, however long.
    long_email = "person-with-very-long-name@long-institution-name.ac.uk"
    headers = shibboleth_headers()
    headers["eppn"] = headers["mail"] = long_email
    page.set_extra_http_headers(headers)
    page.goto(live_server.url)

    expect(page).to_have_url(f"{live_server.url}/")

    user = django_user_model.objects.get(username=long_email)

    assert get_user_details(page, live_server.url, user)[:2] == [
        "Username",
        long_email,
    ]
    assert django_user_model.objects.filter(username=long_email).exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "entitlements,expected_role",
    [
        ("preservation-user", roles.USER_ROLE_READER),
        ("preservation-reviewer", roles.USER_ROLE_REVIEWER),
        ("preservation-manager;preservation-reviewer", roles.USER_ROLE_MANAGER),
        (
            "preservation-admin;preservation-manager;preservation-reviewer",
            roles.USER_ROLE_ADMIN,
        ),
    ],
)
def test_entitlements_map_to_roles(
    page: Page,
    live_server: LiveServer,
    django_user_model: type[User],
    entitlements: str,
    expected_role: str,
) -> None:
    # The entitlements are checked from the highest permission to the lowest,
    # so the highest entitlement wins.
    page.set_extra_http_headers(shibboleth_headers(entitlements=entitlements))
    page.goto(live_server.url)

    expect(page).to_have_url(f"{live_server.url}/")

    user = django_user_model.objects.get(username="demo@example.com")

    assert roles.get_user_role(user) == expected_role
    assert user.is_superuser is (expected_role == roles.USER_ROLE_ADMIN)


@pytest.mark.django_db
def test_entitlement_change_applies_on_next_login(
    browser: Browser, live_server: LiveServer, django_user_model: type[User]
) -> None:
    page = browser.new_page(
        extra_http_headers=shibboleth_headers(
            "admin",
            "Admin",
            "preservation-admin;preservation-manager;preservation-reviewer",
        )
    )
    page.goto(live_server.url)

    expect(page).to_have_url(f"{live_server.url}/")

    user = django_user_model.objects.get(username="admin@example.com")

    assert roles.get_user_role(user) == roles.USER_ROLE_ADMIN
    page.context.close()

    # The role is set on every authentication, so a new session without the
    # entitlement takes it away.
    page = browser.new_page(
        extra_http_headers=shibboleth_headers("admin", "Admin", "preservation-user")
    )
    page.goto(live_server.url)

    expect(page).to_have_url(f"{live_server.url}/")

    user = django_user_model.objects.get(username="admin@example.com")

    assert roles.get_user_role(user) == roles.USER_ROLE_READER
    assert not user.is_superuser
    page.context.close()


@pytest.mark.django_db
def test_attributes_are_only_read_when_a_session_is_established(
    browser: Browser, live_server: LiveServer, django_user_model: type[User]
) -> None:
    """Documents the library behaviour: once the user is logged in, changed
    headers are ignored until the user authenticates again."""
    page = browser.new_page(extra_http_headers=shibboleth_headers())
    page.goto(live_server.url)

    expect(page).to_have_url(f"{live_server.url}/")

    user = django_user_model.objects.get(username="demo@example.com")

    page.set_extra_http_headers(shibboleth_headers(first_name="Renamed"))

    assert "Demo User" in get_user_details(page, live_server.url, user)
    page.context.close()

    page = browser.new_page(extra_http_headers=shibboleth_headers(first_name="Renamed"))

    assert "Renamed User" in get_user_details(page, live_server.url, user)
    page.context.close()


@pytest.mark.django_db
def test_session_survives_requests_without_headers(
    page: Page, live_server: LiveServer
) -> None:
    """Documents the library behaviour: the local session is not ended when a
    request arrives without the remote user header."""
    page.set_extra_http_headers(shibboleth_headers())
    page.goto(live_server.url)
    page.set_extra_http_headers({})
    page.goto(f"{live_server.url}/")

    expect(page).to_have_url(f"{live_server.url}/")
    expect(page.get_by_role("button", name="Log out")).to_be_visible()


@pytest.mark.django_db
def test_missing_entitlement_attribute_is_rejected(
    page: Page, live_server: LiveServer, django_user_model: type[User]
) -> None:
    headers = shibboleth_headers()
    del headers["entitlement"]
    page.set_extra_http_headers(headers)

    response = page.goto(live_server.url)

    assert response is not None
    assert response.status == 500
    assert not django_user_model.objects.filter(username="demo@example.com").exists()


@pytest.mark.django_db
def test_login_with_only_eppn_and_entitlement(
    page: Page, live_server: LiveServer, django_user_model: type[User]
) -> None:
    page.set_extra_http_headers(
        {"eppn": "demo@example.com", "entitlement": "preservation-user"}
    )
    page.goto(live_server.url)

    expect(page).to_have_url(f"{live_server.url}/")

    user = django_user_model.objects.get(username="demo@example.com")

    assert get_user_details(page, live_server.url, user)[:2] == [
        "Username",
        "demo@example.com",
    ]


@pytest.mark.django_db
def test_without_headers_the_local_login_still_works(
    page: Page, live_server: LiveServer, user: User
) -> None:
    page.goto(live_server.url)

    expect(page).to_have_url(url_starting_with(f"{live_server.url}{reverse('login')}"))

    page.get_by_label("Username").fill(user.username)
    page.get_by_label("Password").fill("foobar1A,")
    page.get_by_text("Log in", exact=True).click()

    expect(page).to_have_url(f"{live_server.url}/")


@pytest.mark.django_db
def test_inactive_user_is_not_logged_in(
    page: Page, live_server: LiveServer, django_user_model: type[User]
) -> None:
    django_user_model.objects.create(username="demo@example.com", is_active=False)

    page.set_extra_http_headers(shibboleth_headers())
    page.goto(live_server.url)

    expect(page).to_have_url(url_starting_with(f"{live_server.url}{reverse('login')}"))


@pytest.mark.django_db
def test_logout_link_points_at_the_shibboleth_logout_view(
    page: Page, live_server: LiveServer
) -> None:
    page.set_extra_http_headers(shibboleth_headers())
    page.goto(live_server.url)

    assert (
        logout_form_action(page)
        == f"{reverse('shibboleth:logout')}?target={LOGOUT_TARGET}"
    )


@pytest.mark.django_db
def test_logout_ends_the_local_session_and_redirects_to_the_service_provider(
    page: Page, live_server: LiveServer
) -> None:
    page.set_extra_http_headers(shibboleth_headers())
    page.goto(live_server.url)

    # What the library's logout view implements: a GET. The redirect target
    # is served by the service provider, which then drops its own session, so
    # it is not followed here.
    response = page.request.get(
        f"{live_server.url}{reverse('shibboleth:logout')}?target={LOGOUT_TARGET}",
        headers=shibboleth_headers(),
        max_redirects=0,
    )

    assert response.status == 302
    assert (
        response.headers["location"] == f"/Shibboleth.sso/Logout?return={LOGOUT_TARGET}"
    )

    page.set_extra_http_headers({})
    page.goto(f"{live_server.url}/")

    expect(page).to_have_url(url_starting_with(f"{live_server.url}{reverse('login')}"))


@pytest.mark.django_db
def test_logout_button_logs_out(page: Page, live_server: LiveServer) -> None:
    page.set_extra_http_headers(shibboleth_headers())
    page.goto(live_server.url)

    with page.expect_response(
        lambda response: (
            response.request.method == "POST"
            and reverse("shibboleth:logout") in response.url
        )
    ) as logout:
        page.get_by_role("button", name="Log out").click()

    assert logout.value.status == 302
    expect(page).to_have_url(
        f"{live_server.url}/Shibboleth.sso/Logout?return={LOGOUT_TARGET}"
    )


@pytest.mark.django_db
def test_login_view_redirects_to_the_login_page(
    page: Page, live_server: LiveServer
) -> None:
    login_view = f"{live_server.url}{reverse('shibboleth:login')}?target=/"

    # Anonymous requests never reach the library's view: the Storage Service's
    # login-required middleware sends them to the login page first.
    page.goto(login_view)

    expect(page).to_have_url(url_starting_with(f"{live_server.url}{reverse('login')}"))

    # Behind a service provider the request is authenticated, and the view
    # forwards the target to the login page.
    page.set_extra_http_headers(shibboleth_headers())
    page.goto(login_view)

    expect(page).to_have_url(f"{live_server.url}{reverse('login')}?target=/")


@pytest.mark.django_db
def test_logged_out_page_offers_to_log_in_again(
    page: Page, live_server: LiveServer
) -> None:
    response = page.goto(f"{live_server.url}{LOGOUT_TARGET}")

    assert response is not None
    assert response.status == 200
    expect(page.get_by_text("You are logged out.")).to_be_visible()

    page.get_by_role("link", name="Log in again").click()

    expect(page).to_have_url(url_starting_with(f"{live_server.url}{reverse('login')}"))

    # With the attribute headers present the same link logs the user back in
    # and lands in the application.
    page.set_extra_http_headers(shibboleth_headers())
    page.goto(f"{live_server.url}{LOGOUT_TARGET}")

    page.get_by_role("link", name="Log in again").click()

    expect(page).to_have_url(f"{live_server.url}/")


@pytest.mark.django_db
def test_info_page_lists_the_mapped_attributes(
    page: Page, live_server: LiveServer
) -> None:
    page.set_extra_http_headers(shibboleth_headers())
    page.goto(f"{live_server.url}{reverse('shibboleth:info')}")

    text = page.locator("body").text_content() or ""
    for item in (
        "username: demo@example.com",
        "name: Demo User",
        "email: demo@example.com",
    ):
        assert item in text


@pytest.mark.django_db
def test_user_editing_is_disabled(
    page: Page, live_server: LiveServer, django_user_model: type[User]
) -> None:
    page.set_extra_http_headers(
        shibboleth_headers(
            "admin",
            "Admin",
            "preservation-admin;preservation-manager;preservation-reviewer",
        )
    )
    page.goto(live_server.url)

    expect(page).to_have_url(f"{live_server.url}/")

    user = django_user_model.objects.get(username="admin@example.com")

    # The identity provider owns the user details, so ALLOW_USER_EDITS is off.
    page.goto(
        f"{live_server.url}{reverse('administration:user_detail', args=[user.pk])}"
    )

    expect(page.get_by_role("link", name="Edit")).to_have_count(0)

    page.goto(f"{live_server.url}{reverse('administration:user_list')}")

    expect(page.get_by_role("link", name="Create New User")).to_have_count(0)


@pytest.mark.django_db
def test_api_accepts_api_keys_without_a_session(
    browser: Browser, live_server: LiveServer, user: User, user_apikey: ApiKey
) -> None:
    context = browser.new_context()

    response = context.request.get(
        f"{live_server.url}/api/v2/location/",
        headers={"Authorization": f"ApiKey {user.username}:{user_apikey.key}"},
    )
    assert response.status == 200

    # Without a key or a session the application, not the service provider,
    # answers.
    assert context.request.get(f"{live_server.url}/api/v2/location/").status == 401
    context.close()


# Through the service provider.


@pytest.mark.django_db
def test_saml_login_through_the_service_provider(
    page: Page, live_server: LiveServer, django_user_model: type[User]
) -> None:
    page.goto(SP_URL)

    expect(page).to_have_url(
        url_starting_with("http://keycloak:8080/realms/shibboleth/")
    )

    log_in_via_keycloak(page, "demo")

    user = django_user_model.objects.get(username="demo@example.com")

    assert get_user_details(page, SP_URL, user) == [
        "Username",
        "demo@example.com",
        "Name",
        "Demo User",
        "E-mail",
        "demo@example.com",
    ]
    assert not user.has_usable_password()
    assert roles.get_user_role(user) == roles.USER_ROLE_READER

    page.goto(f"{SP_URL}/Shibboleth.sso/Session")
    session = page.locator("body").text_content() or ""
    for attribute in (
        "eppn: demo@example.com",
        "entitlement: preservation-user",
        "givenName: Demo",
        "sn: User",
        "mail: demo@example.com",
    ):
        assert attribute in session


@pytest.mark.django_db
@pytest.mark.parametrize(
    "username,expected_role",
    [
        ("reviewer", roles.USER_ROLE_REVIEWER),
        ("manager", roles.USER_ROLE_MANAGER),
        ("admin", roles.USER_ROLE_ADMIN),
    ],
)
def test_saml_entitlements_map_to_roles(
    page: Page,
    live_server: LiveServer,
    django_user_model: type[User],
    username: str,
    expected_role: str,
) -> None:
    page.goto(SP_URL)
    log_in_via_keycloak(page, username)

    user = django_user_model.objects.get(username=f"{username}@example.com")

    assert roles.get_user_role(user) == expected_role

    if expected_role == roles.USER_ROLE_ADMIN:
        # The configuration page is only available to administrators; anyone
        # else gets a 403 at the same URL.
        response = page.goto(f"{SP_URL}{reverse('administration:configuration')}")

        assert response is not None
        assert response.status == 200
        expect(page.get_by_role("heading", name="Default Locations")).to_be_visible()


@pytest.mark.django_db
def test_saml_logout_ends_the_service_provider_session(
    page: Page, live_server: LiveServer
) -> None:
    page.goto(SP_URL)
    log_in_via_keycloak(page, "demo")

    page.get_by_role("button", name="Log out").click()

    # The application logs out and sends the browser to the service
    # provider's logout handler, which ends its session and returns to the
    # logged-out page.
    expect(page).to_have_url(f"{SP_URL}{LOGOUT_TARGET}")
    expect(page.get_by_text("You are logged out.")).to_be_visible()
    expect(page.get_by_role("link", name="Log in again")).to_be_visible()

    page.goto(f"{SP_URL}/Shibboleth.sso/Session")

    assert "A valid session was not found" in (
        page.locator("body").text_content() or ""
    )

    # The link re-establishes the service provider session through Keycloak's
    # surviving session and ends in the application.
    page.goto(f"{SP_URL}{LOGOUT_TARGET}")

    page.get_by_role("link", name="Log in again").click()

    expect(page).to_have_url(f"{SP_URL}/")

    page.goto(f"{SP_URL}/Shibboleth.sso/Session")

    assert "eppn: demo@example.com" in (page.locator("body").text_content() or "")


@pytest.mark.django_db
def test_logged_out_page_and_its_assets_need_no_session(
    browser: Browser, live_server: LiveServer
) -> None:
    context = browser.new_context()

    response = context.request.get(f"{SP_URL}{LOGOUT_TARGET}", max_redirects=0)

    assert response.status == 200
    assert "You are logged out." in response.text()

    # The page's stylesheets and JavaScript catalog must be served too, not
    # turned into a login.
    stylesheet = re.search(r'href="(/static/[^"]+\.css)"', response.text())
    assert stylesheet is not None

    for path, content_type in (
        (stylesheet.group(1), "text/css"),
        ("/jsi18n/", "text/javascript"),
    ):
        response = context.request.get(f"{SP_URL}{path}", max_redirects=0)

        assert response.status == 200, path
        assert response.headers["content-type"].startswith(content_type), path
    context.close()


@pytest.mark.django_db
def test_service_provider_rejects_spoofed_attribute_headers(
    browser: Browser, live_server: LiveServer, django_user_model: type[User]
) -> None:
    context = browser.new_context()
    spoofed = {"eppn": "attacker@example.com", "entitlement": "preservation-admin"}

    response = context.request.get(f"{SP_URL}/api/v2/location/", headers=spoofed)
    assert response.status == 500

    response = context.request.get(f"{SP_URL}/", headers=spoofed, max_redirects=0)
    assert response.status == 500

    assert not django_user_model.objects.filter(
        username="attacker@example.com"
    ).exists()
    context.close()


@pytest.mark.django_db
def test_service_provider_lets_api_key_requests_through(
    browser: Browser, live_server: LiveServer, user: User, user_apikey: ApiKey
) -> None:
    context = browser.new_context()

    response = context.request.get(
        f"{SP_URL}/api/v2/location/",
        headers={"Authorization": f"ApiKey {user.username}:{user_apikey.key}"},
    )
    assert response.status == 200

    # Without a key or a session the application, not the service provider,
    # answers.
    assert context.request.get(f"{SP_URL}/api/v2/location/").status == 401
    context.close()
