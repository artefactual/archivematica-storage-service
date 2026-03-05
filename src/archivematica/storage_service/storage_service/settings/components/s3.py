"""Configure S3

From here we can configure aspects of S3 in the Storage Service.
"""

from os import environ

from django.core.exceptions import ImproperlyConfigured

from archivematica.storage_service.common.helpers import is_true


def _get_int_env(name, default):
    try:
        return int(environ.get(name, default))
    except ValueError:
        err_msg = f"{name} configured incorrectly in the environment"
        raise ImproperlyConfigured(err_msg)


# Read and connect timeouts for S3. Ideally these will match the
# defaults recommended by your S3 implementation.
S3_TIMEOUTS = 900
S3_TIMEOUTS = _get_int_env("SS_S3_TIMEOUTS", S3_TIMEOUTS)
S3_CONNECT_TIMEOUTS = _get_int_env("SS_S3_CONNECT_TIMEOUTS", S3_TIMEOUTS)
S3_READ_TIMEOUTS = _get_int_env("SS_S3_READ_TIMEOUTS", S3_TIMEOUTS)

# Retry settings for botocore and managed S3 transfers.
S3_RETRY_MODE = environ.get("SS_S3_RETRY_MODE", "standard")
S3_MAX_ATTEMPTS = _get_int_env("SS_S3_MAX_ATTEMPTS", 10)
S3_TRANSFER_MAX_RETRIES = _get_int_env("SS_S3_TRANSFER_MAX_RETRIES", 3)
S3_TRANSFER_RETRY_BACKOFF = _get_int_env("SS_S3_TRANSFER_RETRY_BACKOFF", 2)
S3_DOWNLOAD_ATTEMPTS = _get_int_env("SS_S3_DOWNLOAD_ATTEMPTS", 5)

# Enable/disable managed transfer threading for boto3 S3 transfers.
# SS_S3_USE_THREADS is kept as a shared fallback for backward compatibility.
S3_USE_THREADS = is_true(environ.get("SS_S3_USE_THREADS", "true"))
S3_UPLOAD_USE_THREADS = is_true(
    environ.get("SS_S3_UPLOAD_USE_THREADS", str(S3_USE_THREADS).lower())
)
S3_DOWNLOAD_USE_THREADS = is_true(
    environ.get("SS_S3_DOWNLOAD_USE_THREADS", str(S3_USE_THREADS).lower())
)
