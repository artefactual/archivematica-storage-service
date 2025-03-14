import json
from typing import Any
from typing import Optional

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ImproperlyConfigured
from django_cas_ng.backends import CASBackend
from josepy.jws import JWS
from mozilla_django_oidc.auth import OIDCAuthenticationBackend

from archivematica.storage_service.administration import roles


class CustomCASBackend(CASBackend):
    def configure_user(self, user):
        # If CAS_AUTOCONFIGURE_EMAIL and CAS_EMAIL_DOMAIN settings are
        # configured, add an email address for this user, using rule
        # username@domain.
        if settings.CAS_AUTOCONFIGURE_EMAIL and settings.CAS_EMAIL_DOMAIN:
            user.email = f"{user.username}@{settings.CAS_EMAIL_DOMAIN}"
            user.save()
        return user


class CustomOIDCBackend(OIDCAuthenticationBackend):
    """Provide OpenID Connect authentication."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # Store additional settings as instance attributes.
        self.OIDC_OP_SET_ROLES_FROM_CLAIMS = getattr(
            settings, "OIDC_OP_SET_ROLES_FROM_CLAIMS", False
        )
        self.OIDC_OP_ROLE_CLAIM_PATH = getattr(
            settings, "OIDC_OP_ROLE_CLAIM_PATH", "realm_access.roles"
        )

        # Extract valid role keys from USER_ROLES.
        self.VALID_ROLES = {role[0] for role in roles.USER_ROLES}

    def get_settings(self, attr, *args) -> Any:
        if attr in [
            "OIDC_RP_CLIENT_ID",
            "OIDC_RP_CLIENT_SECRET",
            "OIDC_OP_AUTHORIZATION_ENDPOINT",
            "OIDC_OP_TOKEN_ENDPOINT",
            "OIDC_OP_USER_ENDPOINT",
            "OIDC_OP_JWKS_ENDPOINT",
            "OIDC_OP_LOGOUT_ENDPOINT",
            "OIDC_OP_SET_ROLES_FROM_CLAIMS",
            "OIDC_OP_ROLE_CLAIM_PATH",
        ]:
            # Retrieve the request object stored in the instance.
            request = getattr(self, "request", None)

            if request:
                provider_name = request.session.get("providername")

                if provider_name and provider_name in settings.OIDC_PROVIDERS:
                    provider_settings = settings.OIDC_PROVIDERS.get(provider_name, {})
                    value = provider_settings.get(attr)

                    if value is None:
                        raise ImproperlyConfigured(
                            f"Setting {attr} for provider {provider_name} not found"
                        )
                    return value

        # If request is None or provider_name session var is not set or attr is
        # not in the list, call the superclass's get_settings method.
        return OIDCAuthenticationBackend.get_settings(attr, *args)

    def authenticate(self, request, **kwargs) -> Any:
        self.request = request
        self.OIDC_RP_CLIENT_ID = self.get_settings("OIDC_RP_CLIENT_ID")
        self.OIDC_RP_CLIENT_SECRET = self.get_settings("OIDC_RP_CLIENT_SECRET")
        self.OIDC_OP_TOKEN_ENDPOINT = self.get_settings("OIDC_OP_TOKEN_ENDPOINT")
        self.OIDC_OP_USER_ENDPOINT = self.get_settings("OIDC_OP_USER_ENDPOINT")
        self.OIDC_OP_JWKS_ENDPOINT = self.get_settings("OIDC_OP_JWKS_ENDPOINT")
        self.OIDC_OP_SET_ROLES_FROM_CLAIMS = self.get_settings(
            "OIDC_OP_SET_ROLES_FROM_CLAIMS"
        )
        self.OIDC_OP_ROLE_CLAIM_PATH = self.get_settings("OIDC_OP_ROLE_CLAIM_PATH")

        return super().authenticate(request, **kwargs)

    def get_userinfo(
        self, access_token: str, id_token: str, verified_id: dict[str, Any]
    ) -> dict[str, Any]:
        """Extract user details from JSON web tokens.

        It returns a dict of user details that will be applied directly to the
        user model.
        """

        def decode_token(token: str) -> Any:
            sig = JWS.from_compact(token.encode("utf-8"))
            payload = sig.payload.decode("utf-8")
            return json.loads(payload)

        access_info = decode_token(access_token)
        id_info = decode_token(id_token)

        info: dict[str, Any] = {}

        for oidc_attr, user_attr in settings.OIDC_ACCESS_ATTRIBUTE_MAP.items():
            if oidc_attr in access_info:
                info.setdefault(user_attr, access_info[oidc_attr])

        for oidc_attr, user_attr in settings.OIDC_ID_ATTRIBUTE_MAP.items():
            if oidc_attr in id_info:
                info.setdefault(user_attr, id_info[oidc_attr])

        return info

    def create_user(self, user_info: dict[str, Any]) -> User:
        """Create a new user when authentication was successful."""
        role = self.get_user_role(user_info)
        if role is None:
            return None

        user = super().create_user(user_info)
        for attr, value in user_info.items():
            setattr(user, attr, value)
        user.set_role(role)
        return user

    def update_user(self, user: User, user_info: dict[str, Any]) -> User:
        """Updates the user's role only if the setting allows roles to be set from OIDC claims."""
        if self.OIDC_OP_SET_ROLES_FROM_CLAIMS:
            role = self.get_user_role(user_info)
            if role is None:
                return None
            user.set_role(role)
        return user

    def get_user_role(self, user_info: dict[str, Any]) -> Optional[str]:
        """
        Assigns the user's role based on OIDC token claims if enabled in settings.
        Otherwise, assigns the default role.
        """
        if self.OIDC_OP_SET_ROLES_FROM_CLAIMS:
            # Get the role claim path from settings (e.g. "realm_access.roles").
            claim_path = self.OIDC_OP_ROLE_CLAIM_PATH.split(".")  # Convert to a list

            role = user_info
            for key in claim_path:
                if isinstance(role, dict):
                    role = role.get(key)
                else:
                    role = None
                    break

            # If role is a list, pick the first one.
            if isinstance(role, list) and role:
                role = role[0]

            if role and role in self.VALID_ROLES:
                return roles.promoted_role(role)
            else:
                return None
        else:
            return roles.promoted_role(settings.DEFAULT_USER_ROLE)
