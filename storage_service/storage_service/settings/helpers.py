from os import environ
from typing import Any

from django.core.exceptions import ImproperlyConfigured


def get_env_variable(var_name: str) -> Any:
    """Get the environment variable or return exception"""
    try:
        return environ[var_name]
    except KeyError:
        error_msg = "Set the %s environment variable" % var_name
        raise ImproperlyConfigured(error_msg)


def is_true(env_str: str) -> bool:
    return env_str.lower() in ["true", "yes", "on", "1"]
