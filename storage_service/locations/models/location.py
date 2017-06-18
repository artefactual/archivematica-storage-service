from __future__ import absolute_import
# stdlib, alphabetical
import logging
import os

# Core Django, alphabetical
from django.dispatch import receiver
from django.db import models
from django.utils.translation import ugettext as _, ugettext_lazy as _l

# Third party dependencies, alphabetical
from django_extensions.db.fields import UUIDField

# This project, alphabetical
from administration.models import Settings

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

    # Whether this location is the default location which is a global
    # application setting stored in administration.models.Settings. See
    # signal receivers unset_default_locaiton and set_default_location for
    # more details.
    _default = False

    def __unicode__(self):
        return _('%(uuid)s: %(path)s (%(purpose)s)') % {'uuid': self.uuid, 'purpose': self.get_purpose_display(), 'path': self.relative_path}

    # Attributes
    @property
    def full_path(self):
        """ Returns full path of location: space + location paths. """
        return os.path.normpath(
            os.path.join(self.space.path, self.relative_path))

    @property
    def default(self):
        """ Looks up whether this location is the default one application-wise. """
        try:
            name = 'default_{}_location'.format(self.purpose)
            Settings.objects.get(name=name, value=self.uuid)
            return True
        except Settings.DoesNotExist:
            return False

    @default.setter
    def default(self, value):
        self._default = value

    def get_description(self):
        """ Returns a user-friendly description (or the path). """
        return self.description or self.full_path


@receiver(models.signals.pre_delete, sender=Location)
def unset_default_location(sender, instance, using, **kwargs):
    name = 'default_{}_location'.format(instance.purpose)
    Settings.objects.filter(name=name, value=instance.uuid).delete()


@receiver(models.signals.pre_save, sender=Location)
def set_default_location_pre_save(sender, instance, raw, using, update_fields, **kwargs):
    # Is this an edit? Has the purpose changed? If both are true, it's possible
    # that a default location setting with the previous purpose exists and it
    # needs to be deleted.
    if not instance.pk:
        return
    try:
        old = Location.objects.get(pk=instance.pk)
    except Location.DoesNotExist:
        return
    if old.purpose != instance.purpose:
        Settings.objects.filter(
            name='default_{}_location'.format(old.purpose),
            value=old.uuid).delete()


@receiver(models.signals.post_save, sender=Location)
def set_default_location_post_save(sender, instance, created, raw, using, update_fields, **kwargs):
    name = 'default_{}_location'.format(instance.purpose)
    if instance._default:
        Settings.objects.update_or_create(name=name, defaults={'value': instance.uuid})
    else:
        Settings.objects.filter(name=name, value=instance.uuid).delete()


class LocationPipeline(models.Model):
    location = models.ForeignKey('Location', to_field='uuid')
    pipeline = models.ForeignKey('Pipeline', to_field='uuid')

    class Meta:
        verbose_name = _l("Location associated with a Pipeline")
        app_label = 'locations'

    def __unicode__(self):
        return _('%(location)s is associated with %(pipeline)s') % {'location': self.location, 'pipeline': self.pipeline}
