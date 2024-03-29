from django.utils import timezone
from django.utils.translation import get_language
from django.views.decorators.cache import cache_page
from django.views.decorators.http import last_modified
from django.views.i18n import JavaScriptCatalog
from shibboleth.views import ShibbolethLogoutView


@cache_page(86400, key_prefix="js18n-%s" % get_language())
@last_modified(lambda req, **kw: timezone.now())
def cached_javascript_catalog(request, domain="djangojs", packages=None):
    return JavaScriptCatalog.as_view()(request, domain, packages)


class CustomShibbolethLogoutView(ShibbolethLogoutView):
    pass
