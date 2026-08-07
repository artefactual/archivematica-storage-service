import pytest
import pytest_django
from django.contrib.auth.models import User

from archivematica.storage_service.administration import roles
from archivematica.storage_service.common.backends import CustomOIDCBackend


@pytest.fixture
def settings(settings: pytest_django.Settings) -> pytest_django.Settings:
    settings.DEFAULT_OIDC_CLAIMS = {
        "given_name": "first_name",
        "family_name": "last_name",
    }
    settings.OIDC_OP_TOKEN_ENDPOINT = "https://example.com/token"
    settings.OIDC_OP_USER_ENDPOINT = "https://example.com/user"
    settings.OIDC_RP_CLIENT_ID = "rp_client_id"
    settings.OIDC_RP_CLIENT_SECRET = "rp_client_secret"
    settings.OIDC_ACCESS_ATTRIBUTE_MAP = {
        "given_name": "first_name",
        "family_name": "last_name",
    }
    settings.OIDC_OP_SET_ROLES_FROM_CLAIMS = False
    settings.OIDC_CREATE_USER = True
    settings.OIDC_OP_ROLE_CLAIM_PATH = "realm_access.roles"
    settings.OIDC_ID_ATTRIBUTE_MAP = {"email": "email"}
    settings.OIDC_USERNAME_ALGO = lambda email: email

    return settings


@pytest.mark.django_db
def test_create_user_set_roles_from_default_role(
    settings: pytest_django.Settings,
) -> None:
    backend = CustomOIDCBackend()

    user = backend.create_user(
        {"email": "test@example.com", "first_name": "Test", "last_name": "User"}
    )
    assert user is not None

    user.refresh_from_db()
    assert user.first_name == "Test"
    assert user.last_name == "User"
    assert user.email == "test@example.com"
    assert user.username == "test@example.com"
    assert roles.role_user(user).get_role() == roles.USER_ROLE_READER


@pytest.mark.django_db
def test_create_user_set_role_from_claim(settings: pytest_django.Settings) -> None:
    settings.OIDC_OP_SET_ROLES_FROM_CLAIMS = True
    settings.OIDC_OP_ROLE_CLAIM_PATH = "realm_access.roles"
    settings.OIDC_ACCESS_ATTRIBUTE_MAP = {
        "given_name": "first_name",
        "family_name": "last_name",
        "realm_access": "realm_access",
    }
    backend = CustomOIDCBackend()

    user = backend.create_user(
        {
            "email": "test@example.com",
            "first_name": "Test",
            "last_name": "User",
            "realm_access": {"roles": ["manager"]},
        }
    )
    assert user is not None

    user.refresh_from_db()
    assert user.first_name == "Test"
    assert user.last_name == "User"
    assert user.email == "test@example.com"
    assert user.username == "test@example.com"
    assert roles.role_user(user).get_role() == roles.USER_ROLE_MANAGER


@pytest.mark.django_db
def test_create_user_role_from_claims(settings: pytest_django.Settings) -> None:
    """
    The role given to a new user is based on token contents.

    In this test, we're ensuring that the highest-permission valid role
    found in the OIDC token claims is assigned.
    """
    settings.OIDC_OP_SET_ROLES_FROM_CLAIMS = True
    settings.OIDC_OP_ROLE_CLAIM_PATH = "realm_access.roles"
    settings.OIDC_ACCESS_ATTRIBUTE_MAP = {
        "given_name": "first_name",
        "family_name": "last_name",
        "realm_access": "realm_access",
    }
    backend = CustomOIDCBackend()

    user = backend.create_user(
        {
            "email": "test@example.com",
            "first_name": "Test",
            "last_name": "User",
            "realm_access": {"roles": ["admin", "editor"]},
        }
    )
    assert user is not None

    user.refresh_from_db()
    assert user.first_name == "Test"
    assert user.last_name == "User"
    assert user.email == "test@example.com"
    assert user.username == "test@example.com"
    assert roles.role_user(user).get_role() == roles.USER_ROLE_ADMIN


@pytest.mark.django_db
def test_create_user_role_from_claims_reverese_token_role_order(
    settings: pytest_django.Settings,
) -> None:
    """
    The role given to a new user is based on token contents.

    In this test, we're ensuring that the highest-permission valid role
    found in the OIDC token claims is assigned.
    """
    settings.OIDC_OP_SET_ROLES_FROM_CLAIMS = True
    settings.OIDC_OP_ROLE_CLAIM_PATH = "realm_access.roles"
    settings.OIDC_ACCESS_ATTRIBUTE_MAP = {
        "given_name": "first_name",
        "family_name": "last_name",
        "realm_access": "realm_access",
    }
    backend = CustomOIDCBackend()

    user = backend.create_user(
        {
            "email": "test@example.com",
            "first_name": "Test",
            "last_name": "User",
            "realm_access": {"roles": ["editor", "admin"]},
        }
    )
    assert user is not None

    user.refresh_from_db()
    assert user.first_name == "Test"
    assert user.last_name == "User"
    assert user.email == "test@example.com"
    assert user.username == "test@example.com"
    assert roles.role_user(user).get_role() == roles.USER_ROLE_ADMIN


@pytest.mark.django_db
def test_create_user_role_from_claims_alt_path(
    settings: pytest_django.Settings,
) -> None:
    settings.OIDC_OP_SET_ROLES_FROM_CLAIMS = True
    settings.OIDC_OP_ROLE_CLAIM_PATH = "custom_claims.user_roles"
    settings.OIDC_ACCESS_ATTRIBUTE_MAP = {
        "given_name": "first_name",
        "family_name": "last_name",
        "realm_access": "realm_access",
    }
    backend = CustomOIDCBackend()

    user = backend.create_user(
        {
            "email": "test@example.com",
            "first_name": "Test",
            "last_name": "User",
            "custom_claims": {"user_roles": ["admin"]},
        }
    )
    assert user is not None

    user.refresh_from_db()
    assert user.first_name == "Test"
    assert user.last_name == "User"
    assert user.email == "test@example.com"
    assert user.username == "test@example.com"
    assert roles.role_user(user).get_role() == roles.USER_ROLE_ADMIN


@pytest.mark.django_db
def test_create_user_role_from_claims_simple_role(
    settings: pytest_django.Settings,
) -> None:
    settings.OIDC_OP_SET_ROLES_FROM_CLAIMS = True
    settings.OIDC_OP_ROLE_CLAIM_PATH = "role"
    settings.OIDC_ACCESS_ATTRIBUTE_MAP = {
        "given_name": "first_name",
        "family_name": "last_name",
        "realm_access": "realm_access",
    }
    backend = CustomOIDCBackend()

    user = backend.create_user(
        {
            "email": "test@example.com",
            "first_name": "Test",
            "last_name": "User",
            "role": "admin",
        }
    )
    assert user is not None

    user.refresh_from_db()
    assert user.first_name == "Test"
    assert user.last_name == "User"
    assert user.email == "test@example.com"
    assert user.username == "test@example.com"
    assert roles.role_user(user).get_role() == roles.USER_ROLE_ADMIN


@pytest.mark.django_db
def test_create_user_set_admin_from_alternate_token_value(
    settings: pytest_django.Settings,
) -> None:
    settings.OIDC_OP_SET_ROLES_FROM_CLAIMS = True
    settings.OIDC_OP_ROLE_CLAIM_PATH = "realm_access.roles"
    settings.OIDC_ACCESS_ATTRIBUTE_MAP = {
        "given_name": "first_name",
        "family_name": "last_name",
        "realm_access": "realm_access",
    }
    settings.OIDC_ROLE_CLAIM_ADMIN = "test"
    backend = CustomOIDCBackend()

    user = backend.create_user(
        {
            "email": "test@example.com",
            "first_name": "Test",
            "last_name": "User",
            "realm_access": {"roles": ["test"]},
        }
    )
    assert user is not None

    user.refresh_from_db()
    assert user.first_name == "Test"
    assert user.last_name == "User"
    assert user.email == "test@example.com"
    assert user.username == "test@example.com"
    assert roles.role_user(user).get_role() == roles.USER_ROLE_ADMIN


@pytest.mark.django_db
def test_create_user_failure_no_claims_in_token(
    settings: pytest_django.Settings,
) -> None:
    settings.OIDC_OP_SET_ROLES_FROM_CLAIMS = True
    settings.OIDC_OP_ROLE_CLAIM_PATH = "realm_access.roles"
    settings.OIDC_ACCESS_ATTRIBUTE_MAP = {
        "given_name": "first_name",
        "family_name": "last_name",
        "realm_access": "realm_access",
    }
    backend = CustomOIDCBackend()

    user = backend.create_user(
        {"email": "test@example.com", "first_name": "Test", "last_name": "User"}
    )

    assert user is None


@pytest.mark.django_db
def test_create_demoted_user(settings: pytest_django.Settings) -> None:
    """
    The role given to a new user is based on ``DEFAULT_USER_ROLE``.

    In this test, we're ensuring that new users are given the reviewer role
    instead of the default "manager" role.
    """
    settings.DEFAULT_USER_ROLE = roles.USER_ROLE_REVIEWER
    backend = CustomOIDCBackend()

    user = backend.create_user(
        {"email": "test@example.com", "first_name": "Test", "last_name": "User"}
    )
    assert user is not None

    user.refresh_from_db()
    assert roles.role_user(user).get_role() == roles.USER_ROLE_REVIEWER


@pytest.mark.django_db
def test_get_userinfo(settings: pytest_django.Settings) -> None:
    # Encoded at https://www.jsonwebtoken.io/
    # {"email": "test@example.com"}
    id_token = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJlbWFpbCI6InRlc3RAZXhhbXBsZS5jb20iLCJqdGkiOiI1M2QyMzUzMy04NDk0LTQyZWQtYTJiZC03Mzc2MjNmMjUzZjciLCJpYXQiOjE1NzMwMzE4NDQsImV4cCI6MTU3MzAzNTQ0NH0.m3nHgvj_DyVJMcW5eyYuUss1Y0PNzJV2O3bX0b_DCmI"
    # {"given_name": "Test", "family_name": "User"}
    access_token = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJnaXZlbl9uYW1lIjoiVGVzdCIsImZhbWlseV9uYW1lIjoiVXNlciIsImp0aSI6ImRhZjIwNTNiLWE4MTgtNDE1Yy1hM2Y1LTkxYWVhMTMxYjljZCIsImlhdCI6MTU3MzAzMTk3OSwiZXhwIjoxNTczMDM1NTc5fQ.cGcmt7d9IuKndvrqPpAH3Dvb3KyCOMqixUWgS7sg8r4"
    backend = CustomOIDCBackend()

    info = backend.get_userinfo(access_token, id_token, {})

    assert info["email"] == "test@example.com"
    assert info["first_name"] == "Test"
    assert info["last_name"] == "User"


@pytest.mark.django_db
def test_get_or_create_user_does_not_create_user_when_disabled(
    settings: pytest_django.fixtures.SettingsWrapper,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings.OIDC_CREATE_USER = False
    backend = CustomOIDCBackend()
    monkeypatch.setattr(
        backend,
        "get_userinfo",
        lambda access_token, id_token, payload: {"email": "new@example.com"},
    )

    user = backend.get_or_create_user(
        access_token="access-token",
        id_token="id-token",
        payload={"sub": "test"},
    )

    assert user is None
    assert User.objects.count() == 0


@pytest.mark.django_db
def test_get_or_create_user_returns_existing_user_when_creation_disabled(
    settings: pytest_django.fixtures.SettingsWrapper,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings.OIDC_CREATE_USER = False
    existing_user = User.objects.create_user(
        username="existing@example.com", email="existing@example.com"
    )
    backend = CustomOIDCBackend()
    monkeypatch.setattr(
        backend,
        "get_userinfo",
        lambda access_token, id_token, payload: {"email": "existing@example.com"},
    )

    user = backend.get_or_create_user(
        access_token="access-token",
        id_token="id-token",
        payload={"sub": "test"},
    )

    assert user == existing_user
    assert User.objects.count() == 1


@pytest.mark.django_db
def test_update_user_role_from_claims(settings: pytest_django.Settings) -> None:
    """
    The role given to a new user is based on ``DEFAULT_USER_ROLE``.

    In this test, we're ensuring that updating a user promotes it to the new role from the token.
    """
    settings.OIDC_OP_SET_ROLES_FROM_CLAIMS = True
    settings.OIDC_OP_ROLE_CLAIM_PATH = "realm_access.roles"
    settings.OIDC_ACCESS_ATTRIBUTE_MAP = {
        "given_name": "first_name",
        "family_name": "last_name",
        "realm_access": "realm_access",
    }

    user = User.objects.create(
        first_name="Foo", last_name="Bar", username="foobar", email="foobar@example.com"
    )
    # User has been given the DEFAULT_USER_ROLE on creation.
    assert roles.role_user(user).get_role() == roles.USER_ROLE_READER
    backend = CustomOIDCBackend()

    # Promote the role in the DEFAULT_USER_ROLE setting.
    settings.DEFAULT_USER_ROLE = roles.USER_ROLE_ADMIN

    backend.update_user(
        user,
        {
            "email": "foobar@example.com",
            "first_name": "Foo",
            "last_name": "Bar",
            "realm_access": {"roles": ["admin"]},
        },
    )

    user.refresh_from_db()
    # User has been promoted to the new role on update.
    assert roles.role_user(user).get_role() == roles.USER_ROLE_ADMIN
