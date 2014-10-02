# stdlib, alphabetical
import logging
import os

# Core Django, alphabetical
from django.db import models

# Third party dependencies, alphabetical
from django_extensions.db.fields import UUIDField

# This project, alphabetical

# This module, alphabetical
from managers import Enabled

__all__ = ('Location', 'LocationPipeline')

LOGGER = logging.getLogger(__name__)


class Location(models.Model):
    """ Stores information about a location. """

    uuid = UUIDField(editable=False, unique=True, version=4,
        help_text="Unique identifier")
    space = models.ForeignKey('Space', to_field='uuid')

    # Sorted by display name
    AIP_STORAGE = 'AS'
    CURRENTLY_PROCESSING = 'CP'
    DIP_STORAGE = 'DS'
    SWORD_DEPOSIT = 'SD'
    # QUARANTINE = 'QU'
    STORAGE_SERVICE_INTERNAL = 'SS'
    BACKLOG = 'BL'
    TRANSFER_SOURCE = 'TS'

    PURPOSE_CHOICES = (
        (AIP_STORAGE, 'AIP Storage'),
        (CURRENTLY_PROCESSING, 'Currently Processing'),
        (DIP_STORAGE, 'DIP Storage'),
        (SWORD_DEPOSIT, 'FEDORA Deposits'),
        # (QUARANTINE, 'Quarantine'),
        (STORAGE_SERVICE_INTERNAL, 'Storage Service Internal Processing'),
        (BACKLOG, 'Transfer Backlog'),
        (TRANSFER_SOURCE, 'Transfer Source'),
    )
    purpose = models.CharField(max_length=2,
        choices=PURPOSE_CHOICES,
        help_text="Purpose of the space.  Eg. AIP storage, Transfer source")
    pipeline = models.ManyToManyField('Pipeline', through='LocationPipeline',
        null=True, blank=True,
        help_text="UUID of the Archivematica instance using this location.")

    relative_path = models.TextField(help_text="Path to location, relative to the storage space's path.")
    description = models.CharField(max_length=256, default=None,
        null=True, blank=True, help_text="Human-readable description.")
    quota = models.BigIntegerField(default=None, null=True, blank=True,
        help_text="Size, in bytes (optional)")
    used = models.BigIntegerField(default=0,
        help_text="Amount used, in bytes.")
    enabled = models.BooleanField(default=True,
        help_text="True if space can be accessed.")

    class Meta:
        verbose_name = "Location"
        app_label = 'locations'

    objects = models.Manager()
    active = Enabled()

    def __unicode__(self):
        return u"{uuid}: {path} ({purpose})".format(
            uuid=self.uuid,
            purpose=self.get_purpose_display(),
            path=self.full_path,
        )

    # Attributes
    @property
    def full_path(self):
        """ Returns full path of location: space + location paths. """
        return os.path.normpath(
            os.path.join(self.space.path, self.relative_path))

    def get_description(self):
        """ Returns a user-friendly description (or the path). """
        return self.description or self.full_path


class LocationPipeline(models.Model):
    location = models.ForeignKey('Location', to_field='uuid')
    pipeline = models.ForeignKey('Pipeline', to_field='uuid')

    class Meta:
        verbose_name = "Location associated with a Pipeline"
        app_label = 'locations'

    def __unicode__(self):
        return u'{} is associated with {}'.format(self.location, self.pipeline)
