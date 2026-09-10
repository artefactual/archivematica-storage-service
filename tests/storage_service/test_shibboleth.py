import pytest
import pytest_django
from django.contrib.auth.models import User

from archivematica.storage_service.administration import roles
from archivematica.storage_service.common.backends import (
    CustomShibbolethRemoteUserBackend,
)
from archivematica.storage_service.common.middleware import (
    CustomShibbolethRemoteUserMiddleware,
)

TEST_SHIBBOLETH_USER = "demo@example.com"
TEST_SHIBBOLETH_ATTRIBUTES = {
    "first_name": "Demo",
    "last_name": "User",
    "email": "demo@example.com",
    "entitlement": "preservation-user",
}


@pytest.fixture
def settings(settings: pytest_django.Settings) -> pytest_django.Settings:
    settings.SHIBBOLETH_ADMIN_ENTITLEMENT = "preservation-admin"
    settings.SHIBBOLETH_MANAGER_ENTITLEMENT = "preservation-manager"
    settings.SHIBBOLETH_REVIEWER_ENTITLEMENT = "preservation-reviewer"

    return settings


def make_profile(user: User, entitlements: str) -> None:
    """Run the middleware hook that maps the entitlements to a role."""
    middleware = CustomShibbolethRemoteUserMiddleware(lambda request: None)

    middleware.make_profile(user, {"entitlement": entitlements})

    user.refresh_from_db()


@pytest.mark.django_db
def test_backend_creates_user_with_mapped_attributes() -> None:
    user = CustomShibbolethRemoteUserBackend().authenticate(
        None, remote_user=TEST_SHIBBOLETH_USER, shib_meta=TEST_SHIBBOLETH_ATTRIBUTES
    )

    assert user is not None
    assert user.username == TEST_SHIBBOLETH_USER
    assert (user.first_name, user.last_name, user.email) == (
        "Demo",
        "User",
        "demo@example.com",
    )
    assert not user.has_usable_password()


@pytest.mark.django_db
def test_backend_updates_existing_user_attributes() -> None:
    existing = User.objects.create(
        username=TEST_SHIBBOLETH_USER, first_name="Old", email="old@example.com"
    )

    user = CustomShibbolethRemoteUserBackend().authenticate(
        None, remote_user=TEST_SHIBBOLETH_USER, shib_meta=TEST_SHIBBOLETH_ATTRIBUTES
    )

    assert user is not None
    assert user.pk == existing.pk
    assert (user.first_name, user.email) == ("Demo", "demo@example.com")


@pytest.mark.django_db
def test_backend_rejects_inactive_user() -> None:
    User.objects.create(username=TEST_SHIBBOLETH_USER, is_active=False)

    assert (
        CustomShibbolethRemoteUserBackend().authenticate(
            None, remote_user=TEST_SHIBBOLETH_USER, shib_meta=TEST_SHIBBOLETH_ATTRIBUTES
        )
        is None
    )


@pytest.mark.django_db
def test_backend_accepts_login_without_user_field_attributes() -> None:
    # The identity provider releases no attribute that maps to a user field.
    user = CustomShibbolethRemoteUserBackend().authenticate(
        None,
        remote_user=TEST_SHIBBOLETH_USER,
        shib_meta={"entitlement": "preservation-user"},
    )

    assert user is not None
    assert user.username == TEST_SHIBBOLETH_USER


@pytest.mark.django_db
@pytest.mark.parametrize(
    "entitlements,expected_role",
    [
        ("preservation-admin", roles.USER_ROLE_ADMIN),
        # The entitlements are checked from the highest permission to the
        # lowest, so the highest entitlement wins.
        (
            "preservation-user;preservation-admin;preservation-manager",
            roles.USER_ROLE_ADMIN,
        ),
        ("preservation-manager;preservation-reviewer", roles.USER_ROLE_MANAGER),
        ("preservation-reviewer", roles.USER_ROLE_REVIEWER),
        ("preservation-user", roles.USER_ROLE_READER),
        # The entitlement is matched whole.
        ("preservation-administrator", roles.USER_ROLE_READER),
    ],
)
def test_middleware_maps_entitlements_to_roles(
    settings: pytest_django.Settings, entitlements: str, expected_role: str
) -> None:
    user = User.objects.create(username=TEST_SHIBBOLETH_USER)

    make_profile(user, entitlements)

    assert roles.get_user_role(user) == expected_role
    assert user.is_superuser is (expected_role == roles.USER_ROLE_ADMIN)


@pytest.mark.django_db
def test_middleware_demotes_a_former_administrator(
    settings: pytest_django.Settings,
) -> None:
    user = User.objects.create(username=TEST_SHIBBOLETH_USER, is_superuser=True)
    assert roles.get_user_role(user) == roles.USER_ROLE_ADMIN

    make_profile(user, "preservation-user")

    assert roles.get_user_role(user) == roles.USER_ROLE_READER
    assert not user.is_superuser


@pytest.mark.django_db
def test_middleware_promotes_a_reader_to_the_default_role(
    settings: pytest_django.Settings,
) -> None:
    settings.DEFAULT_USER_ROLE = "manager"
    user = User.objects.create(username=TEST_SHIBBOLETH_USER)

    make_profile(user, "preservation-user")

    assert roles.get_user_role(user) == roles.USER_ROLE_MANAGER
