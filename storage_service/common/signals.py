import logging

from administration import roles
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.dispatch import receiver
from django_auth_ldap.backend import populate_user
from django_cas_ng.signals import cas_user_authenticated


LOGGER = logging.getLogger(__name__)


def _cas_user_role(cas_attributes):
    """Determine the role of the user from CAS attributes.

    :param cas_attributes: Attributes dict returned by CAS server.

    :returns: The role of the user.
    """
    CAS_ROLE_ATTRIBUTES = [
        (
            roles.USER_ROLE_ADMIN,
            "CAS_ADMIN_ATTRIBUTE",
            "CAS_ADMIN_ATTRIBUTE_VALUE",
        ),
        (
            roles.USER_ROLE_MANAGER,
            "CAS_MANAGER_ATTRIBUTE",
            "CAS_MANAGER_ATTRIBUTE_VALUE",
        ),
        (
            roles.USER_ROLE_REVIEWER,
            "CAS_REVIEWER_ATTRIBUTE",
            "CAS_REVIEWER_ATTRIBUTE_VALUE",
        ),
    ]

    for role, role_attr, role_attr_val in CAS_ROLE_ATTRIBUTES:
        role_attr = getattr(settings, role_attr, None)
        role_attr_val = getattr(settings, role_attr_val, None)
        if not all(
            (
                role_attr,
                role_attr_val,
            )
        ):
            continue
        cas_attr = cas_attributes.get(role_attr)
        if not cas_attr:
            continue
        if isinstance(cas_attr, str):
            cas_attr = [cas_attr]
        if role_attr_val in cas_attr:
            return role

    return roles.USER_ROLE_READER


@receiver(cas_user_authenticated)
def cas_user_authenticated_callback(sender, **kwargs):
    """Set user.is_superuser based on CAS attributes.

    When a user is authenticated, django_cas_ng sends the
    cas_user_authenticated signal, which includes any attributes
    returned by the CAS server during p3/serviceValidate.

    When the CAS_CHECK_ADMIN_ATTRIBUTES setting is enabled, we use this
    receiver to set user.is_superuser to True if we find the expected
    key-value combination configured with CAS_ADMIN_ATTRIBUTE and
    CAS_ADMIN_ATTRIBUTE_VALUE in the CAS attributes, and False if not.

    This check happens for both new and existing users, so that changes
    in group membership on the CAS server (e.g. a user being added or
    removed from the administrator group) are applied in Archivematica
    on the next login.
    """
    if not settings.CAS_CHECK_ADMIN_ATTRIBUTES:
        return

    LOGGER.debug("cas_user_authenticated signal received")

    username = kwargs.get("user")
    attributes = kwargs.get("attributes")

    if not attributes:
        return

    User = get_user_model()
    role = _cas_user_role(attributes)

    role = roles.promoted_role(role)

    with transaction.atomic():
        user = User.objects.select_for_update().get(username=username)
        user.set_role(role)


@receiver(populate_user)
def ldap_populate_user_profile(sender, user=None, ldap_user=None, **kwargs):
    """Populate the user role after authentication."""
    if not settings.LDAP_AUTHENTICATION:
        return

    LOGGER.debug("django_auth_ldap.backend.populate_user signal received")

    if user is None or ldap_user is None:
        return

    if user.is_superuser:
        return

    role = roles.USER_ROLE_READER
    if settings.AUTH_LDAP_ADMIN_GROUP in ldap_user.group_names:
        role = roles.USER_ROLE_ADMIN
    elif settings.AUTH_LDAP_MANAGER_GROUP in ldap_user.group_names:
        role = roles.USER_ROLE_MANAGER
    elif settings.AUTH_LDAP_REVIEWER_GROUP in ldap_user.group_names:
        role = roles.USER_ROLE_REVIEWER

    role = roles.promoted_role(role)

    LOGGER.debug("Setting role %s for user %s", role, user.username)
    user.set_role(role)
