# stdlib, alphabetical

import logging
import os

# Core Django, alphabetical
from django.dispatch import receiver
from django.db import models
from django.utils.translation import ugettext_lazy as _

# Third party dependencies, alphabetical
from django_extensions.db.fields import UUIDField

# This project, alphabetical
from administration.models import Settings

# This module, alphabetical
from .managers import Enabled

__all__ = ("Location", "LocationPipeline")

LOGGER = logging.getLogger(__name__)


class Location(models.Model):
    """ Stores information about a location. """

    uuid = UUIDField(
        editable=False, unique=True, version=4, help_text=_("Unique identifier")
    )
    space = models.ForeignKey("Space", to_field="uuid", on_delete=models.CASCADE)

    # Sorted by display name
    AIP_RECOVERY = "AR"
    AIP_STORAGE = "AS"
    CURRENTLY_PROCESSING = "CP"
    DIP_STORAGE = "DS"
    SWORD_DEPOSIT = "SD"
    # QUARANTINE = 'QU'
    STORAGE_SERVICE_INTERNAL = "SS"
    BACKLOG = "BL"
    TRANSFER_SOURCE = "TS"
    REPLICATOR = "RP"

    # List of purposes where moving is not allowed.
    PURPOSES_DISALLOWED_MOVE = (BACKLOG, AIP_STORAGE, TRANSFER_SOURCE)

    PURPOSE_CHOICES = (
        (AIP_RECOVERY, _("AIP Recovery")),
        (AIP_STORAGE, _("AIP Storage")),
        (CURRENTLY_PROCESSING, _("Currently Processing")),
        (DIP_STORAGE, _("DIP Storage")),
        (SWORD_DEPOSIT, _("FEDORA Deposits")),
        # (QUARANTINE, 'Quarantine'),
        (STORAGE_SERVICE_INTERNAL, _("Storage Service Internal Processing")),
        (BACKLOG, _("Transfer Backlog")),
        (TRANSFER_SOURCE, _("Transfer Source")),
        (REPLICATOR, _("Replicator")),
    )
    purpose = models.CharField(
        max_length=2,
        choices=PURPOSE_CHOICES,
        verbose_name=_("Purpose"),
        help_text=_("Purpose of the space.  Eg. AIP storage, Transfer source"),
    )
    pipeline = models.ManyToManyField(
        "Pipeline",
        through="LocationPipeline",
        blank=True,
        verbose_name=_("Pipeline"),
        help_text=_("UUID of the Archivematica instance using this location."),
    )
    relative_path = models.TextField(
        verbose_name=_("Relative Path"),
        help_text=_("Path to location, relative to the storage space's path."),
    )
    description = models.CharField(
        max_length=256,
        default=None,
        verbose_name=_("Description"),
        null=True,
        blank=True,
        help_text=_("Human-readable description."),
    )
    quota = models.BigIntegerField(
        default=None,
        null=True,
        blank=True,
        verbose_name=_("Quota"),
        help_text=_("Size, in bytes (optional)"),
    )
    used = models.BigIntegerField(
        default=0, verbose_name=_("Used"), help_text=_("Amount used, in bytes.")
    )
    enabled = models.BooleanField(
        default=True,
        verbose_name=_("Enabled"),
        help_text=_("True if space can be accessed."),
    )
    replicators = models.ManyToManyField(
        "Location",
        blank=True,
        related_name="masters",
        verbose_name=_("Replicators"),
        help_text=_(
            "Other locations that will be used to create replicas of"
            " the packages stored in this location"
        ),
    )

    class Meta:
        verbose_name = _("Location")
        app_label = "locations"

    objects = models.Manager()
    active = Enabled()

    # Whether this location is the default location which is a global
    # application setting stored in administration.models.Settings. See
    # signal receivers unset_default_location and set_default_location for
    # more details.
    _default = None

    def __str__(self):
        return _("%(uuid)s: %(path)s (%(purpose)s)") % {
            "uuid": self.uuid,
            "purpose": self.get_purpose_display(),
            "path": self.relative_path,
        }

    # Attributes
    @property
    def full_path(self):
        """ Returns full path of location: space + location paths. """

        # Dataverses are browsed using the relative path. We only want to
        # return that to display to the user here.
        if self.space.access_protocol == self.space.DATAVERSE:
            return self.relative_path
        # Else act as normal.
        return os.path.normpath(os.path.join(self.space.path, self.relative_path))

    @property
    def default(self):
        """ Looks up whether this location is the default one application-wise. """
        if self._default is None:
            try:
                name = f"default_{self.purpose}_location"
                Settings.objects.get(name=name, value=self.uuid)
                self._default = True
            except Settings.DoesNotExist:
                self._default = False
        return self._default

    @default.setter
    def default(self, value):
        self._default = value

    def get_description(self):
        """ Returns a user-friendly description (or the path). """
        return self.description or self.full_path

    def is_move_allowed(self):
        """Returns whether it's allowed to move contents from this location."""
        return self.purpose not in self.PURPOSES_DISALLOWED_MOVE


@receiver(models.signals.pre_delete, sender=Location)
def unset_default_location(sender, instance, using, **kwargs):
    name = f"default_{instance.purpose}_location"
    Settings.objects.filter(name=name, value=instance.uuid).delete()


@receiver(models.signals.pre_save, sender=Location)
def set_default_location_pre_save(
    sender, instance, raw, using, update_fields, **kwargs
):
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
            name=f"default_{old.purpose}_location", value=old.uuid
        ).delete()


@receiver(models.signals.post_save, sender=Location)
def set_default_location_post_save(
    sender, instance, created, raw, using, update_fields, **kwargs
):
    name = f"default_{instance.purpose}_location"
    if instance.default:
        Settings.objects.update_or_create(name=name, defaults={"value": instance.uuid})
    else:
        Settings.objects.filter(name=name, value=instance.uuid).delete()


class LocationPipeline(models.Model):
    location = models.ForeignKey("Location", to_field="uuid", on_delete=models.CASCADE)
    pipeline = models.ForeignKey("Pipeline", to_field="uuid", on_delete=models.CASCADE)

    class Meta:
        verbose_name = _("Location associated with a Pipeline")
        app_label = "locations"

    def __str__(self):
        return _("%(location)s is associated with %(pipeline)s") % {
            "location": self.location,
            "pipeline": self.pipeline,
        }
