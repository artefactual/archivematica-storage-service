import json
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


ProviderConfig = dict[str, str | bool]


def get_oidc_secondary_providers(
    oidc_secondary_provider_names: Iterable[str],
    default_oidc_claims: dict[str, str],
) -> dict[str, ProviderConfig]:
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
        role_claim_admin = environ.get(
            f"OIDC_ROLE_CLAIM_ADMIN_{provider_name}", "admin"
        )
        role_claim_manager = environ.get(
            f"OIDC_ROLE_CLAIM_MANAGER_{provider_name}", "manager"
        )
        role_claim_reviewer = environ.get(
            f"OIDC_ROLE_CLAIM_REVIEWER_{provider_name}", "reviewer"
        )
        role_claim_reader = environ.get(
            f"OIDC_ROLE_CLAIM_READER_{provider_name}", "reader"
        )
        try:
            access_attribute_map = json.loads(
                environ.get(
                    f"OIDC_ACCESS_ATTRIBUTE_MAP_{provider_name}",
                    json.dumps(default_oidc_claims),
                )
            )
        except json.JSONDecodeError:
            access_attribute_map = default_oidc_claims

        if client_id and client_secret:
            provider_config: ProviderConfig = {
                "OIDC_RP_CLIENT_ID": client_id,
                "OIDC_RP_CLIENT_SECRET": client_secret,
                "OIDC_OP_AUTHORIZATION_ENDPOINT": authorization_endpoint,
                "OIDC_OP_TOKEN_ENDPOINT": token_endpoint,
                "OIDC_OP_USER_ENDPOINT": user_endpoint,
                "OIDC_OP_JWKS_ENDPOINT": jwks_endpoint,
                "OIDC_OP_LOGOUT_ENDPOINT": logout_endpoint,
                "OIDC_OP_SET_ROLES_FROM_CLAIMS": set_roles_from_claims,
                "OIDC_OP_ROLE_CLAIM_PATH": role_claim_path,
                "OIDC_ACCESS_ATTRIBUTE_MAP": access_attribute_map,
                "OIDC_ROLE_CLAIM_ADMIN": role_claim_admin,
                "OIDC_ROLE_CLAIM_MANAGER": role_claim_manager,
                "OIDC_ROLE_CLAIM_REVIEWER": role_claim_reviewer,
                "OIDC_ROLE_CLAIM_READER": role_claim_reader,
            }
            providers[provider_name] = provider_config

    return providers
