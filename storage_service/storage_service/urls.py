from __future__ import absolute_import
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
    url(r"^admin/", include(admin.site.urls)),
    url(r"^", include(locations.urls)),
    url(r"^administration/", include(administration.urls)),
    url(r"^login/$", django.contrib.auth.views.login, {"template_name": "login.html"}),
    url(r"^logout/$", django.contrib.auth.views.logout_then_login, name="logout"),
    url(r"^api/", include(locations.api.urls)),
    url(
        r"^jsi18n/$",
        views.cached_javascript_catalog,
        {"domain": "djangojs"},
        name="javascript-catalog",
    ),
    url(r"^i18n/", include("django.conf.urls.i18n", namespace="i18n")),
]


if "shibboleth" in settings.INSTALLED_APPS:
    # Simulate a shibboleth urls module (so our custom Shibboleth logout view
    # matches the same namespaced URL name as the standard logout view from
    # the shibboleth lib)
    class ShibbolethURLs(object):
        urlpatterns = [
            url(r"^logout/$", views.CustomShibbolethLogoutView.as_view(), name="logout")
        ]

    urlpatterns += [url(r"^shib/", include(ShibbolethURLs, namespace="shibboleth"))]


if settings.PROMETHEUS_ENABLED:
    # Include prometheus metrics at /metrics
    urlpatterns.append(url("", include("django_prometheus.urls")))
