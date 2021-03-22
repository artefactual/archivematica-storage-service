# Storage Service Configuration

## Table of contents

- [Storage Service Configuration](#storage-service-configuration)
  - [Table of contents](#table-of-contents)
  - [Introduction](#introduction)
  - [Environment variables](#environment-variables)
    - [Application-specific environment variables](#application-specific-environment-variables)
    - [Gunicorn-specific environment variables](#gunicorn-specific-environment-variables)
    - [LDAP-specific environment variables](#ldap-specific-environment-variables)
    - [CAS-specific environment variables](#cas-specific-environment-variables)
  - [Logging configuration](#logging-configuration)

## Introduction

The configuration system in Storage Service is based on the following pattern:

1. **Environment variables** - setting a configuration parameter with an
   environment variable will override all other methods.
1. **Application defaults**  - if the parameter is not set in an environment
   variable or the config file, the application default is used.

Logging behaviour is configured differently, and provides two methods:

1. **`logging.json` file** - if a JSON file is present in the default location,
    the contents of the JSON file will control the components logging behaviour.
1. **Application default** - if no JSON file is present, the default logging
   behaviour is to write to standard streams (standard out and standard error).

## Environment variables

The value of an environment variable is a string of characters. The
configuration system coerces the value to the types supported:

- `string` (e.g. `"foobar"`)
- `int` (e.g. `"60"`)
- `float` (e.g. `"1.20"`)
- `boolean` where truth values can be represented as follows (checked in a
  case-insensitive manner):
  - True (enabled):  `"1"`, `"yes"`, `"true"` or `"on"`
  - False (disabled): `"0"`, `"no"`, `"false"` or `"off"`

Certain environment strings are mandatory, i.e. they don't have defaults and
the application will refuse to start if the user does not provide one.

Please be aware that Archivematica supports different types of distributions
(Ubuntu/CentOS packages, Ansible or Docker images) and they may override some
of these settings or provide values to mandatory fields.

### Application-specific environment variables

- **`DJANGO_SETTINGS_MODULE`**:
    - **Description:** the [settings module](https://docs.djangoproject.com/en/1.8/ref/settings/#secret-key) used by Django. There are three modules available: [storage_service.settings.production](../storage_service/storage_service/settings/production.py), [storage_service.settings.local](../storage_service/storage_service/settings/local.py) and [storage_service.settings.test](../storage_service/storage_service/settings/test.py). Unless you are a developer you should only use the former.
    - **Type:** `string`
    - :red_circle: **Mandatory!**

- **`DJANGO_ALLOWED_HOSTS`**:
    - **Description:** comma-separated list of hosts or domain names that this Django site can serve. See the [official docs](https://docs.djangoproject.com/en/1.8/ref/settings/#allowed-hosts).
    - **Type:** `string`
    - :red_circle: **Mandatory!**

- **`TIME_ZONE`**:
    - **Description:** application time zone. See [TIME_ZONE](https://docs.djangoproject.com/en/1.8/ref/settings/#time-zone) for more details.
    - **Type:** `string`
    - **Default:** `"America/Los_Angeles"`

- **`SECRET_KEY`**:
    - **Description:** a secret key used for cryptographic signing. See [SECRET_KEY](https://docs.djangoproject.com/en/1.8/ref/settings/#secret-key) for more details.
    - **Type:** `string`
    - :red_circle: **Mandatory!**

- **`SS_AUTH_PASSWORD_MINIMUM_LENGTH`**:
    - **Description:** sets minimum length for user passwords.
    - **Type:** `integer`
    - **Default:** `8`

- **`SS_AUTH_PASSWORD_DISABLE_COMMON_VALIDATION`**:
    - **Description:** disables password validation that prevents users from using passwords that occur in a list of common passwords.
    - **Type:** `boolean`
    - **Default:** `false`

- **`SS_AUTH_PASSWORD_DISABLE_USER_ATTRIBUTE_SIMILARITY_VALIDATION`**:
    - **Description:** disables password validation that prevents users from using passwords that are too similar to their username and other user attributes.
    - **Type:** `boolean`
    - **Default:** `false`

- **`SS_AUTH_PASSWORD_DISABLE_COMPLEXITY_VALIDATION`**:
    - **Description:** disables password validation that checks that passwords contain at least three of: lower-case characters, upper-case characters, numbers, special characters.
    - **Type:** `boolean`
    - **Default:** `false`

- **`SS_SHIBBOLETH_AUTHENTICATION`**:
    - **Description:** enables the Shibboleth authentication system. Other settings related to Shibboleth cannot be defined via environment variables at the moment, please edit [storage_service.settings.base](../storage_service/storage_service/settings/base.py) manually.
    - **Type:** `boolean`
    - **Default:** `false`

- **`SS_CAS_AUTHENTICATION`**:
    - **Description:** enables the CAS (Central Authentication Service) authentication system.
    - **Type:** `boolean`
    - **Default:** `false`

- **`SS_BAG_VALIDATION_NO_PROCESSES`**:
    - **Description:** number of concurrent processes used by BagIt. If Gunicorn is being used to serve the Storage Service and its worker class is set to `gevent`, then BagIt validation must use 1 process. Otherwise, calls to `validate` will hang because of the incompatibility between gevent and multiprocessing (BagIt) concurrency strategies. See [#708](https://github.com/artefactual/archivematica/issues/708).
    - **Type:** `int`
    - **Default:** `1`

- **`SS_GNUPG_HOME_PATH`**:
    - **Description:** path of the GnuPG home directory. If this environment string is not defined Storage Service will use its internal location directory.
    - **Type:** `string`
    - **Default:** `None`

- **`SS_INSECURE_SKIP_VERIFY`**:
    - **Description:** skip the SSL certificate verification process. This setting should not be used in production environments.
    - **Type:** `boolean`
    - **Default:** `false`

- **`SS_PROMETHEUS_ENABLED`**:
    - **Description:** enable metrics export for collection by Prometheus.
    - **Type:** `boolean`
    - **Default:** `false`

- **`SS_AUDIT_LOG_MIDDLEWARE`**:
    - **Description:** enable X-Username header with authenticated HTTP responses.
    - **Type:** `boolean`
    - **Default:** `false`

- **`SS_S3_TIMEOUTS`**:
    - **Description:** read and connect timeouts for S3 matching your implementation's recommended defaults.
    - **Type:** `integer`
    - **Default:** `900`

The configuration of the database is also declared via environment variables. Storage Service looks up the `SS_DB_URL` environment string. If defined, its value is expected to follow the form described in the [dj-database-url docs](https://github.com/kennethreitz/dj-database-url#url-schema), e.g.: `mysql://username:password@192.168.1.20:3306/storage_service`. If undefined, Storage Service defaults to the `django.db.backends.sqlite3` [engine](https://docs.djangoproject.com/en/1.8/ref/settings/#engine) and expects the following environment variables to be defined:

- **`SS_DB_NAME`**:
    - **Description:** see [the official description](https://docs.djangoproject.com/en/1.8/ref/settings/#name).
    - **Type:** `string`

- **`SS_DB_PASSWORD`**:
    - **Description:**  see [the official description](https://docs.djangoproject.com/en/1.8/ref/settings/#password).
    - **Type:** `string`

- **`SS_DB_HOST`**:
    - **Description:**  see [the official description](https://docs.djangoproject.com/en/1.8/ref/settings/#host).
    - **Type:** `string`

There are a limited number of email settings that can be populated via
environment variables - we are hoping to improve this soon (see
[#813](https://github.com/artefactual/archivematica/pull/813)). We have some
settings hard-coded (see [storage_service.settings.production](../storage_service/storage_service/settings/production.py)).
This is the current list of strings supported:

- **`EMAIL_BACKEND`**:
    - **Description:** https://docs.djangoproject.com/en/dev/ref/settings/#email-backend
    - **Type:** `string`
    - **Default:** `django.core.mail.backends.smtp.EmailBackend`

- **`EMAIL_HOST`**
    - **Description:** https://docs.djangoproject.com/en/dev/ref/settings/#email-host
    - **Type:** `string`
    - **Default:** `smtp.gmail.com`

- **`EMAIL_HOST_PASSWORD`**
    - **Description:** https://docs.djangoproject.com/en/dev/ref/settings/#email-host-password
    - **Type:** `string`
    - **Default:** (empty string)

- **`EMAIL_HOST_USER`**
    - **Description:** https://docs.djangoproject.com/en/dev/ref/settings/#email-host-user
    - **Type:** `string`
    - **Default:** `your_email@example.com`

- **`EMAIL_PORT`**
    - **Description:** https://docs.djangoproject.com/en/dev/ref/settings/#email-port
    - **Type:** `int`
    - **Default:** `587`

- **`EMAIL_SUBJECT_PREFIX`**
    - **Description:** https://docs.djangoproject.com/en/dev/ref/settings/#email-subject-prefix
    - **Type:** `string`
    - **Default:** `[Archivematica Storage Service] `

- **`DEFAULT_FROM_EMAIL`**
    - **Description:** https://docs.djangoproject.com/en/dev/ref/settings/#default-from-email
    - **Type:** `string`
    - **Default:** `webmaster@localhost`

- **`EMAIL_USE_TLS`**
    - **Description:** https://docs.djangoproject.com/en/dev/ref/settings/#email-use-tls
    - **Type:** `boolean`
    - **Default:** `true`

### Gunicorn-specific environment variables

- **`SS_GUNICORN_USER`**:
    - **Description:** OS user for gunicorn worker processes to run as. See [USER](http://docs.gunicorn.org/en/stable/settings.html#user).
    - **Type:** `integer` (user id) or `string` (user name)
    - **Default:** `archivematica`

- **`SS_GUNICORN_GROUP`**:
    - **Description:** OS group for gunicorn worker processes to run as. See [GROUP](http://docs.gunicorn.org/en/styable/settings.html#group).
    - **Type:** `integer` (group id) or `string` (group name)
    - **Default:** `archivematica`

- **`SS_GUNICORN_BIND`**:
    - **Description:** the socket for gunicorn to bind to. See [BIND](http://docs.gunicorn.org/en/stable/settings.html#bind).
    - **Type:** `string` (host name or ip with port number)
    - **Default:** `127.0.0.1:8001`

- **`SS_GUNICORN_WORKERS`**:
    - **Description:** number of gunicorn worker processes to run. See [WORKERS](http://docs.gunicorn.org/en/stable/settings.html#workers). If `SS_GUNICORN_WORKER_CLASS` is set to `gevent`, then `SS_BAG_VALIDATION_NO_PROCESSES` **must** be set to `1`. Otherwise reingest will fail at bagit validate. See [#708](https://github.com/artefactual/archivematica/issues/708).
    - **Type:** `integer`
    - **Default:** `1`

- **`SS_GUNICORN_WORKER_CLASS`**:
    - **Description:** the type of worker processes to run. See [WORKER-CLASS](http://docs.gunicorn.org/en/stable/settings.html#worker-class).
    - **Type:** `string`
    - **Default:** `gevent`

- **`SS_GUNICORN_TIMEOUT`**:
    - **Description:** worker process timeout. See [TIMEOUT](http://docs.gunicorn.org/en/stable/settings.html#timeout).
    - **Type:** `integer` (seconds)
    - **Default:** `172800`

- **`SS_GUNICORN_RELOAD`**:
    - **Description:** restart workers when code changes. See [RELOAD](http://docs.gunicorn.org/en/stable/settings.html#reload).
    - **Type:** `boolean`
    - **Default:** `false`

- **`SS_GUNICORN_RELOAD_ENGINE`**:
    - **Description:** method of performing reload. See [RELOAD-ENGINE](http://docs.gunicorn.org/en/stable/settings.html#reload-engine).
    - **Type:** `string`
    - **Default:** `auto`

- **`SS_GUNICORN_CHDIR`**:
    - **Description:** directory to load apps from. See [CHDIR](http://docs.gunicorn.org/en/stable/settings.html#chdir).
    - **Type:** `string`
    - **Default:** `/usr/lib/archivematica/storage-service`

- **`SS_GUNICORN_ACCESSLOG`**:
    - **Description:** location to write access log to. See [ACCESSLOG](http://docs.gunicorn.org/en/stable/settings.html#accesslog).
    - **Type:** `string`
    - **Default:** `/dev/null`

- **`SS_GUNICORN_ERRORLOG`**:
    - **Description:** location to write error log to. See [ERRORLOG](http://docs.gunicorn.org/en/stable/settings.html#errorlog).
    - **Type:** `string`
    - **Default:** `-`

- **`SS_GUNICORN_LOGLEVEL`**:
    - **Description:** the granularity of Error log outputs. See [LOGLEVEL](http://docs.gunicorn.org/en/stable/settings.html#loglevel).
    - **Type:** `string`
    - **Default:** `INFO`

- **`SS_GUNICORN_PROC_NAME`**:
    - **Description:** name for this instance of gunicorn. See [PROC-NAME](http://docs.gunicorn.org/en/stable/settings.html#proc-name).
    - **Type:** `string`
    - **Default:** `archivematica-storage-service`

### LDAP-specific environment variables

These variables specify the behaviour of LDAP authentication. If `SS_LDAP_AUTHENTICATION` is false, none of the other ones are used.

- **`SS_LDAP_AUTHENTICATION`**:
    - **Description:** Enables user authentication via LDAP.
    - **Type:** `boolean`
    - **Default:** `false`

- **`AUTH_LDAP_SERVER_URI`**:
    - **Description:** Address of the LDAP server to authenticate against.
    - **Type:** `string`
    - **Default:** `ldap://localhost`

- **`AUTH_LDAP_BIND_DN`**:
    - **Description:** LDAP "bind DN"; the object to authenticate against the LDAP server with, in order
    to lookup users, e.g. "cn=admin,dc=example,dc=com".  Empty string for anonymous.
    - **Type:** `string`
    - **Default:** `''`

- **`AUTH_LDAP_BIND_PASSWORD`**:
    - **Description:** Password for the LDAP bind DN.
    - **Type:** `string`
    - **Default:** `''`

- **`AUTH_LDAP_USER_SEARCH_BASE_DN`**:
    - **Description:** Base LDAP DN for user search, e.g. "ou=users,dc=example,dc=com".
    - **Type:** `string`
    - **Default:** `''`

- **`AUTH_LDAP_USER_SEARCH_BASE_FILTERSTR`**:
    - **Description:** Filter for identifying LDAP user objects, e.g. "(uid=%(user)s)". The `%(user)s`
    portion of the string will be replaced by the username. This variable is only used if
    `AUTH_LDAP_USER_SEARCH_BASE_DN` is not empty.
    - **Type:** `string`
    - **Default:** `(uid=%(user)s)`

- **`AUTH_LDAP_USER_DN_TEMPLATE`**:
    - **Description:** Template for LDAP user search, e.g. "uid=%(user)s,ou=users,dc=example,dc=com".
    Not applicable if `AUTH_LDAP_USER_SEARCH_BASE_DN` is set.
    - **Type:** `string`
    - **Default:** `''`

- **`AUTH_LDAP_GROUP_IS_ACTIVE`**:
    - **Description:** Template for LDAP group used to set the Django user `is_active` flag, e.g.
    "cn=active,ou=django,ou=groups,dc=example,dc=com".
    - **Type:** `string`
    - **Default:** `''`

- **`AUTH_LDAP_GROUP_IS_STAFF`**:
    - **Description:** Template for LDAP group used to set the Django user `is_staff` flag, e.g.
    "cn=staff,ou=django,ou=groups,dc=example,dc=com".
    - **Type:** `string`
    - **Default:** `''`

- **`AUTH_LDAP_GROUP_IS_SUPERUSER`**:
    - **Description:** Template for LDAP group used to set the Django user `is_superuser` flag, e.g.
    "cn=admins,ou=django,ou=groups,dc=example,dc=com".
    - **Type:** `string`
    - **Default:** `''`

- **`AUTH_LDAP_GROUP_SEARCH_BASE_DN`**:
    - **Description:** Base LDAP DN for group search, e.g. "ou=django,ou=groups,dc=example,dc=com".
    - **Type:** `string`
    - **Default:** `''`

- **`AUTH_LDAP_GROUP_SEARCH_FILTERSTR`**:
    - **Description:** Filter for identifying LDAP group objects, e.g. "(objectClass=groupOfNames)".
    This variable is only used if `AUTH_LDAP_GROUP_SEARCH_BASE_DN` is not empty.
    - **Type:** `string`
    - **Default:** `''`

- **`AUTH_LDAP_REQUIRE_GROUP`**:
    - **Description:** Filter for a group that LDAP users must belong to in order to authenticate, e.g.
    "cn=enabled,ou=django,ou=groups,dc=example,dc=com"
    - **Type:** `string`
    - **Default:** `''`

- **`AUTH_LDAP_DENY_GROUP`**:
    - **Description:** Filter for a group that LDAP users must _not_ belong to in order to authenticate,
    e.g. "cn=disabled,ou=django,ou=groups,dc=example,dc=com"
    - **Type:** `string`
    - **Default:** `''`

- **`AUTH_LDAP_FIND_GROUP_PERMS`**:
    - **Description:** If we should use LDAP group membership to calculate group permissions.
    - **Type:** `boolean`
    - **Default:** `false`

- **`AUTH_LDAP_CACHE_GROUPS`**:
    - **Description:** If we should cache groups to minimize LDAP traffic.
    - **Type:** `boolean`
    - **Default:** `false`

- **`AUTH_LDAP_GROUP_CACHE_TIMEOUT`**:
    - **Description:** How long we should cache LDAP groups for (in seconds). Only applies if
    `AUTH_LDAP_CACHE_GROUPS` is true.
    - **Type:** `integer`
    - **Default:** `3600`

- **`AUTH_LDAP_START_TLS`**:
    - **Description:** Determines if we update to a secure LDAP connection using StartTLS after connecting.
    - **Type:** `boolean`
    - **Default:** `true`

- **`AUTH_LDAP_PROTOCOL_VERSION`**:
    - **Description:** If set, forces LDAP protocol version 3.
    - **Type:** `integer`
    - **Default:** `''`

- **`AUTH_LDAP_TLS_CACERTFILE`**:
    - **Description:** Path to a custom LDAP certificate authority file.
    - **Type:** `string`
    - **Default:** `''`

- **`AUTH_LDAP_TLS_CERTFILE`**:
    - **Description:** Path to a custom LDAP certificate file.
    - **Type:** `string`
    - **Default:** `''`

- **`AUTH_LDAP_TLS_KEYFILE`**:
    - **Description:** Path to a custom LDAP key file (matching the cert given in `AUTH_LDAP_TLS_CERTFILE`).
    - **Type:** `string`
    - **Default:** `''`

- **`AUTH_LDAP_TLS_REQUIRE_CERT`**:
    - **Description:** How strict to be regarding TLS cerfiticate verification. Allowed values are "never",
    "allow", "try", "demand", or "hard". Corresponds to the TLSVerifyClient OpenLDAP setting.
    - **Type:** `string`
    - **Default:** `''`

### CAS-specific environment variables

These variables specify the behaviour of CAS authentication. If `SS_CAS_AUTHENTICATION` is false, none of the other ones are used.

- **`AUTH_CAS_SERVER_URL`**:
    - **Description:** Address of the CAS server to authenticate against. Defaults to CAS demo server.
    - **Type:** `string`
    - **Default:** `https://django-cas-ng-demo-server.herokuapp.com/cas/`

- **`AUTH_CAS_PROTOCOL_VERSION`**:
    - **Description:** Version of CAS protocol to use. Allowed values are "1", "2", "3", or "CAS_2_SAML_1_0".
    - **Type:** `string`
    - **Default:** `3`

- **`AUTH_CAS_CHECK_ADMIN_ATTRIBUTES`**:
    - **Description:** Determines if we check user attributes returned by CAS server to determine if user is an administrator.
    - **Type:** `boolean`
    - **Default:** `false`

- **`AUTH_CAS_ADMIN_ATTRIBUTE`**:
    - **Description:** Name of attribute to check for administrator status, if `CAS_CHECK_ADMIN_ATTRIBUTES` is True.
    - **Type:** `string`
    - **Default:** `None`

- **`AUTH_CAS_ADMIN_ATTRIBUTE_VALUE`**:
    - **Description:** Value in `CAS_ADMIN_ATTRIBUTE` that indicates user is an administrator, if `CAS_CHECK_ADMIN_ATTRIBUTES` is True.
    - **Type:** `string`
    - **Default:** `None`

- **`AUTH_CAS_AUTOCONFIGURE_EMAIL`**:
    - **Description:** Determines if we auto-configure an email address for new users by following the rule username@domain.
    - **Type:** `boolean`
    - **Default:** `false`

- **`AUTH_CAS_EMAIL_DOMAIN`**:
    - **Description:** Domain to use for auto-configured email addresses, if `AUTH_CAS_AUTOCONFIGURE_EMAIL` is True.
    - **Type:** `string`
    - **Default:** `None`

### OIDC-specific environment variables

**OIDC support is experimental, please share your feedback!**

These variables specify the behaviour of OpenID Connect (OIDC) authentication. If `SS_OIDC_AUTHENTICATION` is false, none of the other ones are used.

- **`SS_OIDC_AUTHENTICATION`**:
    - **Description:** Enables user authentication via OIDC.
    - **Type:** `boolean`
    - **Default:** `false`

- **`OIDC_RP_CLIENT_ID`**:
    - **Description:** OIDC client ID
    - **Type:** `string`
    - **Default:** `''`

- **`OIDC_RP_CLIENT_SECRET`**:
    - **Description:** OIDC client secret
    - **Type:** `string`
    - **Default:** `''`

- **`AZURE_TENANT_ID`**:
    - **Description:** Azure Active Directory Tenant ID - if this is provided, the endpoint URLs will be automatically generated from this.
    - **Type:** `string`
    - **Default:** `''`

- **`OIDC_OP_AUTHORIZATION_ENDPOINT`**:
    - **Description:** URL of OIDC provider authorization endpoint
    - **Type:** `string`
    - **Default:** `''`

- **`OIDC_OP_TOKEN_ENDPOINT`**:
    - **Description:** URL of OIDC provider token endpoint
    - **Type:** `string`
    - **Default:** `''`

- **`OIDC_OP_USER_ENDPOINT`**:
    - **Description:** URL of OIDC provider userinfo endpoint
    - **Type:** `string`
    - **Default:** `''`

- **`OIDC_OP_JWKS_ENDPOINT`**:
    - **Description:** URL of OIDC provider JWKS endpoint
    - **Type:** `string`
    - **Default:** `''`

- **`OIDC_RP_SIGN_ALGO`**:
    - **Description:** Algorithm used by the ID provider to sign ID tokens
    - **Type:** `string`
    - **Default:** `HS256`

### AWS-specific environment variables

These variables can be set to allow AWS authentication for S3 storage spaces as an alternative to providing these details via the user interface. See [AWS CLI Environment Variables](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-envvars.html) for details.

- **`AWS_ACCESS_KEY_ID`**:
    - **Description:** Access key for AWS authentication
    - **Type:** `string`
    - **Default:** `''`

- **`AWS_SECRET_ACCESS_KEY`**:
    - **Description:** Secret key associated with the access key
    - **Type:** `string`
    - **Default:** `''`

## Logging configuration

Logging configuration defaults for all logs to using `stdout` and `stderr`
unless they are configured to do otherwise. If there are no changes to the
default configuration they will be handled by whichever process is managing
Archivematica's services. For example, on Ubuntu 16.04, Ubuntu 18.04 or
CentOS 7, Archivematica's processes are managed by `systemd`. Logs for the
Storage Service can be accessed using `sudo journalctl -u archivematica-storage
-service`.

When running Archivematica using docker, `docker-compose logs` commands can be
used to access the logs from different containers, e.g. `docker-compose logs
-f archivematica-storage-service`.

### Overriding the logging configuration

Via the Django configuration settings, i.e. [base.py][django-config], the
storage service will look for a file in `/etc/archivematica/` called
`storageService.logging.json`. If this file is found it can be used to override
the default logging behavior.

The [`storageService.logging.json`](./storageService.logging.json) file found
in this installation directory provides an example that is configured to output
to a logs directory: `/var/log/archivematica/storage-service`, i.e.
`/var/log/archivematica/storage-service/storage_service.log`.

### Increase or decrease the logging output

Archivematica uses Python's standard approach to logging. There is a hierarchy
of logging levels, at each level, more or less output can be configured. The
values run from DEBUG (verbose) to CRITICAL (less verbose) as follows:

* DEBUG.
* INFO.
* WARNING.
* ERROR.
* CRITICAL.

The [Python documentation][python-docs] provides greater explanation.

Though best efforts are taken to include the most useful information for
debugging as possible your mileage may vary in debugging Archivematica or the
Storage Service depending on the way the developer has written any particular
module.

This is largely the same with external libraries, however, increasing their
logging level can make available more information that isn't output by choice
in the storage service's modules. Take for example the S3 Boto3 adapter.
Logging can be changed from INFO to DEBUG to reveal more detailed information
about a file transfer:

```js
    "boto3": {"level": "INFO"}, // becomes "boto3.*": {"level": "DEBUG"},
    "botocore": {"level": "INFO"} // becomes "botocore.*": {"level": "DEBUG"}
```

Debug logging should never be used on a production server without the full
implications being understood. The Boto3 developers, for example, ask users
to [heed their warning][boto3]:

> Warning: Be aware that when logging anything from 'botocore' the full wire
trace will appear in your logs. If your payloads contain sensitive data this
should not be used in production.

More information can be configured in Archivematica's Storage Service logging
for additional Django web-framework components, SWORD2, and Boto3 which is used
to manage data transfer and communication between the Storage Service and S3.

New [issues][gh-issues] or pull-requests can be submitted in support of
additional logging wherever it is needed by maintainers of Archivematica's
services.

[python-docs]: https://docs.python.org/3/howto/logging.html#when-to-use-logging
[boto3]: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/core/boto3.html#boto3.set_stream
[django-config]: https://github.com/artefactual/archivematica-storage-service/blob/1adaea28b8853308b8220c493d836eb9d50eb975/storage_service/storage_service/settings/base.py
[gh-issues]: https://github.com/archivematica/issues
