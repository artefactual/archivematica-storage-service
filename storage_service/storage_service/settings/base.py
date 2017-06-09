# flake8: noqa

"""Common settings and globals."""

from os import environ
from os.path import abspath, basename, dirname, join, normpath
from sys import path

from django.core.exceptions import ImproperlyConfigured
from django.utils.translation import ugettext_lazy as _


def get_env_variable(var_name):
    """ Get the environment variable or return exception """
    try:
        return environ[var_name]
    except KeyError:
        error_msg = "Set the %s environment variable" % var_name
        raise ImproperlyConfigured(error_msg)


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
TEST_RUNNER = 'django.test.runner.DiscoverRunner'
# ######## END DEBUG CONFIGURATION


# ######## MANAGER CONFIGURATION
# See: https://docs.djangoproject.com/en/dev/ref/settings/#admins
ADMINS = (
    ('Your Name', 'your_email@example.com'),
)

# See: https://docs.djangoproject.com/en/dev/ref/settings/#managers
MANAGERS = ADMINS
# ######## END MANAGER CONFIGURATION

# Lets us know whether we're behind an HTTPS connection
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# ######## GENERAL CONFIGURATION
# See: https://docs.djangoproject.com/en/dev/ref/settings/#time-zone
TIME_ZONE = 'America/Los_Angeles'

# See: https://docs.djangoproject.com/en/dev/ref/settings/#language-code
LANGUAGE_CODE = 'en-us'

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
LOCALE_PATHS = [
    normpath(join(SITE_ROOT, 'locale')),
]

LANGUAGES = [
    ('fr', _('French')),
    ('en', _('English')),
    ('es', _('Spanish')),
]
# ######## END LOCALE CONFIGURATION


# ######## MEDIA CONFIGURATION
# See: https://docs.djangoproject.com/en/dev/ref/settings/#media-root
MEDIA_ROOT = normpath(join(SITE_ROOT, 'media'))

# See: https://docs.djangoproject.com/en/dev/ref/settings/#media-url
MEDIA_URL = '/media/'
# ######## END MEDIA CONFIGURATION


# ######## STATIC FILE CONFIGURATION
# See: https://docs.djangoproject.com/en/dev/ref/settings/#static-root
STATIC_ROOT = normpath(join(SITE_ROOT, 'assets'))

# See: https://docs.djangoproject.com/en/dev/ref/settings/#static-url
STATIC_URL = '/static/'

# See:
# https://docs.djangoproject.com/en/dev/ref/contrib/staticfiles/#std:setting-STATICFILES_DIRS
STATICFILES_DIRS = (
    normpath(join(SITE_ROOT, 'static')),
)

# See:
# https://docs.djangoproject.com/en/dev/ref/contrib/staticfiles/#staticfiles-finders
STATICFILES_FINDERS = (
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
)

STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
# END STATIC FILE CONFIGURATION


# ######## SECRET CONFIGURATION
# See: https://docs.djangoproject.com/en/dev/ref/settings/#secret-key
# Note: This key should only be used for development and testing.
SECRET_KEY = "SECRET_KEY"
# ######## END SECRET CONFIGURATION


# ######## SITE CONFIGURATION
# Hosts/domain names that are valid for this site
# See https://docs.djangoproject.com/en/1.5/ref/settings/#allowed-hosts
ALLOWED_HOSTS = ['*']
# ######## END SITE CONFIGURATION


# ######## FIXTURE CONFIGURATION
# See:
# https://docs.djangoproject.com/en/dev/ref/settings/#std:setting-FIXTURE_DIRS
FIXTURE_DIRS = (
    normpath(join(SITE_ROOT, 'fixtures')),
)
# ######## END FIXTURE CONFIGURATION


# ######## TEMPLATE CONFIGURATION

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [normpath(join(SITE_ROOT, 'templates'))],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.contrib.auth.context_processors.auth',
                'django.template.context_processors.debug',
                'django.template.context_processors.i18n',
                'django.template.context_processors.media',
                'django.template.context_processors.static',
                'django.template.context_processors.tz',
                'django.template.context_processors.request',
                'django.contrib.messages.context_processors.messages',
            ],
            'debug': DEBUG,
        },
    },
]

# ######## END TEMPLATE CONFIGURATION


# ######### AUTHENTICATION CONFIGURATION
# See: https://docs.djangoproject.com/en/dev/ref/settings/#authentication-backends

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
]
# ######### END AUTHENTICATION CONFIGURATION

# ######### MIDDLEWARE CONFIGURATION
# See: https://docs.djangoproject.com/en/dev/ref/settings/#middleware-classes
MIDDLEWARE_CLASSES = [
    # 'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'common.middleware.LoginRequiredMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
# ######## END MIDDLEWARE CONFIGURATION


# ######## URL CONFIGURATION
# See: https://docs.djangoproject.com/en/dev/ref/settings/#root-urlconf
ROOT_URLCONF = '%s.urls' % SITE_NAME
# ######## END URL CONFIGURATION


# ######## APP CONFIGURATION
DJANGO_APPS = [
    # Default Django apps:
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.sites',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Useful template tags:
    # 'django.contrib.humanize',

    # Admin panel and documentation:
    'django.contrib.admin',
    # 'django.contrib.admindocs',
]

THIRD_PARTY_APPS = [
    'tastypie',  # REST framework
    'longerusername', # Longer (> 30 characters) username
]

# Apps specific for this project go here.
LOCAL_APPS = [
    'administration',
    'common',
    'locations',
]

# See: https://docs.djangoproject.com/en/dev/ref/settings/#installed-apps
INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS
# ######## END APP CONFIGURATION


# ######## LOGIN REQUIRED MIDDLEWARE CONFIGURATION
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGIN_EXEMPT_URLS = (
    r'^api/',
    r'^admin/',
    r'^logged-out',
    r'^Shibboleth.sso/',
    r'^login/',
)
# ######## END LOGIN REQUIRED MIDDLEWARE CONFIGURATION


# ######## LOGGING CONFIGURATION
# See: https://docs.djangoproject.com/en/dev/ref/settings/#logging
# A sample logging configuration. The only tangible logging
# performed by this configuration is to send an email to
# the site admins on every HTTP 500 error when DEBUG=False.
# See http://docs.djangoproject.com/en/dev/topics/logging for
# more details on how to customize your logging configuration.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse'
        }
    },
    'formatters': {
        'simple': {
            'format': '%(levelname)-8s  %(name)s.%(funcName)s:  %(message)s',
        },
        'detailed': {
            'format': '%(levelname)-8s  %(asctime)s  %(name)s:%(module)s:%(funcName)s:%(lineno)d:  %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S'
        },
    },
    'handlers': {
        'null': {
            'level': 'DEBUG',
            'class': 'logging.NullHandler'
        },
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'detailed',
        },
        'mail_admins': {
            'level': 'ERROR',
            'filters': ['require_debug_false'],
            'class': 'django.utils.log.AdminEmailHandler'
        },
    },
    'loggers': {
        'django.request': {
            'handlers': ['mail_admins'],
            'level': 'ERROR',
            'propagate': True,
        },
        'django.request.tastypie': {
            'level': 'ERROR',
        },
        'administration': {
            'level': 'DEBUG',
        },
        'common': {
            'level': 'DEBUG',
        },
        'locations': {
            'level': 'DEBUG',
        },
        'sword2': {
            'level': 'INFO',
        }
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
}
# ######## END LOGGING CONFIGURATION


# ######## SESSION CONFIGURATION
# So the cookies don't conflict with archivematica cookies
SESSION_COOKIE_NAME = 'storageapi_sessionid'
# ######## END SESSION CONFIGURATION


# ######## WSGI CONFIGURATION
# See: https://docs.djangoproject.com/en/dev/ref/settings/#wsgi-application
WSGI_APPLICATION = '%s.wsgi.application' % SITE_NAME
# ######## END WSGI CONFIGURATION

ALLOW_USER_EDITS = True


def is_true(env_str):
    return env_str.lower() in ['true', 'yes', 'on', '1']

SHIBBOLETH_AUTHENTICATION = is_true(environ.get('SS_SHIBBOLETH_AUTHENTICATION', ''))
if SHIBBOLETH_AUTHENTICATION:
    SHIBBOLETH_LOGOUT_URL = '/Shibboleth.sso/Logout?target=%s'
    SHIBBOLETH_LOGOUT_REDIRECT_URL = '/logged-out'

    SHIBBOLETH_REMOTE_USER_HEADER = 'HTTP_EPPN'
    SHIBBOLETH_ATTRIBUTE_MAP = {
        # Automatic user fields
        'HTTP_GIVENNAME': (False, 'first_name'),
        'HTTP_SN': (False, 'last_name'),
        'HTTP_MAIL': (False, 'email'),
        # Entitlement field (which we handle manually)
        'HTTP_ENTITLEMENT': (True, 'entitlement'),
    }

    # If the user has this entitlement, they will be a superuser/admin
    SHIBBOLETH_ADMIN_ENTITLEMENT = 'preservation-admin'

    TEMPLATES[0]['OPTIONS']['context_processors'] += [
        'shibboleth.context_processors.logout_link',
    ]

    AUTHENTICATION_BACKENDS += [
        'shibboleth.backends.ShibbolethRemoteUserBackend',
    ]

    # Insert Shibboleth after the authentication middleware
    MIDDLEWARE_CLASSES.insert(
        MIDDLEWARE_CLASSES.index(
            'django.contrib.auth.middleware.AuthenticationMiddleware',
        ) + 1,
        'common.middleware.CustomShibbolethRemoteUserMiddleware',
    )

    INSTALLED_APPS += ['shibboleth']

    ALLOW_USER_EDITS = False
