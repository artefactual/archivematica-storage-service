# flake8: noqa

"""Development settings and globals."""

from __future__ import absolute_import

import dj_database_url

from .base import *


# ######## DATABASE CONFIGURATION
# See: https://docs.djangoproject.com/en/dev/ref/settings/#databases
DATABASES = {}
if "SS_DB_URL" in environ:
    DATABASES["default"] = dj_database_url.config(env="SS_DB_URL", conn_max_age=600)
else:
    DATABASES["default"] = {
        "ENGINE": "django.db.backends.sqlite3",  # Add 'postgresql_psycopg2', 'postgresql', 'mysql', 'sqlite3' or 'oracle'.
        "NAME": get_env_variable("SS_DB_NAME"),
        "USER": get_env_variable("SS_DB_USER"),  # Not used with sqlite3.
        "PASSWORD": get_env_variable("SS_DB_PASSWORD"),  # Not used with sqlite3.
        "HOST": get_env_variable(
            "SS_DB_HOST"
        ),  # Set to empty string forr localhost. Not used with sqlite3.
        "PORT": "",  # Set to empty string for default. Not used with sqlite3.
    }
# ######## END DATABASE CONFIGURATION


# DEBUG CONFIGURATION
# See: https://docs.djangoproject.com/en/dev/ref/settings/#debug
DEBUG = True
# ######## END DEBUG CONFIGURATION


# ######## EMAIL CONFIGURATION
# See: https://docs.djangoproject.com/en/dev/ref/settings/#email-backend
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
# ######## END EMAIL CONFIGURATION


# ######## CACHE CONFIGURATION
# See: https://docs.djangoproject.com/en/dev/ref/settings/#caches
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
# ######## END CACHE CONFIGURATION


# ########## TOOLBAR CONFIGURATION
# # See: https://github.com/django-debug-toolbar/django-debug-toolbar#installation
# INSTALLED_APPS += (
#     'debug_toolbar',
# )

# # See: https://github.com/django-debug-toolbar/django-debug-toolbar#installation
# INTERNAL_IPS = ('127.0.0.1',)

# # See: https://github.com/django-debug-toolbar/django-debug-toolbar#installation
# MIDDLEWARE_CLASSES += (
#     'debug_toolbar.middleware.DebugToolbarMiddleware',
# )
# ########## END TOOLBAR CONFIGURATION
