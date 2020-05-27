# -*- coding: utf-8 -*-
from __future__ import absolute_import

from django.conf import settings
from django_cas_ng.backends import CASBackend


class CustomCASBackend(CASBackend):
    def configure_user(self, user):
        # If CAS_AUTOCONFIGURE_EMAIL and CAS_EMAIL_DOMAIN settings are
        # configured, add an email address for this user, using rule
        # username@domain.
        if settings.CAS_AUTOCONFIGURE_EMAIL and settings.CAS_EMAIL_DOMAIN:
            user.email = "{0}@{1}".format(user.username, settings.CAS_EMAIL_DOMAIN)
            user.save()
        return user
