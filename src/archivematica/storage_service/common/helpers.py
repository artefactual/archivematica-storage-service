from collections.abc import Iterable
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


def get_oidc_secondary_providers(
    oidc_secondary_provider_names: Iterable[str],
) -> dict[str, dict[str, object]]:
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
        set_roles_from_claims = is_true(
            environ.get(f"OIDC_OP_SET_ROLES_FROM_CLAIMS_{provider_name}", "")
        )
        role_claim_path = environ.get(
            f"OIDC_OP_ROLE_CLAIM_PATH_{provider_name}", "realm_access.roles"
        )

        if client_id and client_secret:
            providers[provider_name] = {
                "OIDC_RP_CLIENT_ID": client_id,
                "OIDC_RP_CLIENT_SECRET": client_secret,
                "OIDC_OP_AUTHORIZATION_ENDPOINT": authorization_endpoint,
                "OIDC_OP_TOKEN_ENDPOINT": token_endpoint,
                "OIDC_OP_USER_ENDPOINT": user_endpoint,
                "OIDC_OP_JWKS_ENDPOINT": jwks_endpoint,
                "OIDC_OP_LOGOUT_ENDPOINT": logout_endpoint,
                "OIDC_OP_SET_ROLES_FROM_CLAIMS": set_roles_from_claims,
                "OIDC_OP_ROLE_CLAIM_PATH": role_claim_path,
            }

    return providers
