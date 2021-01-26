# flake8: noqa

"""Common settings and globals."""

from __future__ import absolute_import
import json
import logging
import logging.config
from os import environ
from os.path import abspath, basename, dirname, isfile, join, normpath
from sys import path

from django.core.exceptions import ImproperlyConfigured
from django.utils.translation import ugettext_lazy as _

from storage_service.settings.helpers import get_env_variable, is_true

try:
    import ldap
    from django_auth_ldap import config as ldap_config
except ImportError:
    ldap, ldap_config = None, None


# ######## PATH CONFIGURATION
# Absolute filesystem path to the Django project directory:
DJANGO_ROOT = dirname(dirname(abspath(__file__)))

# Absolute filesystem path to the top-level project folder:
SITE_ROOT = dirname(DJANGO_ROOT)

# Site name:
SITE_NAME = basename(DJANGO_ROOT)

# Add our project to our pythonpath, this way we don't need to type our project
# name in our dotted import paths:
path.append(DJANGO_ROOT)
# ######## END PATH CONFIGURATION


# ######## DEBUG CONFIGURATION
# See: https://docs.djangoproject.com/en/dev/ref/settings/#debug
DEBUG = False

# See: https://docs.djangoproject.com/en/dev/ref/settings/#test-runner
TEST_RUNNER = "django.test.runner.DiscoverRunner"
# ######## END DEBUG CONFIGURATION


# ######## MANAGER CONFIGURATION
# See: https://docs.djangoproject.com/en/dev/ref/settings/#admins
ADMINS = (("Your Name", "your_email@example.com"),)

# See: https://docs.djangoproject.com/en/dev/ref/settings/#managers
MANAGERS = ADMINS
# ######## END MANAGER CONFIGURATION

# Lets us know whether we're behind an HTTPS connection
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# ######## GENERAL CONFIGURATION
# See: https://docs.djangoproject.com/en/dev/ref/settings/#time-zone
TIME_ZONE = environ.get("TIME_ZONE", "America/Los_Angeles")

# See: https://docs.djangoproject.com/en/dev/ref/settings/#language-code
LANGUAGE_CODE = "en-us"

# See: https://docs.djangoproject.com/en/dev/ref/settings/#site-id
SITE_ID = 1

# See: https://docs.djangoproject.com/en/dev/ref/settings/#use-i18n
USE_I18N = True

# See: https://docs.djangoproject.com/en/dev/ref/settings/#use-l10n
USE_L10N = True

# See: https://docs.djangoproject.com/en/dev/ref/settings/#use-tz
USE_TZ = True
# ######## END GENERAL CONFIGURATION


# ######## LOCALE CONFIGURATION
LOCALE_PATHS = [normpath(join(SITE_ROOT, "locale"))]

LANGUAGES = [
    ("en", _("English")),
    ("fr", _("French")),
    ("es", _("Spanish")),
    ("pt-br", _("Brazilian Portuguese")),
    ("no", _("Norwegian")),
]
# ######## END LOCALE CONFIGURATION


# ######## MEDIA CONFIGURATION
# See: https://docs.djangoproject.com/en/dev/ref/settings/#media-root
MEDIA_ROOT = normpath(join(SITE_ROOT, "media"))

# See: https://docs.djangoproject.com/en/dev/ref/settings/#media-url
MEDIA_URL = "/media/"
# ######## END MEDIA CONFIGURATION


# ######## STATIC FILE CONFIGURATION
# See: https://docs.djangoproject.com/en/dev/ref/settings/#static-root
STATIC_ROOT = normpath(join(SITE_ROOT, "assets"))

# See: https://docs.djangoproject.com/en/dev/ref/settings/#static-url
STATIC_URL = "/static/"

# See:
# https://docs.djangoproject.com/en/dev/ref/contrib/staticfiles/#std:setting-STATICFILES_DIRS
STATICFILES_DIRS = (normpath(join(SITE_ROOT, "static")),)

# See:
# https://docs.djangoproject.com/en/dev/ref/contrib/staticfiles/#staticfiles-finders
STATICFILES_FINDERS = (
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
)

STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"
# END STATIC FILE CONFIGURATION


# ######## SECRET CONFIGURATION
# See: https://docs.djangoproject.com/en/dev/ref/settings/#secret-key
# Note: This key should only be used for development and testing.
SECRET_KEY = "SECRET_KEY"
# ######## END SECRET CONFIGURATION


# ######## SITE CONFIGURATION
# Hosts/domain names that are valid for this site
# See https://docs.djangoproject.com/en/1.5/ref/settings/#allowed-hosts
ALLOWED_HOSTS = ["*"]
# ######## END SITE CONFIGURATION


# ######## FIXTURE CONFIGURATION
# See:
# https://docs.djangoproject.com/en/dev/ref/settings/#std:setting-FIXTURE_DIRS
FIXTURE_DIRS = (normpath(join(SITE_ROOT, "fixtures")),)
# ######## END FIXTURE CONFIGURATION


# ######## TEMPLATE CONFIGURATION

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [normpath(join(SITE_ROOT, "templates"))],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.contrib.auth.context_processors.auth",
                "django.template.context_processors.debug",
                "django.template.context_processors.i18n",
                "django.template.context_processors.media",
                "django.template.context_processors.static",
                "django.template.context_processors.tz",
                "django.template.context_processors.request",
                "django.contrib.messages.context_processors.messages",
                "common.context_processors.auth_methods",
            ],
            "debug": DEBUG,
        },
    }
]

# ######## END TEMPLATE CONFIGURATION


# ######### AUTHENTICATION CONFIGURATION
# See: https://docs.djangoproject.com/en/dev/ref/settings/#authentication-backends
AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend"]

from .components.auth import *

# ######### END AUTHENTICATION CONFIGURATION

# ######### MIDDLEWARE CONFIGURATION
# See: https://docs.djangoproject.com/en/dev/ref/settings/#middleware-classes
MIDDLEWARE = [
    # 'django.middleware.security.SecurityMiddleware',
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    # Automatic language selection is disabled.
    # See #723 for more details.
    "common.middleware.ForceDefaultLanguageMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "common.middleware.LoginRequiredMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

AUDIT_LOG_MIDDLEWARE = is_true(environ.get("SS_AUDIT_LOG_MIDDLEWARE", "false"))
if AUDIT_LOG_MIDDLEWARE:
    MIDDLEWARE.append("common.middleware.AuditLogMiddleware")
# ######## END MIDDLEWARE CONFIGURATION


# ######## URL CONFIGURATION
# See: https://docs.djangoproject.com/en/dev/ref/settings/#root-urlconf
ROOT_URLCONF = "%s.urls" % SITE_NAME
# ######## END URL CONFIGURATION


# ######## APP CONFIGURATION
DJANGO_APPS = [
    # Default Django apps:
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.sites",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Useful template tags:
    # 'django.contrib.humanize',
    # Admin panel and documentation:
    "django.contrib.admin",
    # 'django.contrib.admindocs',
    "django.forms",
]

THIRD_PARTY_APPS = ["tastypie"]  # REST framework

# Apps specific for this project go here.
LOCAL_APPS = ["administration", "common", "locations"]

# See: https://docs.djangoproject.com/en/dev/ref/settings/#installed-apps
INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS
# ######## END APP CONFIGURATION


# ######## LOGIN REQUIRED MIDDLEWARE CONFIGURATION
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"
LOGIN_EXEMPT_URLS = (r"^api/", r"^admin/", r"^Shibboleth.sso/", r"^login/")
# ######## END LOGIN REQUIRED MIDDLEWARE CONFIGURATION


# ######## LOGGING CONFIGURATION
# See http://docs.djangoproject.com/en/dev/topics/logging for
# more details on how to customize your logging configuration.

# Configure logging manually
LOGGING_CONFIG = None

# Location of the logging configuration file that we're going to pass to
# `logging.config.fileConfig` unless it doesn't exist.
LOGGING_CONFIG_FILE = "/etc/archivematica/storageService.logging.json"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"require_debug_false": {"()": "django.utils.log.RequireDebugFalse"}},
    "formatters": {
        "simple": {"format": "%(levelname)-8s  %(name)s.%(funcName)s:  %(message)s"},
        "detailed": {
            "format": "%(levelname)-8s  %(asctime)s  %(name)s:%(module)s:%(funcName)s:%(lineno)d:  %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "null": {"level": "DEBUG", "class": "logging.NullHandler"},
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "detailed",
        },
        "mail_admins": {
            "level": "ERROR",
            "filters": ["require_debug_false"],
            "class": "django.utils.log.AdminEmailHandler",
        },
    },
    "loggers": {
        "django.request": {
            "handlers": ["mail_admins"],
            "level": "ERROR",
            "propagate": True,
        },
        "django.request.tastypie": {"level": "ERROR"},
        "administration": {"level": "DEBUG"},
        "common": {"level": "DEBUG"},
        "locations": {"level": "DEBUG"},
        "sword2": {"level": "INFO"},
    },
    "root": {"handlers": ["console"], "level": "WARNING"},
}

if isfile(LOGGING_CONFIG_FILE):
    with open(LOGGING_CONFIG_FILE, "rt") as f:
        LOGGING = logging.config.dictConfig(json.load(f))
else:
    logging.config.dictConfig(LOGGING)
# ######## END LOGGING CONFIGURATION


# ######## SESSION CONFIGURATION
# So the cookies don't conflict with archivematica cookies
SESSION_COOKIE_NAME = "storageapi_sessionid"
# ######## END SESSION CONFIGURATION


# ######## WSGI CONFIGURATION
# See: https://docs.djangoproject.com/en/dev/ref/settings/#wsgi-application
WSGI_APPLICATION = "%s.wsgi.application" % SITE_NAME
# ######## END WSGI CONFIGURATION

ALLOW_USER_EDITS = True


######### LDAP CONFIGURATION #########
LDAP_AUTHENTICATION = is_true(environ.get("SS_LDAP_AUTHENTICATION", ""))
if LDAP_AUTHENTICATION:
    if ldap is None or ldap_config is None:
        raise ImproperlyConfigured(
            "python-ldap and django-auth-ldap must be installed to use LDAP authentication."
        )

    # LDAP Backend should come before ModelBackend
    AUTHENTICATION_BACKENDS.insert(0, "django_auth_ldap.backend.LDAPBackend")

    AUTH_LDAP_SERVER_URI = environ.get("AUTH_LDAP_SERVER_URI", "ldap://localhost")
    AUTH_LDAP_BIND_DN = environ.get("AUTH_LDAP_BIND_DN", "")
    AUTH_LDAP_BIND_PASSWORD = environ.get("AUTH_LDAP_BIND_PASSWORD", "")

    if "AUTH_LDAP_USER_SEARCH_BASE_DN" in environ:
        AUTH_LDAP_USER_SEARCH = ldap_config.LDAPSearch(
            environ.get("AUTH_LDAP_USER_SEARCH_BASE_DN"),
            ldap.SCOPE_SUBTREE,
            environ.get("AUTH_LDAP_USER_SEARCH_BASE_FILTERSTR", "(uid=%(user)s)"),
        )
    AUTH_LDAP_USER_DN_TEMPLATE = environ.get("AUTH_LDAP_USER_DN_TEMPLATE", None)
    AUTH_LDAP_USER_ATTR_MAP = {
        "first_name": "givenName",
        "last_name": "sn",
        "email": "mail",
    }

    AUTH_LDAP_USER_FLAGS_BY_GROUP = {}
    if "AUTH_LDAP_GROUP_IS_ACTIVE" in environ:
        AUTH_LDAP_USER_FLAGS_BY_GROUP["is_active"] = environ.get(
            "AUTH_LDAP_GROUP_IS_ACTIVE"
        )
    if "AUTH_LDAP_GROUP_IS_STAFF" in environ:
        AUTH_LDAP_USER_FLAGS_BY_GROUP["is_staff"] = environ.get(
            "AUTH_LDAP_GROUP_IS_STAFF"
        )
    if "AUTH_LDAP_GROUP_IS_SUPERUSER" in environ:
        AUTH_LDAP_USER_FLAGS_BY_GROUP["is_superuser"] = environ.get(
            "AUTH_LDAP_GROUP_IS_SUPERUSER"
        )

    if "AUTH_LDAP_GROUP_SEARCH_BASE_DN" in environ:
        AUTH_LDAP_GROUP_SEARCH = ldap_config.LDAPSearch(
            base_dn=environ.get("AUTH_LDAP_GROUP_SEARCH_BASE_DN", ""),
            scope=ldap.SCOPE_SUBTREE,
            filterstr=environ.get("AUTH_LDAP_GROUP_SEARCH_FILTERSTR", ""),
        )

    # https://pythonhosted.org/django-auth-ldap/groups.html#types-of-groups
    AUTH_LDAP_GROUP_TYPE = ldap_config.ActiveDirectoryGroupType()

    AUTH_LDAP_REQUIRE_GROUP = environ.get("AUTH_LDAP_REQUIRE_GROUP", None)
    AUTH_LDAP_DENY_GROUP = environ.get("AUTH_LDAP_DENY_GROUP", None)

    AUTH_LDAP_FIND_GROUP_PERMS = is_true(
        environ.get("AUTH_LDAP_FIND_GROUP_PERMS", "FALSE")
    )
    AUTH_LDAP_CACHE_GROUPS = is_true(environ.get("AUTH_LDAP_CACHE_GROUPS", "FALSE"))
    try:
        AUTH_LDAP_GROUP_CACHE_TIMEOUT = int(
            environ.get("AUTH_LDAP_GROUP_CACHE_TIMEOUT", "3600")
        )
    except ValueError:
        AUTH_LDAP_GROUP_CACHE_TIMEOUT = 3600

    AUTH_LDAP_START_TLS = is_true(environ.get("AUTH_LDAP_START_TLS", "TRUE"))

    AUTH_LDAP_GLOBAL_OPTIONS = {}
    if environ.get("AUTH_LDAP_PROTOCOL_VERSION", None) == "3":
        AUTH_LDAP_GLOBAL_OPTIONS[ldap.OPT_PROTOCOL_VERSION] = ldap.VERSION3
    if environ.get("AUTH_LDAP_TLS_CACERTFILE", None):
        AUTH_LDAP_GLOBAL_OPTIONS[ldap.OPT_X_TLS_CACERTFILE] = environ.get(
            "AUTH_LDAP_TLS_CACERTFILE"
        )
    if environ.get("AUTH_LDAP_TLS_CERTFILE", None):
        AUTH_LDAP_GLOBAL_OPTIONS[ldap.OPT_X_TLS_CERTFILE] = environ.get(
            "AUTH_LDAP_TLS_CERTFILE"
        )
    if environ.get("AUTH_LDAP_TLS_KEYFILE", None):
        AUTH_LDAP_GLOBAL_OPTIONS[ldap.OPT_X_TLS_KEYFILE] = environ.get(
            "AUTH_LDAP_TLS_KEYFILE"
        )
    if environ.get("AUTH_LDAP_TLS_REQUIRE_CERT", None):
        require_cert = environ.get("AUTH_LDAP_TLS_REQUIRE_CERT").lower()
        if require_cert == "never":
            AUTH_LDAP_GLOBAL_OPTIONS[ldap.OPT_X_TLS_REQUIRE_CERT] = ldap.OPT_X_TLS_NEVER
        elif require_cert == "allow":
            AUTH_LDAP_GLOBAL_OPTIONS[ldap.OPT_X_TLS_REQUIRE_CERT] = ldap.OPT_X_TLS_ALLOW
        elif require_cert == "try":
            AUTH_LDAP_GLOBAL_OPTIONS[ldap.OPT_X_TLS_REQUIRE_CERT] = ldap.OPT_X_TLS_TRY
        elif require_cert == "demand":
            AUTH_LDAP_GLOBAL_OPTIONS[
                ldap.OPT_X_TLS_REQUIRE_CERT
            ] = ldap.OPT_X_TLS_DEMAND
        elif require_cert == "hard":
            AUTH_LDAP_GLOBAL_OPTIONS[ldap.OPT_X_TLS_REQUIRE_CERT] = ldap.OPT_X_TLS_HARD
        else:
            raise ImproperlyConfigured(
                (
                    "Unexpected value for AUTH_LDAP_TLS_REQUIRE_CERT: {}. "
                    "Supported values: 'never', 'allow', try', 'hard', or 'demand'."
                ).format(require_cert)
            )
    # Non-configurable sane defaults
    AUTH_LDAP_ALWAYS_UPDATE_USER = True

######### END LDAP CONFIGURATION #########


SHIBBOLETH_AUTHENTICATION = is_true(environ.get("SS_SHIBBOLETH_AUTHENTICATION", ""))
if SHIBBOLETH_AUTHENTICATION:
    SHIBBOLETH_LOGOUT_URL = "/Shibboleth.sso/Logout?target=%s"

    SHIBBOLETH_REMOTE_USER_HEADER = "HTTP_EPPN"
    SHIBBOLETH_ATTRIBUTE_MAP = {
        # Automatic user fields
        "HTTP_GIVENNAME": (False, "first_name"),
        "HTTP_SN": (False, "last_name"),
        "HTTP_MAIL": (False, "email"),
        # Entitlement field (which we handle manually)
        "HTTP_ENTITLEMENT": (True, "entitlement"),
    }

    # If the user has this entitlement, they will be a superuser/admin
    SHIBBOLETH_ADMIN_ENTITLEMENT = "preservation-admin"

    TEMPLATES[0]["OPTIONS"]["context_processors"] += [
        "shibboleth.context_processors.logout_link"
    ]

    AUTHENTICATION_BACKENDS += ["shibboleth.backends.ShibbolethRemoteUserBackend"]

    # Insert Shibboleth after the authentication middleware
    MIDDLEWARE.insert(
        MIDDLEWARE.index("django.contrib.auth.middleware.AuthenticationMiddleware") + 1,
        "common.middleware.CustomShibbolethRemoteUserMiddleware",
    )

    INSTALLED_APPS += ["shibboleth"]

    ALLOW_USER_EDITS = False

######### CAS CONFIGURATION #########
CAS_AUTHENTICATION = is_true(environ.get("SS_CAS_AUTHENTICATION", ""))
if CAS_AUTHENTICATION:
    # CAS circumvents the Storage Service login screen and prevents
    # usage of other authentication methods, so we raise an exception
    # if a single sign-on option other than CAS is enabled.
    if SHIBBOLETH_AUTHENTICATION or LDAP_AUTHENTICATION:
        raise ImproperlyConfigured(
            "CAS authentication is not supported in tandem with other single "
            "sign-on methods. Please disable other Archivematica SSO settings "
            "(e.g. Shibboleth, LDAP) before proceeding."
        )

    # We default to a live demo CAS server to facilitate QA and
    # regression testing. The following credentials can be used to
    # authenticate:
    # Username: admin
    # Password: django-cas-ng
    CAS_DEMO_SERVER_URL = "https://django-cas-ng-demo-server.herokuapp.com/cas/"
    CAS_SERVER_URL = environ.get("AUTH_CAS_SERVER_URL", CAS_DEMO_SERVER_URL)

    ALLOWED_CAS_VERSION_VALUES = ("1", "2", "3", "CAS_2_SAML_1_0")

    CAS_VERSION = environ.get("AUTH_CAS_PROTOCOL_VERSION", "3")
    if CAS_VERSION not in ALLOWED_CAS_VERSION_VALUES:
        raise ImproperlyConfigured(
            (
                "Unexpected value for AUTH_CAS_PROTOCOL_VERSION: {}. "
                "Supported values: '1', '2', '3', or 'CAS_2_SAML_1_0'."
            ).format(CAS_VERSION)
        )

    CAS_CHECK_ADMIN_ATTRIBUTES = environ.get("AUTH_CAS_CHECK_ADMIN_ATTRIBUTES", False)
    CAS_ADMIN_ATTRIBUTE = environ.get("AUTH_CAS_ADMIN_ATTRIBUTE", None)
    CAS_ADMIN_ATTRIBUTE_VALUE = environ.get("AUTH_CAS_ADMIN_ATTRIBUTE_VALUE", None)

    CAS_AUTOCONFIGURE_EMAIL = environ.get("AUTH_CAS_AUTOCONFIGURE_EMAIL", False)
    CAS_EMAIL_DOMAIN = environ.get("AUTH_CAS_EMAIL_DOMAIN", None)

    CAS_LOGIN_MSG = None
    CAS_LOGIN_URL_NAME = "login"
    CAS_LOGOUT_URL_NAME = "logout"

    AUTHENTICATION_BACKENDS += ["common.backends.CustomCASBackend"]

    # Insert CAS after the authentication middleware
    MIDDLEWARE.insert(
        MIDDLEWARE.index("django.contrib.auth.middleware.AuthenticationMiddleware") + 1,
        "django_cas_ng.middleware.CASMiddleware",
    )

    INSTALLED_APPS += ["django_cas_ng"]

    ALLOW_USER_EDITS = False

######### END CAS CONFIGURATION #########

OIDC_AUTHENTICATION = is_true(environ.get("SS_OIDC_AUTHENTICATION", ""))
if OIDC_AUTHENTICATION:
    ALLOW_USER_EDITS = False

    AUTHENTICATION_BACKENDS += ["common.backends.CustomOIDCBackend"]
    LOGIN_EXEMPT_URLS.append(r"^oidc")
    INSTALLED_APPS += ["mozilla_django_oidc"]

    # AUTH_SERVER = 'https://login.microsoftonline.com/common/v2.0/'
    OIDC_RP_CLIENT_ID = environ.get("OIDC_RP_CLIENT_ID", "")
    OIDC_RP_CLIENT_SECRET = environ.get("OIDC_RP_CLIENT_SECRET", "")

    OIDC_OP_AUTHORIZATION_ENDPOINT = ""
    OIDC_OP_TOKEN_ENDPOINT = ""
    OIDC_OP_USER_ENDPOINT = ""
    OIDC_OP_JWKS_ENDPOINT = ""

    AZURE_TENANT_ID = environ.get("AZURE_TENANT_ID", "")
    if AZURE_TENANT_ID:
        OIDC_OP_AUTHORIZATION_ENDPOINT = (
            "https://login.microsoftonline.com/%s/oauth2/v2.0/authorize"
            % AZURE_TENANT_ID
        )
        OIDC_OP_TOKEN_ENDPOINT = (
            "https://login.microsoftonline.com/%s/oauth2/v2.0/token" % AZURE_TENANT_ID
        )
        OIDC_OP_USER_ENDPOINT = (
            "https://login.microsoftonline.com/%s/openid/userinfo" % AZURE_TENANT_ID
        )
        OIDC_OP_JWKS_ENDPOINT = (
            "https://login.microsoftonline.com/%s/discovery/v2.0/keys" % AZURE_TENANT_ID
        )
    else:
        OIDC_OP_AUTHORIZATION_ENDPOINT = environ["OIDC_OP_AUTHORIZATION_ENDPOINT"]
        OIDC_OP_TOKEN_ENDPOINT = environ["OIDC_OP_TOKEN_ENDPOINT"]
        OIDC_OP_USER_ENDPOINT = environ["OIDC_OP_USER_ENDPOINT"]
        OIDC_OP_JWKS_ENDPOINT = environ.get("OIDC_OP_JWKS_ENDPOINT", "")

    OIDC_RP_SIGN_ALGO = environ.get("OIDC_RP_SIGN_ALGO", "HS256")

    # Username is email address
    OIDC_USERNAME_ALGO = lambda email: email

    # map attributes from access token
    OIDC_ACCESS_ATTRIBUTE_MAP = {"given_name": "first_name", "family_name": "last_name"}

    # map attributes from id token
    OIDC_ID_ATTRIBUTE_MAP = {"email": "email"}

# WARNING: if Gunicorn is being used to serve the Storage Service and its
# worker class is set to `gevent`, then BagIt validation must use 1 process.
# Otherwise, calls to `validate` will hang because of the incompatibility
# between gevent and multiprocessing (BagIt) concurrency strategies. See
# https://github.com/artefactual/archivematica/issues/708
try:
    BAG_VALIDATION_NO_PROCESSES = int(environ.get("SS_BAG_VALIDATION_NO_PROCESSES", 1))
except ValueError:
    BAG_VALIDATION_NO_PROCESSES = 1

GNUPG_HOME_PATH = environ.get("SS_GNUPG_HOME_PATH", None)

# SS uses a Python HTTP library called requests. If this setting is set to True,
# we will skip the SSL certificate verification process. Read more here:
# http://docs.python-requests.org/en/master/user/advanced/#ssl-cert-verification
# This setting is honored in:
# - locations.models.pipeline
# - locations.models.dspace
INSECURE_SKIP_VERIFY = is_true(environ.get("SS_INSECURE_SKIP_VERIFY", ""))

PROMETHEUS_ENABLED = is_true(environ.get("SS_PROMETHEUS_ENABLED", ""))
if PROMETHEUS_ENABLED:
    MIDDLEWARE = (
        ["django_prometheus.middleware.PrometheusBeforeMiddleware"]
        + MIDDLEWARE
        + ["django_prometheus.middleware.PrometheusAfterMiddleware"]
    )
    INSTALLED_APPS = INSTALLED_APPS + ["django_prometheus"]
    LOGIN_EXEMPT_URLS = LOGIN_EXEMPT_URLS + (r"^metrics$",)
