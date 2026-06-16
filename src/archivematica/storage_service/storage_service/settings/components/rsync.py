"""Configure rsync subprocess boundaries."""

from os import environ

from django.core.exceptions import ImproperlyConfigured

# Fail rsync when it observes no I/O for this many seconds. This does not limit
# total transfer duration; large copies can run longer while making progress.
RSYNC_IO_TIMEOUT_SECONDS = 300
try:
    RSYNC_IO_TIMEOUT_SECONDS = int(
        environ.get("SS_RSYNC_IO_TIMEOUT_SECONDS", RSYNC_IO_TIMEOUT_SECONDS)
    )
except ValueError:
    raise ImproperlyConfigured(
        "Rsync I/O timeout configured incorrectly in the environment - "
        "please check the 'SS_RSYNC_IO_TIMEOUT_SECONDS' variable"
    )

# Safety net for rsync processes that keep doing some I/O but never finish.
RSYNC_PROCESS_TIMEOUT_SECONDS = 86400
try:
    RSYNC_PROCESS_TIMEOUT_SECONDS = int(
        environ.get("SS_RSYNC_PROCESS_TIMEOUT_SECONDS", RSYNC_PROCESS_TIMEOUT_SECONDS)
    )
except ValueError:
    raise ImproperlyConfigured(
        "Rsync process timeout configured incorrectly in the environment - "
        "please check the 'SS_RSYNC_PROCESS_TIMEOUT_SECONDS' variable"
    )
