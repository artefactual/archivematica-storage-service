# stdlib, alphabetical
import datetime
import errno
import logging
from lxml import etree
import os
import stat
import subprocess

# Core Django, alphabetical
from django.conf import settings
from django.core import validators
from django.core.exceptions import ValidationError
from django.db import models

# Third party dependencies, alphabetical
from django_extensions.db.fields import UUIDField

# This project, alphabetical
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
    STORAGE_SERVICE_INTERNAL = 'SS'

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
    # pointer_file = models.OneToOneField('self', to_field='uuid', related_name='package', null=True, blank=True)
    pointer_file_location = models.ForeignKey(Location, to_field='uuid', related_name='+', null=True, blank=True)
    pointer_file_path = models.TextField(null=True, blank=True)
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
    package_type = models.CharField(max_length=8, choices=PACKAGE_TYPE_CHOICES)

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


    mounted_locally = set([Space.LOCAL_FILESYSTEM, Space.NFS])
    ssh_only_access = set([Space.PIPELINE_LOCAL_FS])

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

    def full_pointer_file_path(self):
        """ Return the full path of the AIP's pointer file, None if not an AIP.

        Includes the space, location and package paths joined."""
        if self.package_type != self.AIP:
            return None
        else:
            return os.path.join(self.pointer_file_location.full_path(),
                self.pointer_file_path)

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

        # Store AIP Pointer File at
        # internal_usage_location/uuid/split/into/chunks/pointer.xml
        self.pointer_file_location = Location.active.get(purpose=Location.STORAGE_SERVICE_INTERNAL)
        self.pointer_file_path = os.path.join(path, 'pointer.xml')
        pointer_file_src = os.path.join(os.path.dirname(source_path), 'pointer.xml')
        pointer_file_dst = self.full_pointer_file_path()

        self.status = Package.PENDING
        self.save()

        # Create destination for pointer file

        # Call different protocols depending on what Space we're moving it to
        # and from
        src_space = self.origin_location.space
        if src_space.access_protocol in self.mounted_locally and dest_space.access_protocol in self.mounted_locally:
            logging.info("Moving AIP from locally mounted storage to locally mounted storage.")
            # Move pointer file
            self._store_aip_local_to_local(pointer_file_src, pointer_file_dst)
            # Move AIP
            self._store_aip_local_to_local(source_path, destination_path)
        elif src_space.access_protocol in self.ssh_only_access and dest_space.access_protocol in self.mounted_locally:
            logging.info("Moving AIP from SSH-only access storage to locally mounted storage.")
            # Move pointer file
            self._store_aip_ssh_only_to_local(pointer_file_src, pointer_file_dst)
            # Move AIP
            self._store_aip_ssh_only_to_local(source_path, destination_path)
        elif src_space.access_protocol in self.ssh_only_access and dest_space.access_protocol in self.ssh_only_access:
            logging.info("Moving AIP from SSH-only access storage to SSH-only access storage.")
            # Move pointer file
            self._store_aip_ssh_only_to_local(pointer_file_src, pointer_file_dst)
            # Move AIP
            self._store_aip_ssh_only_to_ssh_only(source_path, destination_path)
        else:
            # Not supported: self.mounted_locally to self.ssh_only_access
            logging.warning("Transfering package from {} to {} not supported".format(src_space.access_protocol, dest_space.access_protocol))
            return

        # Save new space/location usage, package status
        dest_space.used += self.size
        dest_space.save()
        location.used += self.size
        location.save()
        self.status = Package.UPLOADED
        self.save()

        # Update pointer file's location infrmation
        nsmap = {'mets': 'http://www.loc.gov/METS/'}
        root = etree.parse(pointer_file_dst)
        element = root.find('mets:fileSec/mets:fileGrp/mets:file', namespaces=nsmap)
        flocat = element.find('mets:FLocat', namespaces=nsmap)
        xlink = 'http://www.w3.org/1999/xlink'
        if self.uuid in element.get('ID', '') and flocat is not None:
            flocat.set('{{{ns}}}href'.format(ns=xlink), self.full_path())
        with open(pointer_file_dst, 'w') as f:
            f.write(etree.tostring(root, pretty_print=True))

    def _store_aip_local_to_local(self, source_path, destination_path):
        """ Stores AIPs to locations accessible locally to the storage service.

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
            if e.errno != errno.EEXIST:
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
        """ Stores an AIP from a location SSH-accessible to one accessible locally.

        AIP is stored at:
        destination_location/uuid/split/into/chunks/destination_path. """
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
        """ Stores AIPs from and to a location only accessible via SSH.

        AIP is stored at:
        destination_location/uuid/split/into/chunks/destination_path. """
        # Get correct protocol-specific model, and then the correct object
        # Importing PROTOCOL here because importing locations.constants at the
        # top of the file causes a circular dependency
        from .constants import PROTOCOL
        src_protocol = self.origin_location.space.access_protocol
        src_protocol_model = PROTOCOL[src_protocol]['model']
        src_protocol_space = src_protocol_model.objects.get(
            space=self.origin_location.space)
        dst_protocol = self.current_location.space.access_protocol
        dst_protocol_model = PROTOCOL[dst_protocol]['model']
        dst_protocol_space = dst_protocol_model.objects.get(
            space=self.current_location.space)
        # TODO try-catch AttributeError if remote_user or remote_name not exist?
        src_user = src_protocol_space.remote_user
        src_host = src_protocol_space.remote_name
        dst_user = dst_protocol_space.remote_user
        dst_host = dst_protocol_space.remote_name

        command = 'mkdir -p {dst_dir} && rsync {src_user}@{src_host}:{src_path} {dst_path}'.format(
            dst_dir=os.path.dirname(destination_path),
            src_user=src_user, src_host=src_host,
            src_path=source_path, dst_path=destination_path,
            )
        ssh_command = ["ssh", dst_user+"@"+dst_host, command]
        logging.info("ssh+rsync command: {}".format(ssh_command))
        try:
            subprocess.check_call(ssh_command)
        except Exception as e:
            logging.warning("ssh+sync failed: {}".format(e))
            raise

    def delete_from_storage(self):
        """ Deletes the package from filesystem and updates metadata.

        Returns (True, None) on success, and (False, error_msg) on failure. """
        if self.current_location.space.access_protocol in self.mounted_locally:
            try:
                os.remove(self.full_path())
            except OSError as e:
                logging.warning("Error deleting package: {}".format(e))
                return False, e.strerror
        elif self.current_location.space.access_protocol in self.ssh_only_access:
            from .constants import PROTOCOL
            protocol = self.current_location.space.access_protocol
            protocol_model = PROTOCOL[protocol]['model']
            protocol_space = protocol_model.objects.get(
                space=self.current_location.space)
            # TODO try-catch AttributeError if remote_user or remote_name not exist?
            user = protocol_space.remote_user
            host = protocol_space.remote_name
            command = 'rm -f '+self.full_path()
            ssh_command = ["ssh", user+"@"+host, command]
            logging.info("ssh+rsync command: {}".format(ssh_command))
            try:
                subprocess.check_call(ssh_command)
            except Exception as e:
                logging.warning("ssh+sync failed: {}".format(e))
                return False, "Error connecting to Location"

        self.status = self.DELETED
        self.save()
        return True, None

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

    def save(self, create_default_locations=False, shared_path=None, *args, **kwargs):
        """ Save pipeline and optionally create default locations. """
        super(Pipeline, self).save(*args, **kwargs)
        if create_default_locations:
            self.create_default_locations(shared_path)

    def create_default_locations(self, shared_path=None):
        """ Creates default locations for a pipeline based on config.

        Creates a local filesystem Space and currently processing location in
        it.  If a shared_path is provided, currently processing location is at
        that path.  Creates Transfer Source and AIP Store locations based on
        configuration from administration.Settings.
        """
        # Use shared path if provided
        if not shared_path:
            shared_path = '/var/archivematica/sharedDirectory'
        shared_path = shared_path.strip('/')+'/'
        logging.info("Creating default locations for pipeline {}.".format(self))

        space, space_created = Space.objects.get_or_create(
            access_protocol=Space.LOCAL_FILESYSTEM, path='/')
        if space_created:
            local_fs = LocalFilesystem(space=space)
            local_fs.save()
            logging.info("Protocol Space created: {}".format(local_fs))
        currently_processing = Location.objects.create(
            purpose=Location.CURRENTLY_PROCESSING,
            space=space,
            relative_path=shared_path)
        logging.info("Currently processing: {}".format(currently_processing))
        LocationPipeline(pipeline=self, location=currently_processing).save()

        purposes = [
            {'default': 'default_transfer_source',
             'new': 'new_transfer_source',
             'purpose': Location.TRANSFER_SOURCE},
            {'default': 'default_aip_storage',
             'new': 'new_aip_storage',
             'purpose': Location.AIP_STORAGE},
        ]
        for p in purposes:
            defaults = utils.get_setting(p['default'], [])
            for uuid in defaults:
                if uuid == 'new':
                    # Create new location
                    new_location = utils.get_setting(p['new'])
                    location = Location.objects.create(
                        purpose=p['purpose'], **new_location)
                else:
                    # Fetch existing location
                    location = Location.objects.get(uuid=uuid)
                    assert location.purpose == p['purpose']
                logging.info("Adding new {} {} to {}".format(
                    p['purpose'], location, self))
                LocationPipeline.objects.get_or_create(
                    pipeline=self, location=location)
