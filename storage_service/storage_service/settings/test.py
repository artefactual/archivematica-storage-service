"""Test settings and globals."""

from .base import *

# ######## IN-MEMORY TEST DATABASE
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": "archivematica-test.db",
        "TEST": {"NAME": "archivematica-test.db"},
        "USER": "",
        "PASSWORD": "",
        "HOST": "",
        "PORT": "",
    }
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"require_debug_false": {"()": "django.utils.log.RequireDebugFalse"}},
    "formatters": {
        "simple": {"format": "%(levelname)-8s  %(name)s.%(funcName)s:  %(message)s"}
    },
    "handlers": {
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "simple",
        }
    },
    "root": {"handlers": ["console"], "level": "WARNING"},
}

# Disable whitenoise
STORAGES["staticfiles"]["BACKEND"] = (
    "django.contrib.staticfiles.storage.StaticFilesStorage"
)
if MIDDLEWARE[0] == "whitenoise.middleware.WhiteNoiseMiddleware":
    del MIDDLEWARE[0]
