from django.utils.translation import get_language
from django.utils import timezone
from django.views.decorators.cache import cache_page
from django.views.decorators.http import last_modified
from django.views.i18n import javascript_catalog
from shibboleth.views import ShibbolethLogoutView, LOGOUT_SESSION_KEY


@cache_page(86400, key_prefix="js18n-%s" % get_language())
@last_modified(lambda req, **kw: timezone.now())
def cached_javascript_catalog(request, domain="djangojs", packages=None):
    return javascript_catalog(request, domain, packages)


class CustomShibbolethLogoutView(ShibbolethLogoutView):
    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        # LOGOUT_SESSION_KEY is set by the standard logout to prevent re-login
        # which is useful to prevent bouncing straight back to login under
        # certain setups, but not here where we want the Django session state
        # to reflect the SP session state
        if LOGOUT_SESSION_KEY in request.session:
            del request.session[LOGOUT_SESSION_KEY]
        return response
