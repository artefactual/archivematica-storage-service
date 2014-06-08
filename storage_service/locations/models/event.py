# stdlib, alphabetical

# Core Django, alphabetical
from django.conf import settings
from django.db import models

# Third party dependencies, alphabetical
from django_extensions.db.fields import UUIDField
import requests

# This project, alphabetical

# This module, alphabetical
from . import StorageException

__all__ = ('Event', 'Callback', 'File', 'CallbackError')


class CallbackError(StorageException):
    pass


class Event(models.Model):
    """ Stores requests to modify packages that need admin approval.

    Eg. delete AIP can be requested by a pipeline, but needs storage
    administrator approval.  Who made the request and why is also stored. """
    package = models.ForeignKey('Package', to_field='uuid')
    DELETE = 'DELETE'
    RECOVER = 'RECOVER'
    EVENT_TYPE_CHOICES = (
        (DELETE, 'delete'),
        (RECOVER, 'recover'),
    )
    event_type = models.CharField(max_length=8, choices=EVENT_TYPE_CHOICES)
    event_reason = models.TextField()
    pipeline = models.ForeignKey('Pipeline', to_field='uuid')
    user_id = models.PositiveIntegerField()
    user_email = models.EmailField(max_length=254)
    SUBMITTED = 'SUBMIT'
    APPROVED = 'APPROVE'
    REJECTED = 'REJECT'
    EVENT_STATUS_CHOICES = (
        (SUBMITTED, 'Submitted'),
        (APPROVED, 'Approved'),
        (REJECTED, 'Rejected'),
    )
    status = models.CharField(max_length=8, choices=EVENT_STATUS_CHOICES)
    status_reason = models.TextField(null=True, blank=True)
    admin_id = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True)
    status_time = models.DateTimeField(auto_now=True)
    store_data = models.TextField(null=True, blank=True, editable=False)

    class Meta:
        verbose_name = "Event"
        app_label = 'locations'

    def __unicode__(self):
        return u"{event_status} request to {event_type} {package}".format(
            event_status=self.get_status_display(),
            event_type=self.get_event_type_display(),
            package=self.package)


class Callback(models.Model):
    """
    Allows REST callbacks to be associated with specific Storage Service events.

    A callback is a call to a given URL (usually a REST API) using a
    particular HTTP method.
    """
    EVENTS = (
        ('post_store', 'Post-store'),
    )

    HTTP_METHODS = (
        ('delete', 'DELETE'),
        ('get', 'GET'),
        ('head', 'HEAD'),
        ('options', 'OPTIONS'),
        ('patch', 'PATCH'),
        ('post', 'POST'),
        ('put', 'PUT'),
    )

    uuid = UUIDField()
    uri = models.CharField(max_length=1024,
        help_text="URL to contact upon callback execution.")
    event = models.CharField(max_length=15, choices=EVENTS,
        help_text="Type of event when this callback should be executed.")
    method = models.CharField(max_length=10, choices=HTTP_METHODS,
        help_text="HTTP request method to use in connecting to the URL.")
    expected_status = models.IntegerField(default=200,
        help_text="Expected HTTP response from the server, used to validate the callback response.")
    enabled = models.BooleanField(default=True,
        help_text="Enabled if this callback should be executed.")

    class Meta:
        verbose_name = "Callback"
        app_label = 'locations'

    def execute(self, url=None):
        """
        Execute the callback by contacting the external service.

        The url parameter can be provided in case the URL needs to be
        altered. For instance, the URL might contain a placeholder such
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

        try:
            response = getattr(requests, self.method)(url)
        except requests.exceptions.ConnectionError as e:
            raise CallbackError(str(e))

        if not response.status_code == self.expected_status:
            raise CallbackError(response.body)


class File(models.Model):
    uuid = UUIDField(editable=False, unique=True, version=4,
        help_text="Unique identifier")
    name = models.TextField(max_length=1000)
    source_id = models.TextField(max_length=128)
    # Sized to fit sha512
    checksum = models.TextField(max_length=128)
    stored = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Callback File"
        app_label = 'locations'
