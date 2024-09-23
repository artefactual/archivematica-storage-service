import json
from typing import Any
from typing import Dict

from administration import roles
from django.conf import settings
from django.contrib.auth.models import User
from django_cas_ng.backends import CASBackend
from josepy.jws import JWS
from mozilla_django_oidc.auth import OIDCAuthenticationBackend


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

    def get_userinfo(
        self, access_token: str, id_token: str, verified_id: Dict[str, Any]
    ) -> Dict[str, Any]:
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

        info: Dict[str, Any] = {}

        for oidc_attr, user_attr in settings.OIDC_ACCESS_ATTRIBUTE_MAP.items():
            if oidc_attr in access_info:
                info.setdefault(user_attr, access_info[oidc_attr])

        for oidc_attr, user_attr in settings.OIDC_ID_ATTRIBUTE_MAP.items():
            if oidc_attr in id_info:
                info.setdefault(user_attr, id_info[oidc_attr])

        return info

    def create_user(self, user_info: Dict[str, Any]) -> User:
        user = super().create_user(user_info)
        for attr, value in user_info.items():
            setattr(user, attr, value)
        self.set_user_role(user)
        return user

    def update_user(self, user, user_info):
        self.set_user_role(user)
        return user

    def set_user_role(self, user):
        # TODO: use user claims accessible via user's authentication tokens.
        role = roles.promoted_role(roles.USER_ROLE_READER)
        user.set_role(role)
