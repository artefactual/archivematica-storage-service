from __future__ import absolute_import
# stdlib, alphabetical
import logging
import os

# Core Django, alphabetical
from django.db import models
from django.utils.translation import ugettext as _, ugettext_lazy as _l

# Third party dependencies, alphabetical
from django_extensions.db.fields import UUIDField

# This project, alphabetical

# This module, alphabetical
from .managers import Enabled

__all__ = ('Location', 'LocationPipeline')

LOGGER = logging.getLogger(__name__)


class Location(models.Model):
    """ Stores information about a location. """

    uuid = UUIDField(editable=False, unique=True, version=4,
        help_text=_l("Unique identifier"))
    space = models.ForeignKey('Space', to_field='uuid')

    # Sorted by display name
    AIP_RECOVERY = 'AR'
    AIP_STORAGE = 'AS'
    CURRENTLY_PROCESSING = 'CP'
    DIP_STORAGE = 'DS'
    SWORD_DEPOSIT = 'SD'
    # QUARANTINE = 'QU'
    STORAGE_SERVICE_INTERNAL = 'SS'
    BACKLOG = 'BL'
    TRANSFER_SOURCE = 'TS'

    PURPOSE_CHOICES = (
        (AIP_RECOVERY, _l('AIP Recovery')),
        (AIP_STORAGE, _l('AIP Storage')),
        (CURRENTLY_PROCESSING, _l('Currently Processing')),
        (DIP_STORAGE, _l('DIP Storage')),
        (SWORD_DEPOSIT, _l('FEDORA Deposits')),
        # (QUARANTINE, 'Quarantine'),
        (STORAGE_SERVICE_INTERNAL, _l('Storage Service Internal Processing')),
        (BACKLOG, _l('Transfer Backlog')),
        (TRANSFER_SOURCE, _l('Transfer Source')),
    )
    purpose = models.CharField(max_length=2,
        choices=PURPOSE_CHOICES,
        verbose_name=_l('Purpose'),
        help_text=_l("Purpose of the space.  Eg. AIP storage, Transfer source"))
    pipeline = models.ManyToManyField('Pipeline', through='LocationPipeline',
        blank=True,
        verbose_name=_l('Pipeline'),
        help_text=_l("UUID of the Archivematica instance using this location."))

    relative_path = models.TextField(
        verbose_name=_l('Relative Path'),
        help_text=_l("Path to location, relative to the storage space's path."))
    description = models.CharField(max_length=256, default=None,
        verbose_name=_l('Description'),
        null=True, blank=True, help_text=_l("Human-readable description."))
    quota = models.BigIntegerField(default=None, null=True, blank=True,
        verbose_name=_l('Quota'),
        help_text=_l("Size, in bytes (optional)"))
    used = models.BigIntegerField(default=0,
        verbose_name=_l('Used'),
        help_text=_l("Amount used, in bytes."))
    enabled = models.BooleanField(default=True,
        verbose_name=_l('Enabled'),
        help_text=_l("True if space can be accessed."))

    class Meta:
        verbose_name = _l("Location")
        app_label = 'locations'

    objects = models.Manager()
    active = Enabled()

    def __unicode__(self):
        return _('%(uuid)s: %(path)s (%(purpose)s)') % {'uuid': self.uuid, 'purpose': self.get_purpose_display(), 'path': self.relative_path}

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
        verbose_name = _l("Location associated with a Pipeline")
        app_label = 'locations'

    def __unicode__(self):
        return _('%(location)s is associated with %(pipeline)s') % {'location': self.location, 'pipeline': self.pipeline}
