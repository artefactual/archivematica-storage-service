from django.conf import settings
from django.conf.urls import include, url
from django.contrib import admin
import django.contrib.auth.views
from django.views.generic import TemplateView

import administration.urls
import locations.urls
import locations.api.urls

from storage_service import views


urlpatterns = [
    url(r"^$", TemplateView.as_view(template_name="index.html")),
    # Uncomment the next line to enable the admin:
    url(r"^admin/", admin.site.urls),
    url(r"^", include(locations.urls)),
    url(r"^administration/", include(administration.urls)),
    url(r"^api/", include(locations.api.urls)),
    url(
        r"^jsi18n/$",
        views.cached_javascript_catalog,
        {"domain": "djangojs"},
        name="javascript-catalog",
    ),
    url(r"^i18n/", include(("django.conf.urls.i18n", "i18n"), namespace="i18n")),
    url(r"^oidc/", include("mozilla_django_oidc.urls")),
]

if "django_cas_ng" in settings.INSTALLED_APPS:
    import django_cas_ng.views

    urlpatterns += [
        url(r"login/$", django_cas_ng.views.LoginView.as_view(), name="login"),
        url(r"logout/$", django_cas_ng.views.LogoutView.as_view(), name="logout"),
    ]
else:
    urlpatterns += [
        url(
            r"^login/$",
            django.contrib.auth.views.LoginView.as_view(template_name="login.html"),
            name="login",
        ),
        url(r"^logout/$", django.contrib.auth.views.logout_then_login, name="logout"),
    ]

if "shibboleth" in settings.INSTALLED_APPS:
    # Simulate a shibboleth urls module (so our custom Shibboleth logout view
    # matches the same namespaced URL name as the standard logout view from
    # the shibboleth lib)
    class ShibbolethURLs:
        urlpatterns = [
            url(r"^logout/$", views.CustomShibbolethLogoutView.as_view(), name="logout")
        ]

    urlpatterns += [url(r"^shib/", include(ShibbolethURLs, namespace="shibboleth"))]


if settings.PROMETHEUS_ENABLED:
    # Include prometheus metrics at /metrics
    urlpatterns.append(url("", include("django_prometheus.urls")))
