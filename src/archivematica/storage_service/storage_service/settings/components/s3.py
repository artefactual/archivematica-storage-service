"""Configure S3

From here we can configure aspects of S3 in the Storage Service.
"""

from os import environ

from django.core.exceptions import ImproperlyConfigured

TRUE_VALUES = {"1", "true", "yes", "on"}


def _env_int(name, default):
    try:
        return int(environ.get(name, default))
    except ValueError as err:
        raise ImproperlyConfigured(
            f"{name} configured incorrectly in the environment"
        ) from err


def _env_float(name, default):
    try:
        return float(environ.get(name, default))
    except ValueError as err:
        raise ImproperlyConfigured(
            f"{name} configured incorrectly in the environment"
        ) from err


def _env_bool(name, default):
    raw = environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in TRUE_VALUES

# Read and connect timeouts for S3. Ideally these will match the
# defaults recommended by your S3 implementation.
S3_TIMEOUTS = _env_int("SS_S3_TIMEOUTS", 900)
S3_RETRY_MAX_ATTEMPTS = _env_int("SS_S3_RETRY_MAX_ATTEMPTS", 10)
S3_RETRY_MODE = environ.get("SS_S3_RETRY_MODE", "standard")

S3_TRANSFER_MAX_CONCURRENCY = _env_int("SS_S3_TRANSFER_MAX_CONCURRENCY", 10)
S3_TRANSFER_MULTIPART_THRESHOLD = _env_int(
    "SS_S3_TRANSFER_MULTIPART_THRESHOLD", 8 * 1024 * 1024
)
S3_TRANSFER_MULTIPART_CHUNKSIZE = _env_int(
    "SS_S3_TRANSFER_MULTIPART_CHUNKSIZE", 8 * 1024 * 1024
)

S3_UPLOAD_MAX_ATTEMPTS = _env_int("SS_S3_UPLOAD_MAX_ATTEMPTS", 3)
S3_UPLOAD_RETRY_DELAY = _env_float("SS_S3_UPLOAD_RETRY_DELAY", 2.0)
S3_UPLOAD_VERIFY = _env_bool("SS_S3_UPLOAD_VERIFY", True)
S3_UPLOAD_VERIFY_MAX_ATTEMPTS = _env_int("SS_S3_UPLOAD_VERIFY_MAX_ATTEMPTS", 6)
S3_UPLOAD_VERIFY_DELAY = _env_float("SS_S3_UPLOAD_VERIFY_DELAY", 2.0)
