import pytest
import pytest_django
from django.contrib.auth.models import User

from archivematica.storage_service.administration import roles
from archivematica.storage_service.common.backends import CustomCASBackend
from archivematica.storage_service.common.signals import _cas_user_role
from archivematica.storage_service.common.signals import cas_user_authenticated_callback

TEST_CAS_USER = "casuser"
TEST_CAS_ROLE_ATTRIBUTE = "memberOf"
TEST_CAS_ADMIN_ATTRIBUTE_VALUE = "administrators"
TEST_CAS_MANAGER_ATTRIBUTE_VALUE = "managers"
TEST_CAS_REVIEWER_ATTRIBUTE_VALUE = "reviewers"


@pytest.fixture
def settings(settings: pytest_django.Settings) -> pytest_django.Settings:
    settings.CAS_ADMIN_ATTRIBUTE = TEST_CAS_ROLE_ATTRIBUTE
    settings.CAS_ADMIN_ATTRIBUTE_VALUE = TEST_CAS_ADMIN_ATTRIBUTE_VALUE
    settings.CAS_MANAGER_ATTRIBUTE = TEST_CAS_ROLE_ATTRIBUTE
    settings.CAS_MANAGER_ATTRIBUTE_VALUE = TEST_CAS_MANAGER_ATTRIBUTE_VALUE
    settings.CAS_REVIEWER_ATTRIBUTE = TEST_CAS_ROLE_ATTRIBUTE
    settings.CAS_REVIEWER_ATTRIBUTE_VALUE = TEST_CAS_REVIEWER_ATTRIBUTE_VALUE

    return settings


@pytest.mark.parametrize(
    "attributes,expected_role",
    [
        # The CAS client hands over a single group as a string and several
        # groups as a list, so both shapes have to be understood.
        (
            {TEST_CAS_ROLE_ATTRIBUTE: TEST_CAS_ADMIN_ATTRIBUTE_VALUE},
            roles.USER_ROLE_ADMIN,
        ),
        (
            {TEST_CAS_ROLE_ATTRIBUTE: [TEST_CAS_MANAGER_ATTRIBUTE_VALUE, "users"]},
            roles.USER_ROLE_MANAGER,
        ),
        # The roles are checked from the highest permission to the lowest, so
        # a member of every group gets the highest role.
        (
            {
                TEST_CAS_ROLE_ATTRIBUTE: [
                    TEST_CAS_ADMIN_ATTRIBUTE_VALUE,
                    TEST_CAS_MANAGER_ATTRIBUTE_VALUE,
                    TEST_CAS_REVIEWER_ATTRIBUTE_VALUE,
                ]
            },
            roles.USER_ROLE_ADMIN,
        ),
        (
            {
                TEST_CAS_ROLE_ATTRIBUTE: [
                    TEST_CAS_MANAGER_ATTRIBUTE_VALUE,
                    TEST_CAS_REVIEWER_ATTRIBUTE_VALUE,
                ]
            },
            roles.USER_ROLE_MANAGER,
        ),
        (
            {TEST_CAS_ROLE_ATTRIBUTE: TEST_CAS_REVIEWER_ATTRIBUTE_VALUE},
            roles.USER_ROLE_REVIEWER,
        ),
        ({TEST_CAS_ROLE_ATTRIBUTE: ["users"]}, roles.USER_ROLE_READER),
        ({}, roles.USER_ROLE_READER),
        ({"affiliation": [TEST_CAS_ADMIN_ATTRIBUTE_VALUE]}, roles.USER_ROLE_READER),
    ],
)
def test_cas_user_role(
    settings: pytest_django.Settings,
    attributes: dict[str, object],
    expected_role: str,
) -> None:
    assert _cas_user_role(attributes) == expected_role


@pytest.mark.parametrize(
    "unset_setting", ["CAS_ADMIN_ATTRIBUTE", "CAS_ADMIN_ATTRIBUTE_VALUE"]
)
def test_unconfigured_role_attributes_grant_nobody_that_role(
    settings: pytest_django.Settings, unset_setting: str
) -> None:
    setattr(settings, unset_setting, None)

    # The administrator role is skipped because it is not configured, but the
    # manager role still applies.
    assert (
        _cas_user_role(
            {
                TEST_CAS_ROLE_ATTRIBUTE: [
                    TEST_CAS_ADMIN_ATTRIBUTE_VALUE,
                    TEST_CAS_MANAGER_ATTRIBUTE_VALUE,
                ]
            }
        )
        == roles.USER_ROLE_MANAGER
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    "attributes,expected_role",
    [
        (
            {TEST_CAS_ROLE_ATTRIBUTE: TEST_CAS_ADMIN_ATTRIBUTE_VALUE},
            roles.USER_ROLE_ADMIN,
        ),
        (
            {TEST_CAS_ROLE_ATTRIBUTE: [TEST_CAS_MANAGER_ATTRIBUTE_VALUE]},
            roles.USER_ROLE_MANAGER,
        ),
        ({TEST_CAS_ROLE_ATTRIBUTE: ["users"]}, roles.USER_ROLE_READER),
    ],
)
def test_cas_user_authenticated_callback_sets_the_role(
    settings: pytest_django.Settings,
    attributes: dict[str, object],
    expected_role: str,
) -> None:
    settings.CAS_CHECK_ADMIN_ATTRIBUTES = True
    user = User.objects.create(username=TEST_CAS_USER)

    cas_user_authenticated_callback(sender=None, user=user, attributes=attributes)

    user.refresh_from_db()
    assert roles.get_user_role(user) == expected_role
    assert user.is_superuser is (expected_role == roles.USER_ROLE_ADMIN)
    assert user.groups.filter(name="Managers").exists() is (
        expected_role == roles.USER_ROLE_MANAGER
    )


@pytest.mark.django_db
def test_cas_user_authenticated_callback_demotes_a_former_administrator(
    settings: pytest_django.Settings,
) -> None:
    settings.CAS_CHECK_ADMIN_ATTRIBUTES = True
    user = User.objects.create(username=TEST_CAS_USER, is_superuser=True)
    assert roles.get_user_role(user) == roles.USER_ROLE_ADMIN

    cas_user_authenticated_callback(
        sender=None,
        user=user,
        attributes={TEST_CAS_ROLE_ATTRIBUTE: ["users"]},
    )

    user.refresh_from_db()
    assert roles.get_user_role(user) == roles.USER_ROLE_READER
    assert not user.is_superuser


@pytest.mark.django_db
def test_cas_user_authenticated_callback_sets_the_role_on_the_authenticated_user(
    settings: pytest_django.Settings,
) -> None:
    settings.CAS_CHECK_ADMIN_ATTRIBUTES = True
    user = User.objects.create(username=TEST_CAS_USER)
    # django_cas_ng can match a local user through another field, in which
    # case the CAS username it sends along differs from the local one and may
    # even name another account.
    other_user = User.objects.create(username=f"{TEST_CAS_USER}@example.com")

    cas_user_authenticated_callback(
        sender=None,
        user=user,
        username=other_user.username,
        attributes={TEST_CAS_ROLE_ATTRIBUTE: TEST_CAS_ADMIN_ATTRIBUTE_VALUE},
    )

    user.refresh_from_db()
    assert roles.get_user_role(user) == roles.USER_ROLE_ADMIN
    other_user.refresh_from_db()
    assert roles.get_user_role(other_user) == roles.USER_ROLE_READER


@pytest.mark.django_db
def test_cas_user_authenticated_callback_ignores_a_missing_user(
    settings: pytest_django.Settings,
) -> None:
    settings.CAS_CHECK_ADMIN_ATTRIBUTES = True

    # django_cas_ng sends no user when it is configured not to create local
    # users and none matches the CAS identity.
    cas_user_authenticated_callback(
        sender=None,
        user=None,
        username=TEST_CAS_USER,
        attributes={TEST_CAS_ROLE_ATTRIBUTE: TEST_CAS_ADMIN_ATTRIBUTE_VALUE},
    )

    assert not User.objects.exists()


@pytest.mark.django_db
def test_cas_user_authenticated_callback_does_nothing_when_the_check_is_off(
    settings: pytest_django.Settings,
) -> None:
    settings.CAS_CHECK_ADMIN_ATTRIBUTES = False
    user = User.objects.create(username=TEST_CAS_USER, is_superuser=True)

    # These attributes would demote the administrator if the check was on.
    cas_user_authenticated_callback(
        sender=None,
        user=user,
        attributes={TEST_CAS_ROLE_ATTRIBUTE: ["users"]},
    )

    user.refresh_from_db()
    assert roles.get_user_role(user) == roles.USER_ROLE_ADMIN
    assert user.is_superuser


@pytest.mark.django_db
@pytest.mark.parametrize(
    "autoconfigure_email,expected_email",
    [(True, f"{TEST_CAS_USER}@example.com"), (False, "")],
)
def test_cas_backend_autoconfigures_email(
    settings: pytest_django.Settings,
    autoconfigure_email: bool,
    expected_email: str,
) -> None:
    settings.CAS_AUTOCONFIGURE_EMAIL = autoconfigure_email
    settings.CAS_EMAIL_DOMAIN = "example.com"
    user = User.objects.create(username=TEST_CAS_USER)

    configured_user = CustomCASBackend().configure_user(user)

    assert configured_user.email == expected_email
    user.refresh_from_db()
    assert user.email == expected_email
