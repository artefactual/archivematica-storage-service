"""User roles in Archivematica Storage Service.

Every user in the system has a role. The role determines what the user can do.
An administrator uses the `is_superuser` flag. Managers and reviewers are
implemented as Django groups.
"""
from django.conf import settings
from django.contrib.auth.models import Group
from django.db import transaction
from django.utils.translation import gettext as _


# User roles codenames and labels used in this application.
USER_ROLE_ADMIN = "admin"
USER_ROLE_MANAGER = "manager"
USER_ROLE_REVIEWER = "reviewer"
USER_ROLE_READER = "reader"
USER_ROLES = [
    # Users with the is_superuser flag enabled.
    (USER_ROLE_ADMIN, _("Administrator")),
    # Members of the "Managers" group.
    (USER_ROLE_MANAGER, _("Manager")),
    # Members of the "Reviewers" group.
    (USER_ROLE_REVIEWER, _("Reviewer")),
    # Authenticated users.
    (USER_ROLE_READER, _("Reader")),
]


def get_user_role(user):
    """Retrieve the user role codename of a User."""
    if user.is_superuser:
        return USER_ROLE_ADMIN
    if user.groups.filter(name="Managers").exists():
        return USER_ROLE_MANAGER
    if user.groups.filter(name="Reviewers").exists():
        return USER_ROLE_REVIEWER
    return USER_ROLE_READER


def is_admin(user):
    """Return whether a user has the administrator role.

    Equivalent to a ``is_superuser`` look-up, but it is named after the user
    role as opposed to an implementation detail of the Django framework.
    """
    return get_user_role(user) == USER_ROLE_ADMIN


def get_user_role_label(user):
    """Retrieve the user role label of a User."""
    return dict(USER_ROLES)[get_user_role(user)]


@transaction.atomic
def set_user_role(user, role: str):
    """Assign a new role to a User given the role codename."""
    # Only users with the admin role are Django superusers.
    user.is_superuser = role == USER_ROLE_ADMIN
    user.save()

    groups = []
    if role == USER_ROLE_MANAGER:
        managers = Group.objects.get(name="Managers")
        groups.append(managers)
    elif role == USER_ROLE_REVIEWER:
        reviewers = Group.objects.get(name="Reviewers")
        groups.append(reviewers)

    if groups:
        user.groups.set(groups)
    else:
        # Readers don't belong to a group for now.
        user.groups.clear()


def promoted_role(role: str):
    """Return a new role that replaces a reader.

    This is used to promote a reader to a role with more permissions, based on
    user-provided input (settings.DEFAULT_USER_ROLE).
    """
    if role != USER_ROLE_READER:
        return role
    suggested = settings.DEFAULT_USER_ROLE
    if dict(USER_ROLES).get(suggested):
        return suggested
    return role
