import datetime
import logging
import os.path
import stat
import subprocess

from django.conf import settings
from django.core import validators
from django.core.exceptions import ValidationError
from django.db import models

from django_extensions.db.fields import UUIDField

import common.utils as utils

logger = logging.getLogger(__name__)
logging.basicConfig(#filename="/tmp/storage-service.log",
    level=logging.INFO)

########################## COMMON ##########################

class StorageException(Exception):
    """ Exceptions specific to the service."""
    pass

class Enabled(models.Manager):
    """ Manager to only return enabled objects.

    Filters by disable=False if it exists, or enabled=True if it exists, or
    returns all items if neither is found.  """
    def get_query_set(self):
        try:
            self.model._meta.get_field_by_name('disabled')
        except models.FieldDoesNotExist:
            try:
                self.model._meta.get_field_by_name('enabled')
            except models.FieldDoesNotExist:
                return super(Enabled, self).get_query_set()
            else:
                return super(Enabled, self).get_query_set().filter(enabled=True)
        else:  # found disabled
            return super(Enabled, self).get_query_set().filter(disabled=False)


def store_aip_local_path(aip_file):
    """ Stores AIPs to locations accessible locally to the storage service.

    Checks if there is space in the Space and Location for the AIP, and raises
    a StorageException if not.  All sizes expected to be in bytes.

    AIP is stored at:
    destination_location/uuid/split/into/chunks/destination_path. """
    # TODO Move some of the procesing in archivematica
    # clientScripts/storeAIP to here
    location = aip_file.current_location
    space = location.space
    if space.size is not None and space.used + aip_file.size > space.size:
        raise StorageException(
            "Not enough space for AIP on storage device {space}; Used: {used}; Size: {size}; AIP size: {aip_size}".format(
            space=space, used=space.used, size=space.size,
            aip_size=aip_file.size))
    if (location.quota is not None and
            location.used + aip_file.size > location.quota):
        raise StorageException(
            "AIP too big for quota on {location}; Used: {used}; Quota: {quota}; AIP size: {aip_size}".format(
                location=location, used=location.used, quota=location.quota,
                aip_size=aip_file.size))

    source = aip_file.full_origin_path()

    # Store AIP at
    # destination_location/uuid/split/into/chunks/destination_path
    path = utils.uuid_to_path(aip_file.uuid)
    aip_file.current_path = os.path.join(path, aip_file.current_path)
    aip_file.save()
    destination = aip_file.full_path()

    aip_file.status = File.PENDING
    aip_file.save()

    # Create directories
    logging.info("rsyncing from {} to {}".format(source, destination))
    try:
        mode = (stat.S_IRUSR + stat.S_IWUSR + stat.S_IXUSR +
                stat.S_IRGRP +                stat.S_IXGRP +
                stat.S_IROTH +                stat.S_IXOTH)
        os.makedirs(os.path.dirname(destination), mode)
        # Mode not getting set correctly
        os.chmod(os.path.dirname(destination), mode)
    except OSError as e:
        if e.errno != 17:
            logging.warning("Could not create storage directory: {}".format(e))
            raise
    # Rsync file over
    # TODO use Gearman to do this asyncronously
    command = ['rsync', '--chmod=u+rw,go-rwx', source, destination]
    logging.info("rsync command: {}".format(command))
    try:
        subprocess.check_call(command)
    except Exception as e:
        logging.warning("Rsync failed: {}".format(e))
        raise

    space.used += aip_file.size
    space.save()
    location.used += aip_file.size
    location.save()
    aip_file.status = File.UPLOADED
    aip_file.save()

def validate_space_path(path):
    """ Validation for path in Space.  Must be absolute. """
    if path[0] != '/':
        raise ValidationError("Path must begin with a /")


########################## SPACES ##########################

class Space(models.Model):
    """ Common storage space information.

    Knows what protocol to use to access a storage space, but all protocol
    specific information is in children classes with ForeignKeys to Space."""
    uuid = UUIDField(editable=False, unique=True, version=4,
        help_text="Unique identifier")

    LOCAL_FILESYSTEM = 'FS'
    NFS = 'NFS'
    # LOCKSS = 'LOCKSS'
    # FEDORA = 'FEDORA'
    ACCESS_PROTOCOL_CHOICES = (
        (LOCAL_FILESYSTEM, "Local Filesystem"),
        (NFS, "NFS")
    )
    access_protocol = models.CharField(max_length=6,
        choices=ACCESS_PROTOCOL_CHOICES,
        help_text="How the space can be accessed.")
    size = models.BigIntegerField(default=None, null=True, blank=True,
        help_text="Size in bytes (optional)")
    used = models.BigIntegerField(default=0,
        help_text="Amount used in bytes")
    path = models.TextField(validators=[validate_space_path],
        help_text="Absolute path to the space on the storage service machine.")
    verified = models.BooleanField(default=False,
       help_text="Whether or not the space has been verified to be accessible.")
    last_verified = models.DateTimeField(default=None, null=True, blank=True,
        help_text="Time this location was last verified to be accessible.")

    def __unicode__(self):
        return u"{uuid}: {path} ({access_protocol})".format(
            uuid=self.uuid,
            access_protocol=self.access_protocol,
            path=self.path,
        )

    def store_aip(self, *args, **kwargs):
        # FIXME there has to be a better way to do this
        if self.access_protocol == self.LOCAL_FILESYSTEM:
            self.localfilesystem.store_aip(*args, **kwargs)
        elif self.access_protocol == self.NFS:
            self.nfs.store_aip(*args, **kwargs)
        else:
            logging.warning("No access protocol for this space.")


class LocalFilesystem(models.Model):
    """ Spaces found in the local filesystem of the storage service."""
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

    def store_aip(self, aip_file, *args, **kwargs):
        """ Stores aip_file in this space. """
        # IDEA Make this a script that can be run? Would lose access to python
        # objects and have to pass UUIDs
        # Confirm that this is the correct space to be moving to
        assert self.space == aip_file.current_location.space
        store_aip_local_path(aip_file)


class NFS(models.Model):
    """ Spaces accessed over NFS. """
    space = models.OneToOneField('Space', to_field='uuid')

    # Space.path is the local path
    remote_name = models.CharField(max_length=256,
        help_text="Name of the NFS server.")
    remote_path = models.TextField(
        help_text="Path on the NFS server to the export.")
    version = models.CharField(max_length=64, default='nfs4',
        help_text="Type of the filesystem, i.e. nfs, or nfs4. \
        Should match a command in `mount`.")
    # https://help.ubuntu.com/community/NFSv4Howto

    manually_mounted = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        self.verify()
        super(NFS, self).save(*args, **kwargs)

    def verify(self):
        """ Verify that the space is accessible to the storage service. """
        # TODO run script to verify that it works
        if self.manually_mounted:
            verified = os.path.ismount(self.space.path)
            self.space.verified = verified
            self.space.last_verified = datetime.datetime.now()

    def mount(self):
        """ Mount the NFS export with the provided info. """
        # sudo mount -t nfs -o proto=tcp,port=2049 192.168.1.133:/export /mnt/
        # sudo mount -t self.version -o proto=tcp,port=2049 self.remote_name:self.remote_path self.space.path
        # or /etc/fstab
        # self.remote_name:self.remote_path   self.space.path   self.version    auto,user  0  0
        # may need to tweak options
        pass

    def store_aip(self, aip_file, *args, **kwargs):
        """ Stores aip_file in this space, at aip_file.current_location.

        Assumes that aip_file.current_location is mounted locally."""
        # IDEA Make this a script that can be run? Would lose access to python
        # objects and have to pass UUIDs
        # Confirm that this is the correct space to be moving to
        assert self.space == aip_file.current_location.space
        store_aip_local_path(aip_file)


# To add a new storage space the following places must be updated:
#  locations/models.py (this file)
#   Add constant for storage protocol
#   Add constant to ACCESS_PROTOCOL_CHOICES
#   Add class for protocol-specific fields using template below
#  locations/forms.py
#   Add ModelForm for new class
#  common/constants.py
#   Add entry to protocol with fields that should be added to GET resource
#     requests, the Model and ModelForm

# class Example(models.Model):
#     space = models.OneToOneField('Space', to_field='uuid')
#
#     def verify(self):
#         pass

########################## LOCATIONS ##########################

class Location(models.Model):
    """ Stores information about a location. """

    uuid = UUIDField(editable=False, unique=True, version=4,
        help_text="Unique identifier")
    space = models.ForeignKey('Space', to_field='uuid')

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
    pipeline = models.ForeignKey('Pipeline', to_field='uuid',
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

    objects = models.Manager()
    active = Enabled()

    def __unicode__(self):
        return u"{uuid}: {path} ({purpose})".format(
            uuid=self.uuid,
            purpose=self.purpose,
            path=self.relative_path,
        )

    def full_path(self):
        """ Returns full path of location: space + location paths. """
        return os.path.normpath(
            os.path.join(self.space.path, self.relative_path))

    def get_description(self):
        """ Returns a user-friendly description (or the path). """
        return self.description or self.full_path()


########################## FILES ##########################
# NOTE If the Files section gets much bigger, move to its own app

class File(models.Model):
    """ A file stored in a specific location. """
    uuid = UUIDField(editable=False, unique=True, version=4,
        help_text="Unique identifier")
    origin_location = models.ForeignKey(Location, to_field='uuid', related_name='+')
    origin_path = models.TextField()
    current_location = models.ForeignKey(Location, to_field='uuid', related_name='+')
    current_path = models.TextField()
    size = models.IntegerField(default=0)

    AIP = "AIP"
    SIP = "SIP"
    DIP = "DIP"
    TRANSFER = "transfer"
    FILE = 'file'
    PACKAGE_TYPE_CHOICES = (
        (AIP, 'AIP'),
        (SIP, 'SIP'),
        (DIP, 'DIP'),
        (TRANSFER, 'Transfer'),
        (FILE, 'Single File'),
    )
    package_type = models.CharField(max_length=8,
        choices=PACKAGE_TYPE_CHOICES,
        help_text="Purpose of the space.  Eg. AIP storage, Transfer source")

    PENDING = 'PENDING'
    UPLOADED = 'UPLOADED'
    VERIFIED = 'VERIFIED'
    DEL_REQ = 'DEL_REQ'
    DELETED = 'DELETED'
    FAIL = 'FAIL'
    STATUS_CHOICES = (
        (PENDING, "Upload Pending"),
        (UPLOADED, "Uploaded"),
        (VERIFIED, "Verified"),
        (FAIL, "Failed"),
        (DEL_REQ, "Delete requested"),
        (DELETED, "Deleted"),
    )
    status = models.CharField(max_length=8, choices=STATUS_CHOICES,
        default=FAIL,
        help_text="Status of the file in the storage service.")

    def __unicode__(self):
        return u"{uuid}: {path}".format(
            uuid=self.uuid,
            path=self.full_path(),
        )
        # return "File: {}".format(self.uuid)

    def full_path(self):
        """ Return the full path of the file's current location.

        Includes the space, location, and file paths joined. """
        return os.path.normpath(
            os.path.join(self.current_location.full_path(), self.current_path))

    def full_origin_path(self):
        """ Return the full path of the file's original location.

        Includes the space, location, and file paths joined. """
        return os.path.normpath(
            os.path.join(self.origin_location.full_path(), self.origin_path))


class Event(models.Model):
    """ Stores requests to modify files that need admin approval.

    Eg. delete AIP can be requested by a pipeline, but needs storage
    administrator approval.  Who made the request and why is also stored. """
    file = models.ForeignKey('File', to_field='uuid')
    DELETE = 'DELETE'
    EVENT_TYPE_CHOICES = (
        (DELETE, 'delete'),
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

    def __unicode__(self):
        return u"{event_status} request to {event_type} {file}".format(
            event_status=self.get_status_display(),
            event_type=self.get_event_type_display(),
            file=self.file)


########################## OTHER ##########################

class Pipeline(models.Model):
    """ Information about Archivematica instances using the storage service. """
    uuid = UUIDField(unique=True, version=4, auto=False, verbose_name="UUID",
        help_text="Identifier for the Archivematica pipeline",
        validators=[validators.RegexValidator(
            r'\w{8}-\w{4}-\w{4}-\w{4}-\w{12}',
            "Needs to be format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx where x is a hexadecimal digit.",
            "Invalid UUID")])
    description = models.CharField(max_length=256, default=None,
        null=True, blank=True,
        help_text="Human readable description of the Archivematica instance.")
    enabled = models.BooleanField(default=True,
        help_text="Enabled if this pipeline is able to access the storage service.")

    objects = models.Manager()
    active = Enabled()

    def __unicode__(self):
        return u"{uuid} ({description})".format(
            uuid=self.uuid,
            description=self.description)
