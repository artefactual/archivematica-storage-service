from __future__ import absolute_import

import json
import logging

from django.dispatch import receiver, Signal
from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.db.models import signals
from django.utils.translation import ugettext as _
from tastypie.models import create_api_key

LOGGER = logging.getLogger(__name__)

deletion_request = Signal(providing_args=["uuid", "location", "url"])
failed_fixity_check = Signal(providing_args=["uuid", "location", "report"])
successful_fixity_check = Signal(providing_args=["uuid", "location", "report"])
fixity_check_not_run = Signal(providing_args=["uuid", "location", "report"])


def _notify_administrators(subject, message):
    admin_users = User.objects.filter(is_superuser=True)
    for user in admin_users:
        try:
            user.email_user(subject, message)
        except Exception:
            LOGGER.exception("Unable to send email to %s", user.email)


@receiver(deletion_request, dispatch_uid="deletion_request")
def report_deletion_request(sender, **kwargs):
    subject = _('Deletion request for package %(uuid)s') % {'uuid': kwargs['uuid']}
    message = _('A package deletion request was received for the package with UUID %(uuid)s. This package is currently stored at: %(location)s.') % {'uuid': kwargs['uuid'], 'location': kwargs['location']}

    # The URL may not be configured in the site; if it isn't,
    # don't try to tell the user the URL to approve/deny the request.
    if kwargs["url"]:
        message = message + _('To approve this deletion request, visit: %(url)s') % {'url': kwargs['url'] + reverse('package_delete_request')}

    _notify_administrators(subject, message)


def _log_report(uuid, success, message=None):
    # NOTE Importing this at the top of the module fails because this file is
    # imported in models.__init__.py and seems to cause a circular import error
    from . import models
    package = models.Package.objects.get(uuid=uuid)
    models.FixityLog.objects.create(package=package, success=success, error_details=message)


@receiver(failed_fixity_check, dispatch_uid="fixity_check")
def report_failed_fixity_check(sender, **kwargs):
    report_data = json.loads(kwargs['report'])
    _log_report(kwargs['uuid'], False, report_data['message'])

    subject = _('Fixity check failed for package %(uuid)s') % {'uuid': kwargs['uuid']}
    message = _("""
A fixity check failed for the package with UUID %(uuid)s. This package is currently stored at: %(location)s

Full failure report (in JSON format):
%(report)s
""") % {'uuid': kwargs['uuid'], 'location': kwargs['location'], 'report': kwargs['report']}

    _notify_administrators(subject, message)


@receiver(successful_fixity_check, dispatch_uid="fixity_check")
def report_successful_fixity_check(sender, **kwargs):
    _log_report(kwargs['uuid'], True)


@receiver(fixity_check_not_run, dispatch_uid="fixity_check")
def report_not_run_fixity_check(sender, **kwargs):
    """Handle a fixity not run signal."""
    report_data = json.loads(kwargs['report'])
    _log_report(uuid=kwargs['uuid'], success=None, message=report_data['message'])


# Create an API key for every user, for TastyPie
signals.post_save.connect(create_api_key, sender=User)
