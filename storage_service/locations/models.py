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
            self.model._meta.get_field_by_name('enabled')
        except models.FieldDoesNotExist:
            try:
                self.model._meta.get_field_by_name('disabled')
            except models.FieldDoesNotExist:
                return super(Enabled, self).get_query_set()
            else:
                return super(Enabled, self).get_query_set().filter(disabled=False)
        else:  # found enabled
            return super(Enabled, self).get_query_set().filter(enabled=True)




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
    PIPELINE_LOCAL_FS = 'PIPE_FS'
    # LOCKSS = 'LOCKSS'
    # FEDORA = 'FEDORA'
    ACCESS_PROTOCOL_CHOICES = (
        (LOCAL_FILESYSTEM, "Local Filesystem"),
        (NFS, "NFS"),
        (PIPELINE_LOCAL_FS, "Pipeline Local Filesystem"),
    )
    access_protocol = models.CharField(max_length=8,
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


class PipelineLocalFS(models.Model):
    """ Spaces local to the creating machine, but not to the storage service.

    Use case: currently processing locations. """
    space = models.OneToOneField('Space', to_field='uuid')

    remote_user = models.CharField(max_length=64,
        help_text="Username on the remote machine accessible via ssh")
    remote_name = models.CharField(max_length=256,
        help_text="Name or IP of the remote machine.")
    # Space.path is the path on the remote machine


# To add a new storage space the following places must be updated:
#  locations/models.py (this file)
#   Add constant for storage protocol
#   Add constant to ACCESS_PROTOCOL_CHOICES
#   Add class for protocol-specific fields using template below
#   Add to Package.store_aip(), using existing categories if possible
#  locations/forms.py
#   Add ModelForm for new class
#  common/constants.py
#   Add entry to protocol with fields that should be added to GET resource
#     requests, the Model and ModelForm

# class Example(models.Model):
#     space = models.OneToOneField('Space', to_field='uuid')
#


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
    pipeline = models.ManyToManyField('Pipeline', through='LocationPipeline',
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


class LocationPipeline(models.Model):
    location = models.ForeignKey('Location', to_field='uuid')
    pipeline = models.ForeignKey('Pipeline', to_field='uuid')

    def __unicode__(self):
        return u'{} to {}'.format(self.location, self.pipeline)

########################## PACKAGES ##########################
# NOTE If the Packages section gets much bigger, move to its own app

class Package(models.Model):
    """ A package stored in a specific location. """
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
        help_text="Status of the package in the storage service.")

    def __unicode__(self):
        return u"{uuid}: {path}".format(
            uuid=self.uuid,
            path=self.full_path(),
        )
        # return "File: {}".format(self.uuid)

    def full_path(self):
        """ Return the full path of the package's current location.

        Includes the space, location, and package paths joined. """
        return os.path.normpath(
            os.path.join(self.current_location.full_path(), self.current_path))

    def full_origin_path(self):
        """ Return the full path of the package's original location.

        Includes the space, location, and package paths joined. """
        return os.path.normpath(
            os.path.join(self.origin_location.full_path(), self.origin_path))

    def store_aip(self):
        """ Stores an AIP in the correct Location.

        Invokes different transfer mechanisms depending on what the source and
        destination Spaces are.  Checks if there is space in the Space and
        Location for the AIP, and raises a StorageException if not.  All sizes
        expected to be in bytes.
        """
        # TODO Move some of the procesing in archivematica
        # clientScripts/storeAIP to here?

        # Check if enough space on the space and location
        # All sizes expected to be in bytes
        location = self.current_location
        dest_space = location.space
        if dest_space.size is not None and dest_space.used + self.size > dest_space.size:
            raise StorageException(
                "Not enough space for AIP on storage device {space}; Used: {used}; Size: {size}; AIP size: {aip_size}".format(
                space=dest_space, used=dest_space.used, size=dest_space.size,
                aip_size=self.size))
        if (location.quota is not None and
                location.used + self.size > location.quota):
            raise StorageException(
                "AIP too big for quota on {location}; Used: {used}; Quota: {quota}; AIP size: {aip_size}".format(
                    location=location, used=location.used, quota=location.quota,
                    aip_size=self.size))
        source_path = self.full_origin_path()

        # Store AIP at
        # destination_location/uuid/split/into/chunks/destination_path
        path = utils.uuid_to_path(self.uuid)
        self.current_path = os.path.join(path, self.current_path)
        self.save()
        destination_path = self.full_path()

        self.status = Package.PENDING
        self.save()

        # Call different protocols depending on what Space we're moving it to
        # and from
        mounted_locally = set([Space.LOCAL_FILESYSTEM, Space.NFS])
        ssh_only_access = set([Space.PIPELINE_LOCAL_FS])
        src_space = self.origin_location.space
        if src_space.access_protocol in mounted_locally and dest_space.access_protocol in mounted_locally:
            logging.info("Moving AIP from locally mounted storage to locally mounted storage.")
            self._store_aip_local_to_local(source_path, destination_path)
        elif src_space.access_protocol in ssh_only_access and dest_space.access_protocol in mounted_locally:
            logging.info("Moving AIP from SSH-only access storage to locally mounted storage.")
            self._store_aip_ssh_only_to_local(source_path, destination_path)
        elif src_space.access_protocol in ssh_only_access and dest_space.access_protocol in ssh_only_access:
            logging.info("Moving AIP from SSH-only access storage to SSH-only access storage.")
            self._store_aip_ssh_only_to_ssh_only(source_path, destination_path)
        else:
            # Not supported: mounted_locally to ssh_only_access
            logging.warning("Transfering package from {} to {} not supported".format(src_space.access_protocol, dest_space.access_protocol))
            return

        # Save new space/location usage, package status
        dest_space.used += self.size
        dest_space.save()
        location.used += self.size
        location.save()
        self.status = Package.UPLOADED
        self.save()

    def _store_aip_local_to_local(self, source_path, destination_path):
        """ Stores AIPs to locations accessible locally to the storage service.

        Checks if there is space in the Space and Location for the AIP, and raises
        a StorageException if not.  All sizes expected to be in bytes.

        AIP is stored at:
        destination_location/uuid/split/into/chunks/destination_path. """
        # Create directories
        logging.info("rsyncing from {} to {}".format(source_path, destination_path))
        try:
            mode = (stat.S_IRUSR + stat.S_IWUSR + stat.S_IXUSR +
                    stat.S_IRGRP +                stat.S_IXGRP +
                    stat.S_IROTH +                stat.S_IXOTH)
            os.makedirs(os.path.dirname(destination_path), mode)
            # Mode not getting set correctly
            os.chmod(os.path.dirname(destination_path), mode)
        except OSError as e:
            if e.errno != 17:
                logging.warning("Could not create storage directory: {}".format(e))
                raise
        # Rsync file over
        # TODO use Gearman to do this asyncronously
        command = ['rsync', '--chmod=u+rw,go-rwx', source_path, destination_path]
        logging.info("rsync command: {}".format(command))
        try:
            subprocess.check_call(command)
        except Exception as e:
            logging.warning("Rsync failed: {}".format(e))
            raise

    def _store_aip_ssh_only_to_local(self, source_path, destination_path):
        # Local to local uses rsync, so pass it a source_path that includes
        # user@host:path
        # Get correct protocol-specific model, and then the correct object
        # Importing PROTOCOL here because importing locations.constants at the
        # top of the file causes a circular dependency
        from .constants import PROTOCOL
        protocol = self.origin_location.space.access_protocol
        protocol_model = PROTOCOL[protocol]['model']
        protocol_space = protocol_model.objects.get(space=self.origin_location.space)
        # TODO try-catch AttributeError if remote_user or remote_name not exist?
        user = protocol_space.remote_user
        host = protocol_space.remote_name
        full_source_path = "{user}@{host}:{path}".format(user=user, host=host,
            path=source_path)
        self._store_aip_local_to_local(full_source_path, destination_path)

    def _store_aip_ssh_only_to_ssh_only(self, source_path, destination_path):
        raise Exception("Moving AIP within SSH only access spaces not implemented yet.")


class Event(models.Model):
    """ Stores requests to modify packages that need admin approval.

    Eg. delete AIP can be requested by a pipeline, but needs storage
    administrator approval.  Who made the request and why is also stored. """
    package = models.ForeignKey('Package', to_field='uuid')
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
        return u"{event_status} request to {event_type} {package}".format(
            event_status=self.get_status_display(),
            event_type=self.get_event_type_display(),
            package=self.package)


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
