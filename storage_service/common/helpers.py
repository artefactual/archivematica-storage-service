from os import environ
from typing import Any
from typing import Dict
from typing import Iterable

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


def get_oidc_secondary_providers(
    oidc_secondary_provider_names: Iterable[str],
) -> Dict[str, Dict[str, str]]:
    providers = {}

    for provider_name in oidc_secondary_provider_names:
        provider_name = provider_name.strip().upper()
        client_id = environ.get(f"OIDC_RP_CLIENT_ID_{provider_name}")
        client_secret = environ.get(f"OIDC_RP_CLIENT_SECRET_{provider_name}")
        authorization_endpoint = environ.get(
            f"OIDC_OP_AUTHORIZATION_ENDPOINT_{provider_name}", ""
        )
        token_endpoint = environ.get(f"OIDC_OP_TOKEN_ENDPOINT_{provider_name}", "")
        user_endpoint = environ.get(f"OIDC_OP_USER_ENDPOINT_{provider_name}", "")
        jwks_endpoint = environ.get(f"OIDC_OP_JWKS_ENDPOINT_{provider_name}", "")
        logout_endpoint = environ.get(f"OIDC_OP_LOGOUT_ENDPOINT_{provider_name}", "")

        if client_id and client_secret:
            providers[provider_name] = {
                "OIDC_RP_CLIENT_ID": client_id,
                "OIDC_RP_CLIENT_SECRET": client_secret,
                "OIDC_OP_AUTHORIZATION_ENDPOINT": authorization_endpoint,
                "OIDC_OP_TOKEN_ENDPOINT": token_endpoint,
                "OIDC_OP_USER_ENDPOINT": user_endpoint,
                "OIDC_OP_JWKS_ENDPOINT": jwks_endpoint,
                "OIDC_OP_LOGOUT_ENDPOINT": logout_endpoint,
            }

    return providers
