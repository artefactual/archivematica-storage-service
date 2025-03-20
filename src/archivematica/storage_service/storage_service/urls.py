import django.contrib.auth.views
from django.conf import settings
from django.contrib import admin
from django.urls import include
from django.urls import path
from django.views.generic import TemplateView

import archivematica.storage_service.administration.urls
import archivematica.storage_service.locations.api.urls
import archivematica.storage_service.locations.urls
from archivematica.storage_service.storage_service import views

urlpatterns = [
    path("", TemplateView.as_view(template_name="index.html")),
    path("admin/", admin.site.urls),
    path("", include(archivematica.storage_service.locations.urls)),
    path("administration/", include(archivematica.storage_service.administration.urls)),
    path("api/", include(archivematica.storage_service.locations.api.urls)),
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

elif "mozilla_django_oidc" in settings.INSTALLED_APPS:
    from archivematica.storage_service.storage_service.views import CustomOIDCLogoutView

    urlpatterns += [
        path(
            "login/",
            django.contrib.auth.views.LoginView.as_view(template_name="login.html"),
            name="login",
        ),
        path(
            "logout/",
            CustomOIDCLogoutView.as_view(),
            name="logout",
        ),
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
