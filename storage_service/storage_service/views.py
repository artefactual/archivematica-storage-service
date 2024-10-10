from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth.views import logout_then_login
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone
from django.utils.translation import get_language
from django.views.decorators.cache import cache_page
from django.views.decorators.http import last_modified
from django.views.i18n import JavaScriptCatalog
from mozilla_django_oidc.views import OIDCAuthenticationRequestView
from mozilla_django_oidc.views import OIDCLogoutView
from shibboleth.views import ShibbolethLogoutView


@cache_page(86400, key_prefix="js18n-%s" % get_language())
@last_modified(lambda req, **kw: timezone.now())
def cached_javascript_catalog(request, domain="djangojs", packages=None):
    return JavaScriptCatalog.as_view()(request, domain, packages)


class CustomShibbolethLogoutView(ShibbolethLogoutView):
    pass


class CustomOIDCAuthenticationRequestView(OIDCAuthenticationRequestView):
    """
    Provide OpenID Connect authentication
    """

    def get_settings(self, attr, *args):
        if attr in [
            "OIDC_RP_CLIENT_ID",
            "OIDC_RP_CLIENT_SECRET",
            "OIDC_OP_AUTHORIZATION_ENDPOINT",
            "OIDC_OP_TOKEN_ENDPOINT",
            "OIDC_OP_USER_ENDPOINT",
            "OIDC_OP_JWKS_ENDPOINT",
            "OIDC_OP_LOGOUT_ENDPOINT",
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
        return OIDCAuthenticationRequestView.get_settings(attr, *args)

    def get(self, request):
        self.request = request
        self.OIDC_RP_CLIENT_ID = self.get_settings("OIDC_RP_CLIENT_ID")
        self.OIDC_RP_CLIENT_SECRET = self.get_settings("OIDC_RP_CLIENT_SECRET")
        self.OIDC_OP_AUTH_ENDPOINT = self.get_settings("OIDC_OP_AUTHORIZATION_ENDPOINT")

        return super().get(request)


class CustomOIDCLogoutView(OIDCLogoutView):
    """
    Provide OpenID Logout capability
    """

    def get(self, request):
        self.request = request

        if "oidc_id_token" in request.session:
            # If the user authenticated via OIDC, perform the OIDC logout.
            redirect = super().post(request)

            if "providername" in request.session:
                del request.session["providername"]

            return redirect
        else:
            # If the user did not authenticate via OIDC, perform a local logout and redirect to login.
            return logout_then_login(request)


def get_oidc_logout_url(request):
    """
    Constructs the OIDC logout URL used in OIDCLogoutView.
    """
    # Retrieve the ID token from the session.
    id_token = request.session.get("oidc_id_token")

    if not id_token:
        raise ValueError("ID token not found in session.")

    # Get the end session endpoint.
    end_session_endpoint = getattr(settings, "OIDC_OP_LOGOUT_ENDPOINT", None)

    # Override the end session endpoint from the provider settings if available.
    if request:
        provider_name = request.session.get("providername")

        if provider_name and provider_name in settings.OIDC_PROVIDERS:
            provider_settings = settings.OIDC_PROVIDERS.get(provider_name, {})
            end_session_endpoint = provider_settings.get("OIDC_OP_LOGOUT_ENDPOINT")

            if end_session_endpoint is None:
                raise ImproperlyConfigured(
                    f"Setting OIDC_OP_LOGOUT_ENDPOINT for provider {provider_name} not found"
                )

    if not end_session_endpoint:
        raise ValueError("OIDC logout endpoint not configured for provider.")

    # Define the post logout redirect URL.
    post_logout_redirect_uri = request.build_absolute_uri("/")

    # Construct the logout URL with required parameters.
    params = {
        "id_token_hint": id_token,
        "post_logout_redirect_uri": post_logout_redirect_uri,
    }
    logout_url = f"{end_session_endpoint}?{urlencode(params)}"

    return logout_url
