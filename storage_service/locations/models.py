# stdlib, alphabetical
import ast
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
logging.basicConfig(filename="/tmp/storage-service.log",
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
    SWORD_SERVER = 'SWORD_S'
    # LOCKSS = 'LOCKSS'
    # FEDORA = 'FEDORA'
    ACCESS_PROTOCOL_CHOICES = (
        (LOCAL_FILESYSTEM, "Local Filesystem"),
        (NFS, "NFS"),
        (PIPELINE_LOCAL_FS, "Pipeline Local Filesystem"),
        (SWORD_SERVER, "SWORD Server"),
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
    staging_path=models.TextField(validators=[validate_space_path],
        help_text="Absolute path to a staging area.  Must be UNIX filesystem compatible, preferably on the same filesystem as the path.")
    verified = models.BooleanField(default=False,
       help_text="Whether or not the space has been verified to be accessible.")
    last_verified = models.DateTimeField(default=None, null=True, blank=True,
        help_text="Time this location was last verified to be accessible.")

    mounted_locally = set([LOCAL_FILESYSTEM, NFS, SWORD_SERVER])
    ssh_only_access = set([PIPELINE_LOCAL_FS])

    class Meta:
        verbose_name = 'Space'

    def __unicode__(self):
        return u"{uuid}: {path} ({access_protocol})".format(
            uuid=self.uuid,
            access_protocol=self.get_access_protocol_display(),
            path=self.path,
        )

    def get_child_space(self):
        """ Returns the protocol-specific space object. """
        # Importing PROTOCOL here because importing locations.constants at the
        # top of the file causes a circular dependency
        from .constants import PROTOCOL
        protocol_model = PROTOCOL[self.access_protocol]['model']
        protocol_space = protocol_model.objects.get(space=self)
        # TODO try-catch AttributeError if remote_user or remote_name not exist?
        return protocol_space

    def browse(self, path):
        """ Returns {'directories': [directory], 'entries': [entries]} at path.

        `path` is a full path in this space.

        'directories' in the return dict is the name of all the directories
            located at that path
        'entries' in the return dict is the name of any file (directory or other)
            located at that path
        """
        if self.access_protocol in self.mounted_locally:
            # Sorted list of all entries in directory, excluding hidden files
            # This may need magic for encoding/decoding, but doesn't seem to
            if isinstance(path, unicode):
                path = str(path)
            entries = [name for name in os.listdir(path) if name[0] != '.']
            entries = sorted(entries, key=lambda s: s.lower())
            directories = []
            for name in entries:
                full_path = os.path.join(path, name)
                if os.path.isdir(full_path) and os.access(full_path, os.R_OK):
                    directories.append(name)
        elif self.access_protocol in self.ssh_only_access:
            protocol_space = self.get_child_space()
            user = protocol_space.remote_user
            host = protocol_space.remote_name
            private_ssh_key = '/var/lib/archivematica/.ssh/id_rsa'
            # Get entries
            command = "python2 -c \"import os; print os.listdir('{path}')\"".format(path=path)
            ssh_command = ["ssh",  "-i", private_ssh_key, user+"@"+host, command]
            logging.info("ssh+rsync command: {}".format(ssh_command))
            try:
                entries = subprocess.check_output(ssh_command)
                entries = ast.literal_eval(entries)
            except Exception as e:
                logging.warning("ssh+sync failed: {}".format(e))
                entries = []
            # Get directories
            command = "python2 -c \"import os; print [d for d in os.listdir('{path}') if d[0] != '.' and os.path.isdir(os.path.join('{path}', d))]\"".format(path=path)
            ssh_command = ["ssh",  "-i", private_ssh_key, user+"@"+host, command]
            logging.info("ssh+rsync command: {}".format(ssh_command))
            try:
                directories = subprocess.check_output(ssh_command)
                directories = ast.literal_eval(directories)
                print 'directories eval', directories
            except Exception as e:
                logging.warning("ssh+sync failed: {}".format(e))
                print 'exception', e
                directories = []
        else:
            # Error
            logging.error("Unexpected category of access protocol ({}): browse failed".format(self.access_protocol))
            directories = []
            entries = []
        return {'directories': directories, 'entries': entries}

    def move_to_storage_service(self, source_path, destination_path,
                                destination_space, *args, **kwargs):
        """ Move source_path to destination_path in the staging area of destination_space.

        If source_path is not an absolute path, it is assumed to be relative to
        Space.path.

        destination_path must be relative and destination_space.staging_path
        MUST be locally accessible to the storage service.

        This is implemented by the child protocol spaces.
        """
        logging.debug('TO: src: {}'.format(source_path))
        logging.debug('TO: dst: {}'.format(destination_path))
        logging.debug('TO: staging: {}'.format(destination_space.staging_path))
        # TODO move the path mangling to here?
        # TODO enforce source_path is inside self.path
        try:
            self.get_child_space().move_to_storage_service(
                source_path, destination_path, destination_space, *args, **kwargs)
        except AttributeError:
            raise NotImplementedError('{} space has not implemented move_to_storage_service'.format(self.get_access_protocol_display()))

    def post_move_to_storage_service(self, *args, **kwargs):
        """ Hook for any actions that need to be taken after moving to the storage service. """
        try:
            self.get_child_space().post_move_to_storage_service(*args, **kwargs)
        except AttributeError:
            # This is optional for the child class to implement
            pass

    def move_from_storage_service(self, source_path, destination_path,
                                  *args, **kwargs):
        """ Move source_path in this Space's staging area to destination_path in this Space.

        That is, moves self.staging_path/source_path to self.path/destination_path.

        If destination_path is not an absolute path, it is assumed to be
        relative to Space.path.

        source_path must be relative to self.staging_path.

        This is implemented by the child protocol spaces.
        """
        logging.debug('FROM: src: {}'.format(source_path))
        logging.debug('FROM: dst: {}'.format(destination_path))
        # TODO move the path mangling to here?
        # TODO enforce destination_path is inside self.path
        try:
            self.get_child_space().move_from_storage_service(
                source_path, destination_path, *args, **kwargs)
        except AttributeError:
            raise NotImplementedError('{} space has not implemented move_from_storage_service'.format(self.get_access_protocol_display()))

    def post_move_from_storage_service(self, *args, **kwargs):
        """ Hook for any actions that need to be taken after moving from the storage service to the final destination. """
        try:
            self.get_child_space().post_move_from_storage_service(*args, **kwargs)
        except AttributeError:
            # This is optional for the child class to implement
            pass

    # HELPER FUNCTIONS

    def _move_locally(self, source_path, destination_path, mode=None):
        """ Moves a file from source_path to destination_path on the local filesystem. """
        logging.info("Moving from {} to {}".format(source_path, destination_path))

        # Create directories
        self._create_local_directory(destination_path, mode)

        # Move the file
        os.rename(source_path, destination_path)

    def _move_rsync(self, source, destination):
        """ Moves a file from source to destination using rsync.

        All directories leading to destination must exist.
        Space._create_local_directory may be useful.
        """
        # Create directories
        logging.info("Rsyncing from {} to {}".format(source, destination))

        # Rsync file over
        # TODO Do this asyncronously, with restarting failed attempts
        command = ['rsync', '--chmod=ugo+rw', '-r', source, destination]
        logging.info("rsync command: {}".format(command))
        try:
            subprocess.check_call(command)
        except Exception as e:
            logging.warning("Rsync failed: {}".format(e))
            raise

    def _create_local_directory(self, path, mode=None):
        """ Creates a local directory at 'path' with 'mode' (default 755). """
        if mode is None:
            mode = (stat.S_IRUSR + stat.S_IWUSR + stat.S_IXUSR +
                    stat.S_IRGRP +                stat.S_IXGRP +
                    stat.S_IROTH +                stat.S_IXOTH)
        try:
            os.makedirs(os.path.dirname(path), mode)
        except os.error as e:
            # If the leaf node already exists, that's fine
            if e.errno != errno.EEXIST:
                logging.warning("Could not create storage directory: {}".format(e))
                raise

        # Mode not getting set correctly in os.makedirs
        # Some spaces (eg CIFS) doesn't allow chmod, so wrap it in a try-catch
        # and ignore the failure.
        try:
            os.chmod(os.path.dirname(path), mode)
        except os.error as e:
            logging.warning(e)


class LocalFilesystem(models.Model):
    """ Spaces found in the local filesystem of the storage service."""
    space = models.OneToOneField('Space', to_field='uuid')

    class Meta:
        verbose_name = "Local Filesystem"

    def move_to_storage_service(self, src_path, dest_path, dest_space):
        """ Moves src_path to dest_space.staging_path/dest_path. """
        source_path = os.path.join(self.space.path, src_path)
        # dest_path must be relative
        if os.path.isabs(dest_path):
            dest_path = dest_path.lstrip(os.sep)
            # os.path.join(*dest_path.split(os.sep)[1:]) # Strips up to first os.sep
        destination_path = os.path.join(dest_space.staging_path, dest_path)
        # Archivematica expects the file to still be on disk even after stored
        self.space._create_local_directory(destination_path)
        return self.space._move_rsync(source_path, destination_path)

    def move_from_storage_service(self, src_path, dest_path):
        """ Moves self.staging_path/src_path to dest_path. """
        # src_path must be relative
        if os.path.isabs(src_path):
            src_path = src_path.lstrip(os.sep)
            # os.path.join(*src_path.split(os.sep)[1:]) # Strips up to first os.sep
        source_path = os.path.join(self.space.staging_path, src_path)
        destination_path = os.path.join(self.space.path, dest_path)
        return self.space._move_locally(source_path, destination_path)

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

    class Meta:
        verbose_name = "Network File System (NFS)"

    def move_to_storage_service(self, src_path, dest_path, dest_space):
        """ Moves src_path to dest_space.staging_path/dest_path. """
        source_path = os.path.join(self.space.path, src_path)
        # dest_path must be relative
        if os.path.isabs(dest_path):
            dest_path = dest_path.lstrip(os.sep)
            # os.path.join(*dest_path.split(os.sep)[1:]) # Strips up to first os.sep
        destination_path = os.path.join(dest_space.staging_path, dest_path)
        self.space._create_local_directory(destination_path)
        return self.space._move_rsync(source_path, destination_path)

    def post_move_to_storage_service(self, *args, **kwargs):
        # TODO delete original file?
        pass

    def move_from_storage_service(self, src_path, dest_path):
        """ Moves self.staging_path/src_path to dest_path. """
        # src_path must be relative
        if os.path.isabs(src_path):
            src_path = src_path.lstrip(os.sep)
            # os.path.join(*src_path.split(os.sep)[1:]) # Strips up to first os.sep
        source_path = os.path.join(self.space.staging_path, src_path)
        destination_path = os.path.join(self.space.path, dest_path)
        # TODO optimization - check if the staging path and destination path are on the same device and use os.rename/self.space._move_locally if so
        self.space._create_local_directory(destination_path)
        return self.space._move_rsync(source_path, destination_path)

    def post_move_from_storage_service(self, staging_file):
        # Remove the staging file, since rsync leaves it behind
        os.remove(staging_file)

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

    class Meta:
        verbose_name = "Pipeline Local FS"

    def move_to_storage_service(self, src_path, dest_path, dest_space):
        """ Moves src_path to dest_space.staging_path/dest_path. """
        # if dest_space == self:
        #     # If moving within same space, don't bring to storage service
        #     # FIXME dest_path is relative, and intended for staging_path, need
        #     # real destination path - memoize something and retrieve it in
        #     # move_from_storage_service?  Move to self.space.path/dest_path?
        #     command = 'mkdir -p {dest_dir} && mv {src_path} {dest_path}'.format(
        #         dest_dir=os.path.dirname(dest_path),
        #         src_user=self.remote_user, src_host=self.remote_name,
        #         src_path=src_path, dest_path=dest_path,
        #         )
        #     ssh_command = ["ssh", self.remote_user+"@"+self.remote_name, command]
        #     logging.info("ssh+mv command: {}".format(ssh_command))
        #     try:
        #         subprocess.check_call(ssh_command)
        #     except Exception as e:
        #         logging.warning("ssh+mv failed: {}".format(e))
        #         raise
        # else:
        source_path = "{user}@{host}:{path}".format(
            user=self.remote_user,
            host=self.remote_name,
            path=os.path.join(self.space.path, src_path))
        # dest_path must be relative
        if os.path.isabs(dest_path):
            dest_path = dest_path.lstrip(os.sep)
            # os.path.join(*dest_path.split(os.sep)[1:]) # Strips up to first os.sep
        destination_path = os.path.join(dest_space.staging_path, dest_path)
        self.space._create_local_directory(destination_path)
        return self.space._move_rsync(source_path, destination_path)

    def post_move_to_storage_service(self, *args, **kwargs):
        # TODO delete original file?
        pass

    def move_from_storage_service(self, src_path, dest_path):
        """ Moves self.staging_path/src_path to dest_path. """
        # src_path must be relative
        if os.path.isabs(src_path):
            src_path = src_path.lstrip(os.sep)
            # os.path.join(*src_path.split(os.sep)[1:]) # Strips up to first os.sep
        source_path = os.path.join(self.space.staging_path, src_path)
        destination_path = os.path.join(self.space.path, dest_path)

        # Need to make sure destination exists
        command = 'mkdir -p {}'.format(os.path.dirname(destination_path))
        ssh_command = ["ssh", self.remote_user+"@"+self.remote_name, command]
        logging.info("ssh+mkdir command: {}".format(ssh_command))
        try:
            subprocess.check_call(ssh_command)
        except Exception as e:
            logging.warning("ssh+mkdir failed: {}".format(e))
            raise

        # Prepend user and host to destination
        destination_path = "{user}@{host}:{path}".format(
            user=self.remote_user,
            host=self.remote_name,
            path=destination_path)

        # Move file
        return self.space._move_rsync(source_path, destination_path)

    def post_move_from_storage_service(self, *args, **kwargs):
        # TODO delete staging file?
        pass


class SwordServer(models.Model):
    """ SWORD server that accepts deposits."""
    space = models.OneToOneField('Space', to_field='uuid')
    pipeline = models.ForeignKey('Pipeline', to_field='uuid')

    def save(self, *args, **kwargs):
        self.verify()
        super(SwordServer, self).save(*args, **kwargs)

    def verify(self):
        """ Verify that the space is accessible to the storage service. """
        # TODO run script to verify that it works
        verified = os.path.isdir(self.space.path)
        self.space.verified = verified
        self.space.last_verified = datetime.datetime.now()


# To add a new storage space the following places must be updated:
#  locations/models.py (this file)
#   Add constant for storage protocol
#   Add constant to ACCESS_PROTOCOL_CHOICES
#   Add class for protocol-specific fields using template below
#   Add to Space.browse, using existing categories if possible
#  locations/forms.py
#   Add ModelForm for new class
#  common/constants.py
#   Add entry to protocol
#    'model' is the model object
#    'form' is the ModelForm for creating the space
#    'fields' is a whitelist of fields to display to the user

# class Example(models.Model):
#     space = models.OneToOneField('Space', to_field='uuid')
#
#     class Meta:
#         verbose_name = "Example Space"
#
#     def move_to_storage_service(self, src_path, dest_path, dest_space):
#         """ Moves src_path to dest_space.staging_path/dest_path. """
#         pass
#
#     def move_from_storage_service(self, src_path, dest_path):
#         """ Moves self.staging_path/src_path to dest_path. """
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
    STORAGE_SERVICE_INTERNAL = 'SS'
    SWORD_DEPOSIT = 'SD'

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

    # SWORD-related attributes
    deposit_completion_time = models.DateTimeField(default=None, null=True, blank=True)
    ready_for_finalization = models.BooleanField(default=False)
    finalization_attempt_failed = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Location"

    objects = models.Manager()
    active = Enabled()

    def __unicode__(self):
        return u"{uuid}: {path} ({purpose})".format(
            uuid=self.uuid,
            purpose=self.get_purpose_display(),
            path=self.full_path(),
        )

    def full_path(self):
        """ Returns full path of location: space + location paths. """
        return os.path.normpath(
            os.path.join(self.space.path, self.relative_path))

    def get_description(self):
        """ Returns a user-friendly description (or the path). """
        return self.description or self.full_path()

    # SWORD-related methods
    def has_been_submitted_for_processing(self):
        return self.deposit_completion_time != None

class LocationPipeline(models.Model):
    location = models.ForeignKey('Location', to_field='uuid')
    pipeline = models.ForeignKey('Pipeline', to_field='uuid')

    class Meta:
        verbose_name = "Location associated with a Pipeline"

    def __unicode__(self):
        return u'{} is associated with {}'.format(self.location, self.pipeline)

# For SWORD asynchronous downloading support
class LocationDownloadTask(models.Model):
    uuid = UUIDField(editable=False, unique=True, version=4,
        help_text="Unique identifier")
    location = models.ForeignKey('Location', to_field='uuid')

    downloads_attempted = models.IntegerField(default=0)
    downloads_completed = models.IntegerField(default=0)
    download_completion_time = models.DateTimeField(default=None, null=True, blank=True)

    """
    In order to determine the downloading status we need to check
    for three possibilities:

    1) The task involved no downloads. The downloads_attempted
       DB row column should be 0. This would be unusual, however,
       as there's no reason to make a task if not attempting
       to download anything.

    2) The task is downloading, but the downloading is not
       yet complete. downloads_attempted is greater than 0, but
       download_completion_time is not set.

    3) The task finished downloading and completed successfully.
       download_completion_time is set. downloads_attempted is
       equal to downloads_completed.

    4) The task finished downloading and completed unsuccessfully.
       download_completion_time is set. downloads_attempted isn't
       equal to downloads_completed.
    """
    def downloading_status(self):
        if self.downloads_attempted == 0:
            return 'complete'
        else:
            if self.download_completion_time == None:
                return 'incomplete'
            else:
                if self.downloads_attempted == self.downloads_completed:
                    return 'complete'
                else:
                    return 'failed'

class LocationDownloadTaskFile(models.Model):
    uuid = UUIDField(editable=False, unique=True, version=4,
        help_text="Unique identifier")
    task = models.ForeignKey('LocationDownloadTask', to_field='uuid')

    filename = models.CharField(max_length=256)
    url = models.TextField()

    completed = models.BooleanField(default=False,
        help_text="True if file downloaded successfully.")
    failed = models.BooleanField(default=False,
        help_text="True if file failed to download.")

    def downloading_status(self):
        if self.completed:
            return 'complete'
        else:
            if self.failed:
                return 'failed'
            else:
                return 'downloading'


########################## PACKAGES ##########################
# NOTE If the Packages section gets much bigger, move to its own app

class Package(models.Model):
    """ A package stored in a specific location. """
    uuid = UUIDField(editable=False, unique=True, version=4,
        help_text="Unique identifier")
    origin_pipeline = models.ForeignKey('Pipeline', to_field='uuid')
    current_location = models.ForeignKey(Location, to_field='uuid')
    current_path = models.TextField()
    pointer_file_location = models.ForeignKey(Location, to_field='uuid', related_name='+', null=True, blank=True)
    pointer_file_path = models.TextField(null=True, blank=True)
    size = models.IntegerField(default=0)

    AIP = "AIP"
    AIC = "AIC"
    SIP = "SIP"
    DIP = "DIP"
    TRANSFER = "transfer"
    FILE = 'file'
    PACKAGE_TYPE_CHOICES = (
        (AIP, 'AIP'),
        (AIC, 'AIC'),
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

    PACKAGE_TYPE_DELETABLE = (AIP, AIC)
    PACKAGE_TYPE_EXTRACTABLE = (AIP, AIC)

    class Meta:
        verbose_name = "Package"

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

    def full_pointer_file_path(self):
        """ Return the full path of the AIP's pointer file, None if not an AIP.

        Includes the space, location and package paths joined."""
        if self.package_type not in (self.AIP, self.AIC):
            return None
        else:
            return os.path.join(self.pointer_file_location.full_path(),
                self.pointer_file_path)

    def store_aip(self, origin_location, origin_path):
        """ Stores an AIP in the correct Location.

        Invokes different transfer mechanisms depending on what the source and
        destination Spaces are.  Checks if there is space in the Space and
        Location for the AIP, and raises a StorageException if not.  All sizes
        expected to be in bytes.
        """
        self.origin_location = origin_location
        self.origin_path = origin_path
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
        source_path = os.path.normpath(
            os.path.join(self.origin_location.full_path(), self.origin_path))

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

        src_space = self.origin_location.space

        # Move pointer file
        pointer_file_name = 'pointer-'+self.uuid+'.xml'
        src_space.move_to_storage_service(pointer_file_src, pointer_file_name, self.pointer_file_location.space)
        self.pointer_file_location.space.move_from_storage_service(pointer_file_name, pointer_file_dst)

        # Move AIP
        src_space.move_to_storage_service(
            source_path=os.path.join(self.origin_location.relative_path, self.origin_path),
            destination_path=self.current_path,  # This should include Location.path
            destination_space=dest_space)
        dest_space.move_from_storage_service(
            source_path=self.current_path,  # This should include Location.path
            destination_path=os.path.join(location.relative_path, self.current_path),
            )
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


    def delete_from_storage(self):
        """ Deletes the package from filesystem and updates metadata.

        Returns (True, None) on success, and (False, error_msg) on failure. """
        if self.current_location.space.access_protocol in Space.mounted_locally:
            try:
                os.remove(self.full_path())
            except os.error as e:
                logging.exception("Error deleting package.")
                return False, e.strerror
            # Remove uuid quad directories if they're empty
            utils.removedirs(os.path.dirname(self.current_path),
                base=self.current_location.full_path())
        elif self.current_location.space.access_protocol in Space.ssh_only_access:
            protocol_space = self.current_location.space.get_child_space()
            # TODO try-catch AttributeError if remote_user or remote_name not exist?
            user = protocol_space.remote_user
            host = protocol_space.remote_name
            command = 'rm -f '+self.full_path()
            ssh_command = ["ssh", user+"@"+host, command]
            logging.info("ssh+rsync command: {}".format(ssh_command))
            try:
                subprocess.check_call(ssh_command)
            except Exception as e:
                logging.exception("ssh+sync failed.")
                return False, "Error connecting to Location"

        # Remove pointer file, and the UUID quad directories if they're empty
        try:
            os.remove(self.full_pointer_file_path())
        except os.error as e:
            logging.exception("Error deleting pointer file {} for package {}".format(self.full_pointer_file_path(), self.uuid))

        utils.removedirs(os.path.dirname(self.pointer_file_path),
            base=self.pointer_file_location.full_path())

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

    class Meta:
        verbose_name = "Event"

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
    remote_name = models.CharField(max_length=256, default=None,
        null=True, blank=True,
        help_text="Host or IP address of the pipeline server for making API calls.")
    api_username = models.CharField(max_length=256, default=None,
        null=True, blank=True,
        help_text="Username to use when making API calls to the pipeline.")
    api_key = models.CharField(max_length=256, default=None,
        null=True, blank=True,
        help_text="API key to use when making API calls to the pipeline.")
    enabled = models.BooleanField(default=True,
        help_text="Enabled if this pipeline is able to access the storage service.")

    class Meta:
        verbose_name = "Pipeline"

    objects = models.Manager()
    active = Enabled()

    def __unicode__(self):
        return u"{description} ({uuid})".format(
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

        Also create a SWORD server Space.
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
        currently_processing, _ = Location.objects.get_or_create(
            purpose=Location.CURRENTLY_PROCESSING,
            space=space,
            relative_path=shared_path)
        LocationPipeline.objects.get_or_create(
            pipeline=self, location=currently_processing)
        logging.info("Currently processing: {}".format(currently_processing))

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

        # create SWORD space if it doesn't already exist
        space_path = os.path.join(os.path.join('/', shared_path), 'staging', 'deposits', self.uuid)
        space, space_created = Space.objects.get_or_create(
            access_protocol=Space.SWORD_SERVER, path=space_path)

        if space_created:
            try:
                os.makedirs(space_path)
            except OSError as e:
                if e.errno != errno.EEXIST:
                    logging.error("Unable to create directory {} for SWORD server space.".format(space.path))

        # create SWORD server for pipeline if it doesn't already exist
        sword_server, sword_server_created = SwordServer.objects.get_or_create(space=space, pipeline=self)
        if sword_server_created:
            logging.info("SWORD server created: {}".format(sword_server))
