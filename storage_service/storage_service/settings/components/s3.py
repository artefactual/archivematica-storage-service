"""Configure S3

From here we can configure aspects of S3 in the Storage Service.
"""
from os import environ

from django.core.exceptions import ImproperlyConfigured

# Read and connect timeouts for S3. Ideally these will match the
# defaults recommended by your S3 implementation.
S3_TIMEOUTS = 900
try:
    S3_TIMEOUTS = int(environ.get("SS_S3_TIMEOUTS", S3_TIMEOUTS))
except ValueError:
    err_msg = "S3 timeout value configured incorrectly in the environment - please check the 'S3_TIMEOUTS' variable"
    raise ImproperlyConfigured(err_msg)
