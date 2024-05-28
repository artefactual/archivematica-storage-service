import json
import logging
import sys

from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import signals
from django.dispatch import Signal
from django.dispatch import receiver
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from prometheus_client import Counter
from tastypie.models import create_api_key

LOGGER = logging.getLogger(__name__)

deletion_request = Signal()
failed_fixity_check = Signal()
successful_fixity_check = Signal()
fixity_check_not_run = Signal()


def _notify_users(subject, message, users):
    for user in users:
        try:
            user.email_user(subject, message)
        except Exception:
            LOGGER.exception("Unable to send email to %s", user.email)


@receiver(deletion_request, dispatch_uid="deletion_request")
def report_deletion_request(sender, **kwargs):
    subject = _("Deletion request for package %(uuid)s") % {"uuid": kwargs["uuid"]}
    message = _(
        """A package deletion request was received:

Pipeline UUID: %(pipeline)s
Package UUID: %(uuid)s
Package location: %(location)s"""
    ) % {
        "pipeline": kwargs["pipeline"],
        "uuid": kwargs["uuid"],
        "location": kwargs["location"],
    }

    # The URL may not be configured in the site; if it isn't,
    # don't try to tell the user the URL to approve/deny the request.
    if kwargs["url"]:
        message = message + _("To approve this deletion request, visit: %(url)s") % {
            "url": kwargs["url"] + reverse("package_delete_request")
        }

    _notify_users(subject, message, User.objects.filter(is_superuser=True))


def _log_report(uuid, success, message=None):
    # NOTE Importing this at the top of the module fails because this file is
    # imported in models.__init__.py and seems to cause a circular import error
    from . import models

    package = models.Package.objects.get(uuid=uuid)
    return models.FixityLog.objects.create(
        package=package, success=success, error_details=message
    )


@receiver(failed_fixity_check, dispatch_uid="fixity_check")
def report_failed_fixity_check(sender, **kwargs):
    report_data = json.loads(kwargs["report"])
    fixity_log = _log_report(kwargs["uuid"], False, report_data["message"])
    timestamp = timezone.localtime(fixity_log.datetime_reported).strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    subject = _("Fixity check failed for package %(uuid)s") % {"uuid": kwargs["uuid"]}
    message = _(
        """
[%(timestamp)s] A fixity check failed for the package with UUID %(uuid)s.
"""
    ) % {
        "timestamp": timestamp,
        "uuid": kwargs["uuid"],
    }

    _notify_users(subject, message, User.objects.filter(is_active=True))


@receiver(successful_fixity_check, dispatch_uid="fixity_check")
def report_successful_fixity_check(sender, **kwargs):
    _log_report(kwargs["uuid"], True)


@receiver(fixity_check_not_run, dispatch_uid="fixity_check")
def report_not_run_fixity_check(sender, **kwargs):
    """Handle a fixity not run signal."""
    report_data = json.loads(kwargs["report"])
    _log_report(uuid=kwargs["uuid"], success=None, message=report_data["message"])


def _create_api_key(sender, *args, **kwargs):
    """Create API key for every user, for TastyPie.

    We don't want to run this in our tests because our fixtures provision a
    custom key. Tell me there is a better way to do this that does not require
    more scattering of signal business.
    """
    if "pytest" in sys.modules:
        return
    create_api_key(sender, **kwargs)


signals.post_save.connect(_create_api_key, sender=User)


if settings.PROMETHEUS_ENABLED:
    # Count saves and deletes via Prometheus.
    # This is a bit of a flawed way to do it (it doesn't include bulk create,
    # update, etc), but is a good starting point.
    # django-prometheus provides these counters via a model mixin, but signals
    # are less invasive.

    model_save_count = Counter(
        "django_model_save_total", "Total model save calls", ["model"]
    )
    model_delete_count = Counter(
        "django_model_delete_total", "Total model delete calls", ["model"]
    )

    @receiver(signals.post_save)
    def increment_model_save_count(sender, **kwargs):
        model_save_count.labels(model=sender.__name__).inc()

    @receiver(signals.post_delete)
    def increment_model_delete_count(sender, **kwargs):
        model_delete_count.labels(model=sender.__name__).inc()
