import logging
from django.dispatch import receiver, Signal
from django.contrib.auth.models import User
from django.core.urlresolvers import reverse

LOGGER = logging.getLogger(__name__)

deletion_request = Signal(providing_args=["uuid", "location", "url"])
failed_fixity_check = Signal(providing_args=["uuid", "location", "report"])


def _notify_administrators(subject, message):
    admin_users = User.objects.filter(is_superuser=True)
    for user in admin_users:
        try:
            user.email_user(subject, message)
        except Exception:
            LOGGER.exception("Unable to send email to %s", user.email)


@receiver(deletion_request, dispatch_uid="deletion_request")
def report_deletion_request(sender, **kwargs):
    subject = "Deletion request for package {}".format(kwargs["uuid"])
    message = """
A package deletion request was received for the package with UUID {}. This package is currently stored at: {}.
""".format(kwargs["uuid"], kwargs["location"])

    # The URL may not be configured in the site; if it isn't,
    # don't try to tell the user the URL to approve/deny the request.
    if kwargs["url"]:
        message = message + """
To approve this deletion request, visit: {}{}
""".format(kwargs["url"], reverse('aip_delete_request'))

    _notify_administrators(subject, message)


@receiver(failed_fixity_check, dispatch_uid="fixity_check")
def report_failed_fixity_check(sender, **kwargs):
    subject = "Fixity check failed for package {}".format(kwargs["uuid"])
    message = """
A fixity check failed for the package with UUID {}. This package is currently stored at: {}

Full failure report (in JSON format):
{}
""".format(kwargs["uuid"], kwargs["location"], kwargs["report"])
    _notify_administrators(subject, message)
