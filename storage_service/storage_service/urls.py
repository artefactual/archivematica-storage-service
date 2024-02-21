import administration.urls
import django.contrib.auth.views
import locations.api.urls
import locations.urls
from django.conf import settings
from django.contrib import admin
from django.urls import include
from django.urls import path
from django.urls import re_path
from django.views.generic import TemplateView

from storage_service import views


urlpatterns = [
    path("", TemplateView.as_view(template_name="index.html")),
    # Uncomment the next line to enable the admin:
    re_path(r"^admin/", admin.site.urls),
    path("", include(locations.urls)),
    path("administration/", include(administration.urls)),
    path("api/", include(locations.api.urls)),
    path(
        "jsi18n/",
        views.cached_javascript_catalog,
        {"domain": "djangojs"},
        name="javascript-catalog",
    ),
    path("i18n/", include(("django.conf.urls.i18n", "i18n"), namespace="i18n")),
    path("oidc/", include("mozilla_django_oidc.urls")),
]

if "django_cas_ng" in settings.INSTALLED_APPS:
    import django_cas_ng.views

    urlpatterns += [
        path("login/", django_cas_ng.views.LoginView.as_view(), name="login"),
        path("logout/", django_cas_ng.views.LogoutView.as_view(), name="logout"),
    ]
else:
    urlpatterns += [
        path(
            "login/",
            django.contrib.auth.views.LoginView.as_view(template_name="login.html"),
            name="login",
        ),
        path("logout/", django.contrib.auth.views.logout_then_login, name="logout"),
    ]

if "shibboleth" in settings.INSTALLED_APPS:
    urlpatterns += [path("shib/", include("shibboleth.urls"))]


if settings.PROMETHEUS_ENABLED:
    # Include prometheus metrics at /metrics
    urlpatterns.append(path("", include("django_prometheus.urls")))
