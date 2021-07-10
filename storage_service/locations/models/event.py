# stdlib, alphabetical
from collections import OrderedDict
import json

# Core Django, alphabetical
from django.conf import settings
from django.db import models
from django.utils.translation import ugettext_lazy as _

# Third party dependencies, alphabetical
from django_extensions.db.fields import UUIDField
import requests

# This project, alphabetical

# This module, alphabetical
from . import StorageException

__all__ = ("Event", "Callback", "File", "CallbackError")


class CallbackError(StorageException):
    pass


class Event(models.Model):
    """Stores requests to modify packages that need admin approval.

    Eg. delete AIP can be requested by a pipeline, but needs storage
    administrator approval.  Who made the request and why is also stored."""

    package = models.ForeignKey("Package", to_field="uuid", on_delete=models.CASCADE)
    DELETE = "DELETE"
    RECOVER = "RECOVER"
    EVENT_TYPE_CHOICES = ((DELETE, _("delete")), (RECOVER, _("recover")))
    event_type = models.CharField(max_length=8, choices=EVENT_TYPE_CHOICES)
    event_reason = models.TextField()
    pipeline = models.ForeignKey("Pipeline", to_field="uuid", on_delete=models.CASCADE)
    user_id = models.PositiveIntegerField()
    user_email = models.EmailField(max_length=254)
    SUBMITTED = "SUBMIT"
    APPROVED = "APPROVE"
    REJECTED = "REJECT"
    EVENT_STATUS_CHOICES = (
        (SUBMITTED, _("Submitted")),
        (APPROVED, _("Approved")),
        (REJECTED, _("Rejected")),
    )
    status = models.CharField(max_length=8, choices=EVENT_STATUS_CHOICES)
    status_reason = models.TextField(null=True, blank=True)
    admin_id = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE
    )
    status_time = models.DateTimeField(auto_now=True)
    store_data = models.TextField(null=True, blank=True, editable=False)

    class Meta:
        verbose_name = _("Event")
        app_label = "locations"

    def __str__(self):
        return _("%(event_status)s request to %(event_type)s %(package)s") % {
            "event_status": self.get_status_display(),
            "event_type": self.get_event_type_display(),
            "package": self.package,
        }


class Callback(models.Model):
    """
    Allows REST callbacks to be associated with specific Storage Service events.

    A callback is a call to a given URL (usually a REST API) using a
    particular HTTP method.
    """

    EVENTS = (
        ("post_store", _("Post-store AIP (source files)")),
        ("post_store_aip", _("Post-store AIP")),
        ("post_store_aic", _("Post-store AIC")),
        ("post_store_dip", _("Post-store DIP")),
    )

    HTTP_METHODS = (
        ("delete", "DELETE"),
        ("get", "GET"),
        ("head", "HEAD"),
        ("options", "OPTIONS"),
        ("patch", "PATCH"),
        ("post", "POST"),
        ("put", "PUT"),
    )

    uuid = UUIDField()
    uri = models.CharField(
        max_length=1024,
        verbose_name=_("URI"),
        help_text=_("URL to contact upon callback execution."),
    )
    event = models.CharField(
        max_length=15,
        choices=EVENTS,
        verbose_name=_("Event"),
        help_text=_("Type of event when this callback should be executed."),
    )
    method = models.CharField(
        max_length=10,
        choices=HTTP_METHODS,
        verbose_name=_("Method"),
        help_text=_("HTTP request method to use in connecting to the URL."),
    )
    body = models.TextField(
        null=True,
        blank=True,
        verbose_name=_("Body"),
        help_text=_(
            "Body content for each request. Set the 'Content-type' header accordingly."
        ),
    )
    headers = models.TextField(
        null=True,
        blank=True,
        verbose_name=_("Headers"),
        help_text=_("Headers for each request."),
    )
    expected_status = models.IntegerField(
        default=200,
        verbose_name=_("Expected Status"),
        help_text=_(
            "Expected HTTP response from the server, used to validate the callback response."
        ),
    )
    enabled = models.BooleanField(
        default=True,
        verbose_name=_("Enabled"),
        help_text=_("Enabled if this callback should be executed."),
    )

    class Meta:
        verbose_name = _("Callback")
        app_label = "locations"

    def get_headers(self):
        """Loads the headers string into a key/value OrderedDict."""
        return (
            json.loads(self.headers, object_pairs_hook=OrderedDict)
            if self.headers
            else {}
        )

    def execute(self, url=None, body=None):
        """
        Execute the callback by contacting the external service.

        The url and body parameters can be provided in case they need to
        be altered. For instance, they might contain a placeholder such
        as <file_uuid>, which will be replaced with the real file UUID
        before executing.

        If the connection does not succeed, returns a CallbackError
        with explanatory text.

        If the response from the server did not match the expected
        status code, raises a a CallbackError with the body of the
        response; otherwise, returns None.
        """
        if not url:
            url = self.uri
        if not body:
            body = self.body

        try:
            response = getattr(requests, self.method)(
                url, data=body or "", headers=self.get_headers()
            )
        except requests.exceptions.ConnectionError as e:
            raise CallbackError(str(e))

        if not response.status_code == self.expected_status:
            raise CallbackError(response.text)


class File(models.Model):
    uuid = UUIDField(
        editable=False, unique=True, version=4, help_text=_("Unique identifier")
    )
    package = models.ForeignKey("Package", null=True, on_delete=models.CASCADE)
    name = models.TextField(max_length=1000)
    source_id = models.TextField(max_length=128)
    source_package = models.TextField(
        blank=True, help_text=_("Unique identifier of originating unit")
    )
    # Sized to fit sha512
    checksum = models.TextField(max_length=128)
    stored = models.BooleanField(default=False)
    accessionid = models.TextField(
        blank=True, help_text=_("Accession ID of originating transfer")
    )
    origin = UUIDField(
        editable=False,
        unique=False,
        version=4,
        blank=True,
        help_text=_("Unique identifier of originating Archivematica dashboard"),
    )

    class Meta:
        verbose_name = _("File")
        app_label = "locations"
