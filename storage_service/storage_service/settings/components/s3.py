"""Configure S3

From here we can configure aspects of S3 in the Storage Service.

With specific reference to debug, we use an S3 library called boto3. If
the service does need to be investigated then it should be done so on
strictly non-production/non-sensitive data. And then the debug setting
reverted once investigation is complete.

From the docs at time of writing: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/core/boto3.html#boto3.set_stream_logger

    Warning: Be aware that when logging anything from 'botocore' the
    full wire trace will appear in your logs. If your payloads contain
    sensitive data this should not be used in production.

"""
from os import environ

from storage_service.settings.helpers import is_true

# Turn on all debug messages from boto3 including the full wire-trace.
# There isn't greater granularity because the amount of information
S3_DEBUG = False
if is_true(environ.get("SS_S3_DEBUG", "false")):
    S3_DEBUG = True

# Read and connect timeouts for S3. Ideally these will match the
# defaults recommended by your S3 implementation
S3_TIMEOUTS = 900
try:
    S3_TIMEOUTS = int(environ.get("SS_S3_TIMEOUTS", S3_TIMEOUTS))
except ValueError:
    pass
