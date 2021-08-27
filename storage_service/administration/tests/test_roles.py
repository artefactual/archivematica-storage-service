from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
import pytest

from administration import roles


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(
        username="demo", email="demo@example.com", password="Abc.Def.1234"
    )


@pytest.mark.django_db
def test_get_user_roles(user):
    labels = dict(roles.USER_ROLES)
    assert user.get_role_label() == labels[roles.USER_ROLE_READER]
    assert user.is_admin() is False

    user.groups.set([Group.objects.get(name="Reviewers")])
    assert user.get_role_label() == labels[roles.USER_ROLE_REVIEWER]
    assert user.is_admin() is False

    user.groups.set([Group.objects.get(name="Managers")])
    assert user.get_role_label() == labels[roles.USER_ROLE_MANAGER]
    assert user.is_admin() is False

    user.groups.clear()
    user.is_superuser = True
    user.save()
    assert user.get_role_label() == labels[roles.USER_ROLE_ADMIN]
    assert user.is_admin() is True


@pytest.mark.django_db
def test_set_user_roles(user):
    """Setting a role changes group membership and is_superuser is updates."""
    user.set_role(roles.USER_ROLE_READER)
    assert user.is_superuser is False
    assert user.groups.count() == 0

    user.set_role(roles.USER_ROLE_REVIEWER)
    assert user.is_superuser is False
    assert list(user.groups.values_list("name", flat=True)) == ["Reviewers"]

    user.set_role(roles.USER_ROLE_MANAGER)
    assert user.is_superuser is False
    assert list(user.groups.values_list("name", flat=True)) == ["Managers"]

    user.set_role(roles.USER_ROLE_ADMIN)
    assert user.is_superuser is True
    assert user.groups.count() == 0


@pytest.mark.django_db
@pytest.mark.parametrize(
    "default_user_role,input_role,is_superuser,groups",
    [
        # A reader is promoted as per the default role in the settings.
        (roles.USER_ROLE_ADMIN, roles.USER_ROLE_READER, True, []),
        (roles.USER_ROLE_MANAGER, roles.USER_ROLE_READER, False, ["Managers"]),
        (roles.USER_ROLE_REVIEWER, roles.USER_ROLE_READER, False, ["Reviewers"]),
        (roles.USER_ROLE_READER, roles.USER_ROLE_READER, False, []),
        # Only readers are promoted
        (None, roles.USER_ROLE_ADMIN, True, []),
        (None, roles.USER_ROLE_MANAGER, False, ["Managers"]),
        (None, roles.USER_ROLE_REVIEWER, False, ["Reviewers"]),
        # Return original role when the setting value is not recognized.
        ("invalid", roles.USER_ROLE_READER, False, []),
    ],
)
def test_promoted_role(
    user, settings, default_user_role, input_role, is_superuser, groups
):
    settings.DEFAULT_USER_ROLE = default_user_role

    role = roles.promoted_role(input_role)
    user.set_role(role)

    assert user.is_superuser is is_superuser
    assert list(user.groups.values_list("name", flat=True)) == groups
