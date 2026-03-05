"""Configure S3

From here we can configure aspects of S3 in the Storage Service.
"""

from os import environ

from django.core.exceptions import ImproperlyConfigured

from archivematica.storage_service.common.helpers import is_true

# Read and connect timeouts for S3. Ideally these will match the
# defaults recommended by your S3 implementation.
S3_TIMEOUTS = 900
try:
    S3_TIMEOUTS = int(environ.get("SS_S3_TIMEOUTS", S3_TIMEOUTS))
except ValueError:
    err_msg = "S3 timeout value configured incorrectly in the environment - please check the 'S3_TIMEOUTS' variable"
    raise ImproperlyConfigured(err_msg)

# Enable/disable managed transfer threading for boto3 S3 transfers.
# SS_S3_USE_THREADS is kept as a shared fallback for backward compatibility.
S3_USE_THREADS = is_true(environ.get("SS_S3_USE_THREADS", "true"))
S3_UPLOAD_USE_THREADS = is_true(
    environ.get("SS_S3_UPLOAD_USE_THREADS", str(S3_USE_THREADS).lower())
)
S3_DOWNLOAD_USE_THREADS = is_true(
    environ.get("SS_S3_DOWNLOAD_USE_THREADS", str(S3_USE_THREADS).lower())
)
