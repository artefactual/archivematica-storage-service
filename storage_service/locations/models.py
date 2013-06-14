from django import forms
from django.db import models

from django_extensions.db.fields import UUIDField

########################## SPACES ##########################

class Space(models.Model):
    uuid = UUIDField(editable=False, unique=True, help_text="Unique identifier")

    LOCAL_FILESYSTEM = 'FS'
    # NFS = 'NFS'
    SAMBA = 'SAMBA'
    # LOCKSS = 'LOCKSS'
    # FEDORA = 'FEDORA'
    ACCESS_PROTOCOL_CHOICES = (
        (LOCAL_FILESYSTEM, "Local Filesystem"),
        (SAMBA, "SAMBA")
    )
    access_protocol = models.CharField(max_length=6,
                            choices=ACCESS_PROTOCOL_CHOICES,
                            help_text="How the space can be accessed.")
    size = models.BigIntegerField(default=None, null=True, blank=True,
                                  help_text="Size in bytes")
    used = models.BigIntegerField(default=0,
                                  help_text="Amount used in bytes")
    path = models.TextField()
    verified = models.BooleanField(default=False,
                                   help_text="Whether or not the space has been verified to be accessible.")

    def __unicode__(self):
        return "{uuid}: {path} ({access_protocol})".format(
            uuid=self.uuid,
            access_protocol=self.access_protocol,
            path=self.path,
            )


class LocalFilesystem(models.Model):
    """ Spaces found in the local filesystem."""
    space = models.OneToOneField('Space', to_field='uuid')
    # Does not currently need any other information - delete?


class Samba(models.Model):
    """ Spaces accessed over SAMBA. """
    space = models.OneToOneField('Space', to_field='uuid')

    username = models.CharField(max_length=256)
    password = models.CharField(max_length=256)
    remote_name = models.CharField(max_length=256)


########################## LOCATIONS ##########################

class Location(models.Model):
    """ Stores information about a location. """

    uuid = UUIDField(editable=False, unique=True, help_text="Unique identifier")
    space = models.ForeignKey('Space', to_field='uuid')

    TRANSFER_SOURCE = 'TS'
    AIP_STORAGE = 'AS'
    # QUARANTINE = 'QU'
    # BACKLOG = 'BL'

    PURPOSE_CHOICES = (
        (TRANSFER_SOURCE, 'Transfer Source'),
        (AIP_STORAGE, 'AIP Storage'),
        # (QUARANTINE, 'Quarantine'),
        # (BACKLOG, 'Backlog Transfer'),
    )
    purpose = models.CharField(max_length=2,
                               choices=PURPOSE_CHOICES,
                               help_text="Purpose of the space.  Eg. AIP storage, Transfer source")

    path = models.TextField()
    quota = models.BigIntegerField(default=None, null=True, blank=True,
                                   help_text="Size in bytes")
    used = models.BigIntegerField(default=0,
                                  help_text="Amount used in bytes")
    disabled = models.BooleanField(default=False,
                                   help_text="True if space should no longer be accessed.")

    def __unicode__(self):
        return "{uuid}: {path} ({purpose})".format(
            uuid=self.uuid,
            purpose=self.purpose,
            path=self.path,
            )

# For validation of resources
class LocationForm(forms.ModelForm):
    class Meta:
        model = Location

########################## FILES ##########################

# Currently untested
class File(models.Model):
    """ A file stored in a specific location. """
    uuid = UUIDField(editable=False, unique=True)
    location = models.ForeignKey(Location, to_field='uuid')
    path = models.TextField()
    size = models.IntegerField()
    # package_type = models.CharField() # eg. AIP, SIP, DIP, Transfer, File

    def __unicode__(self):
        return "{uuid}: {path} in {location}".format(
            uuid=self.uuid,
            path=self.path,
            location=self.location,
            )

