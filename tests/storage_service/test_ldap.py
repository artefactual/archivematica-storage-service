import pytest
import pytest_django
from django.contrib.auth.models import User
from django_auth_ldap.backend import LDAPBackend
from django_auth_ldap.backend import populate_user

from archivematica.storage_service.administration import roles

TEST_LDAP_USER = "ldapuser"


class FakeLDAPUser:
    """Stand-in for the LDAP user django_auth_ldap sends with the signal."""

    def __init__(self, group_names: set[str]) -> None:
        self.group_names = group_names


@pytest.fixture
def settings(settings: pytest_django.Settings) -> pytest_django.Settings:
    settings.LDAP_AUTHENTICATION = True
    # The receiver only checks that this setting exists.
    settings.AUTH_LDAP_GROUP_SEARCH = object()
    settings.AUTH_LDAP_ADMIN_GROUP = "administrators"
    settings.AUTH_LDAP_MANAGER_GROUP = "managers"
    settings.AUTH_LDAP_REVIEWER_GROUP = "reviewers"
    settings.DEFAULT_USER_ROLE = "reader"

    return settings


def send_populate_user(user: User, group_names: set[str]) -> None:
    """Send the signal django_auth_ldap sends after authentication."""
    populate_user.send(
        sender=LDAPBackend, user=user, ldap_user=FakeLDAPUser(group_names)
    )

    user.refresh_from_db()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "group_names,expected_role",
    [
        # The groups are checked from the highest permission to the lowest,
        # so a member of every group gets the highest role.
        ({"administrators", "managers", "reviewers"}, roles.USER_ROLE_ADMIN),
        ({"managers", "reviewers"}, roles.USER_ROLE_MANAGER),
        ({"reviewers"}, roles.USER_ROLE_REVIEWER),
        (set(), roles.USER_ROLE_READER),
        ({"users"}, roles.USER_ROLE_READER),
    ],
)
def test_group_names_map_to_roles(
    settings: pytest_django.Settings,
    group_names: set[str],
    expected_role: str,
) -> None:
    user = User.objects.create(username=TEST_LDAP_USER)

    send_populate_user(user, group_names)

    assert roles.get_user_role(user) == expected_role


@pytest.mark.django_db
def test_superusers_keep_their_role(settings: pytest_django.Settings) -> None:
    user = User.objects.create(username=TEST_LDAP_USER, is_superuser=True)

    # The receiver leaves superusers alone, so these groups do not demote
    # the administrator.
    send_populate_user(user, {"reviewers"})

    assert roles.get_user_role(user) == roles.USER_ROLE_ADMIN


@pytest.mark.django_db
def test_role_changes_with_the_groups(settings: pytest_django.Settings) -> None:
    user = User.objects.create(username=TEST_LDAP_USER)
    roles.set_user_role(user, roles.USER_ROLE_MANAGER)

    send_populate_user(user, {"reviewers"})

    assert roles.get_user_role(user) == roles.USER_ROLE_REVIEWER


@pytest.mark.django_db
def test_default_role_applies_without_group_search(
    settings: pytest_django.Settings,
) -> None:
    del settings.AUTH_LDAP_GROUP_SEARCH
    settings.DEFAULT_USER_ROLE = "manager"
    user = User.objects.create(username=TEST_LDAP_USER)

    # The groups are ignored, the default role is promoted to instead.
    send_populate_user(user, {"administrators"})

    assert roles.get_user_role(user) == roles.USER_ROLE_MANAGER


@pytest.mark.django_db
def test_receiver_is_inert_when_ldap_is_off(
    settings: pytest_django.Settings,
) -> None:
    settings.LDAP_AUTHENTICATION = False
    user = User.objects.create(username=TEST_LDAP_USER)
    roles.set_user_role(user, roles.USER_ROLE_MANAGER)

    # These groups would make the user an administrator if LDAP was on.
    send_populate_user(user, {"administrators"})

    assert roles.get_user_role(user) == roles.USER_ROLE_MANAGER
