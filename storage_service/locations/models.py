import datetime
import os.path

from django import forms
from django.core.exceptions import ValidationError
from django.db import models

from django_extensions.db.fields import UUIDField

########################## SPACES ##########################

class Space(models.Model):

    def validate_path(path):
        if path[0] != '/':
            raise ValidationError("Path must begin with a /")

    uuid = UUIDField(editable=False, unique=True, version=4, help_text="Unique identifier")

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
    path = models.TextField(validators=[validate_path])
    verified = models.BooleanField(default=False,
                                   help_text="Whether or not the space has been verified to be accessible.")
    last_verified = models.DateTimeField(default=None, null=True, blank=True,
        help_text="Time this location was last verified to be accessible.")

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

    def save(self, *args, **kwargs):
        self.verify()
        super(LocalFilesystem, self).save(*args, **kwargs)

    def verify(self):
        """ Verify that the space is accessible to the storage service. """
        # TODO run script to verify that it works
        verified = os.path.isdir(self.space.path)
        self.space.verified = verified
        self.space.last_verified = datetime.datetime.now()


class Samba(models.Model):
    """ Spaces accessed over SAMBA. """
    space = models.OneToOneField('Space', to_field='uuid')

    username = models.CharField(max_length=256)
    password = models.CharField(max_length=256)
    remote_name = models.CharField(max_length=256)

# For validation of resources
class SpaceForm(forms.ModelForm):
    class Meta:
        model = Space


########################## LOCATIONS ##########################

class Location(models.Model):
    """ Stores information about a location. """

    def validate_path(path):
        if path[0] == '/':
            raise ValidationError("Path cannot begin with a /")

    uuid = UUIDField(editable=False, unique=True, version=4, help_text="Unique identifier")
    storage_space = models.ForeignKey('Space', to_field='uuid')
    # storage_space cannot be called the same thing as the ForeignKey in 
    # resources.py , because of iteractions with Tastypie, see 
    # https://github.com/toastdriven/django-tastypie/issues/152 for details

    TRANSFER_SOURCE = 'TS'
    AIP_STORAGE = 'AS'
    # QUARANTINE = 'QU'
    # BACKLOG = 'BL'
    CURRENTLY_PROCESSING = 'CP'

    PURPOSE_CHOICES = (
        (TRANSFER_SOURCE, 'Transfer Source'),
        (AIP_STORAGE, 'AIP Storage'),
        # (QUARANTINE, 'Quarantine'),
        # (BACKLOG, 'Backlog Transfer'),
        (CURRENTLY_PROCESSING, 'Currently Processing'),
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

    def full_path(self):
        return os.path.join(self.storage_space.path, self.path)

# For validation of resources
class LocationForm(forms.ModelForm):
    class Meta:
        model = Location

########################## FILES ##########################

# Currently untested
class File(models.Model):
    """ A file stored in a specific location. """
    uuid = UUIDField(editable=False, unique=True, version=4, help_text="Unique identifier")
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

