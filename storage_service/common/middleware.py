from django.conf import settings
from django.http import HttpResponseRedirect
from django.utils.deprecation import MiddlewareMixin
from django.utils.http import urlquote
from re import compile
from shibboleth.middleware import ShibbolethRemoteUserMiddleware


# Login required code from https://gist.github.com/ryanwitt/130583
# With modifications from comments on
# http://onecreativeblog.com/post/59051248/django-login-required-middleware

EXEMPT_URLS = [compile(settings.LOGIN_URL.lstrip("/"))]
if hasattr(settings, "LOGIN_EXEMPT_URLS"):
    EXEMPT_URLS += [compile(expr) for expr in settings.LOGIN_EXEMPT_URLS]


class AuditLogMiddleware:
    """Add X-Username header with authenticated user to responses."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.user.is_authenticated:
            response["X-Username"] = request.user.get_username()
        return response


class LoginRequiredMiddleware(MiddlewareMixin):
    """
    Middleware that requires a user to be authenticated to view any page other
    than LOGIN_URL. Exemptions to this requirement can optionally be specified
    in settings via a list of regular expressions in LOGIN_EXEMPT_URLS (which
    you can copy from your urls.py).

    Requires authentication middleware and template context processors to be
    loaded. You'll get an error if they aren't.
    """

    def process_request(self, request):
        assert hasattr(
            request, "user"
        ), "The Login Required middleware\
 requires authentication middleware to be installed. Edit your\
 MIDDLEWARE setting to insert\
 'django.contrib.auth.middlware.AuthenticationMiddleware'. If that doesn't\
 work, ensure your TEMPLATES setting includes\
 'django.core.context_processors.auth'."
        if not request.user.is_authenticated:
            path = request.path_info.lstrip("/")
            if not any(m.match(path) for m in EXEMPT_URLS):
                fullURL = "{}?next={}".format(
                    settings.LOGIN_URL, urlquote(request.get_full_path())
                )
                return HttpResponseRedirect(fullURL)


SHIBBOLETH_REMOTE_USER_HEADER = getattr(
    settings, "SHIBBOLETH_REMOTE_USER_HEADER", "REMOTE_USER"
)


class CustomShibbolethRemoteUserMiddleware(ShibbolethRemoteUserMiddleware):
    """
    Custom version of Shibboleth remote user middleware

    THe aim of this is to provide a custom header name that is expected
    to identify the remote Shibboleth user
    """

    header = SHIBBOLETH_REMOTE_USER_HEADER

    def make_profile(self, user, shib_meta):
        """
        Customize the user based on shib_meta mappings (anything that's not
        already covered by the attribute map)
        """
        # Make the user an administrator if they are in the designated admin group
        entitlements = shib_meta["entitlement"].split(";")
        user.is_superuser = settings.SHIBBOLETH_ADMIN_ENTITLEMENT in entitlements
        user.save()


class ForceDefaultLanguageMiddleware(MiddlewareMixin):
    """
    Ignore Accept-Language HTTP headers

    This will force the I18N machinery to always choose settings.LANGUAGE_CODE
    as the default initial language, unless another one is set via sessions or
    cookies.

    Should be installed *before* any middleware that checks
    request.META['HTTP_ACCEPT_LANGUAGE'], namely
    django.middleware.locale.LocaleMiddleware.
    """

    def process_request(self, request):
        if "HTTP_ACCEPT_LANGUAGE" in request.META:
            del request.META["HTTP_ACCEPT_LANGUAGE"]
