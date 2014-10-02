# stdlib, alphabetical
import errno
import logging
import os
import shutil
import stat
import subprocess

# Core Django, alphabetical
from django.core.exceptions import ValidationError
from django.db import models

# Third party dependencies, alphabetical
from django_extensions.db.fields import UUIDField

# This project, alphabetical
LOGGER = logging.getLogger(__name__)

# This module, alphabetical
from . import StorageException

__all__ = ('Space', )


def validate_space_path(path):
    """ Validation for path in Space.  Must be absolute. """
    if path[0] != '/':
        raise ValidationError("Path must begin with a /")

# To add a new storage space the following places must be updated:
#  locations/models/space.py (this file)
#   Add constant for storage protocol
#   Add constant to ACCESS_PROTOCOL_CHOICES
#  locations/models/<spacename>.py
#   Add class for protocol-specific fields using template below
#  locations/models/__init__.py
#   Add class to import list
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
#         app_label = 'locations'
#
#     ALLOWED_LOCATION_PURPOSE = [
#         Location.AIP_RECOVERY,
#         Location.AIP_STORAGE,
#         Location.CURRENTLY_PROCESSING,
#         Location.DIP_STORAGE,
#         Location.STORAGE_SERVICE_INTERNAL,
#         Location.TRANSFER_SOURCE,
#         Location.BACKLOG,
#     ]
#
#     def browse(self, path):
#         pass
#
#     def delete_path(self, delete_path):
#         pass
#
#     def move_to_storage_service(self, src_path, dest_path, dest_space):
#         """ Moves src_path to dest_space.staging_path/dest_path. """
#         pass
#
#     def move_from_storage_service(self, source_path, destination_path):
#         """ Moves self.staging_path/src_path to dest_path. """
#         pass


class Space(models.Model):
    """ Common storage space information.

    Knows what protocol to use to access a storage space, but all protocol
    specific information is in children classes with ForeignKeys to Space."""
    uuid = UUIDField(editable=False, unique=True, version=4,
        help_text="Unique identifier")

    DURACLOUD = 'DC'
    FEDORA = 'FEDORA'
    LOCAL_FILESYSTEM = 'FS'
    LOM = 'LOM'
    NFS = 'NFS'
    PIPELINE_LOCAL_FS = 'PIPE_FS'
    OBJECT_STORAGE = {DURACLOUD}
    ACCESS_PROTOCOL_CHOICES = (
        (DURACLOUD, 'DuraCloud'),
        (FEDORA, "FEDORA via SWORD2"),
        (LOCAL_FILESYSTEM, "Local Filesystem"),
        (LOM, "LOCKSS-o-matic"),
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
    path = models.TextField(default='', blank=True,
        help_text="Absolute path to the space on the storage service machine.")
    staging_path = models.TextField(validators=[validate_space_path],
        help_text="Absolute path to a staging area.  Must be UNIX filesystem compatible, preferably on the same filesystem as the path.")
    verified = models.BooleanField(default=False,
       help_text="Whether or not the space has been verified to be accessible.")
    last_verified = models.DateTimeField(default=None, null=True, blank=True,
        help_text="Time this location was last verified to be accessible.")

    class Meta:
        verbose_name = 'Space'
        app_label = 'locations'

    def __unicode__(self):
        return u"{uuid}: {path} ({access_protocol})".format(
            uuid=self.uuid,
            access_protocol=self.get_access_protocol_display(),
            path=self.path,
        )

    def clean(self):
        # Object storage spaces do not require a path, or for it to start with /
        if self.access_protocol not in self.OBJECT_STORAGE:
            if not self.path:
                raise ValidationError('Path is required')
            validate_space_path(self.path)

    def get_child_space(self):
        """ Returns the protocol-specific space object. """
        # Importing PROTOCOL here because importing locations.constants at the
        # top of the file causes a circular dependency
        from ..constants import PROTOCOL
        protocol_model = PROTOCOL[self.access_protocol]['model']
        protocol_space = protocol_model.objects.get(space=self)
        # TODO try-catch AttributeError if remote_user or remote_name not exist?
        return protocol_space

    def browse(self, path, *args, **kwargs):
        """ Returns {'directories': [directory], 'entries': [entries]} at path.

        `path` is a full path in this space.

        'directories' in the return dict is the name of all the directories
            located at that path
        'entries' in the return dict is the name of any file (directory or other)
            located at that path

        If not implemented in the child space, looks locally.
        """
        LOGGER.info('path: %s', path)
        try:
            return self.get_child_space().browse(path, *args, **kwargs)
        except AttributeError:
            return self._browse_local(path)

    def delete_path(self, delete_path, *args, **kwargs):
        """
        Deletes `delete_path` stored in this space.

        `delete_path` is a full path in this space.

        If not implemented in the child space, looks locally.
        """
        # Enforce delete_path is in self.path
        if not delete_path.startswith(self.path):
            raise ValueError('%s is not within %s', delete_path, self.path)
        try:
            return self.get_child_space().delete_path(delete_path, *args, **kwargs)
        except AttributeError:
            return self._delete_path_local(delete_path)

    def move_to_storage_service(self, source_path, destination_path,
                                destination_space, *args, **kwargs):
        """ Move source_path to destination_path in the staging area of destination_space.

        If source_path is not an absolute path, it is assumed to be relative to
        Space.path.

        destination_path must be relative and destination_space.staging_path
        MUST be locally accessible to the storage service.

        This is implemented by the child protocol spaces.
        """
        LOGGER.debug('TO: src: %s', source_path)
        LOGGER.debug('TO: dst: %s', destination_path)
        LOGGER.debug('TO: staging: %s', destination_space.staging_path)

        # TODO enforce source_path is inside self.path
        # Path pre-processing
        source_path = os.path.join(self.path, source_path)
        # dest_path must be relative
        if os.path.isabs(destination_path):
            destination_path = destination_path.lstrip(os.sep)
            # Alternative implementation
            # os.path.join(*destination_path.split(os.sep)[1:]) # Strips up to first os.sep
        destination_path = os.path.join(destination_space.staging_path, destination_path)

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
        LOGGER.debug('FROM: src: %s', source_path)
        LOGGER.debug('FROM: dst: %s', destination_path)

        # Path pre-processing
        # source_path must be relative
        if os.path.isabs(source_path):
            source_path = source_path.lstrip(os.sep)
            # Alternate implementation:
            # os.path.join(*source_path.split(os.sep)[1:]) # Strips up to first os.sep
        source_path = os.path.join(self.staging_path, source_path)
        if os.path.isdir(source_path):
            source_path += os.sep
        destination_path = os.path.join(self.path, destination_path)

        # TODO enforce destination_path is inside self.path
        try:
            self.get_child_space().move_from_storage_service(
                source_path, destination_path, *args, **kwargs)
        except AttributeError:
            raise NotImplementedError('{} space has not implemented move_from_storage_service'.format(self.get_access_protocol_display()))
        # Delete staging copy
        if source_path != destination_path:
            try:
                if os.path.isdir(source_path):
                    # Need to convert this to an str - if this is a
                    # unicode string, rmtree will use os.path.join
                    # on the directory and the names of its children,
                    # which can result in an attempt to join mixed encodings;
                    # this blows up if the filename cannot be converted to
                    # unicode.
                    shutil.rmtree(str(os.path.normpath(source_path)))
                elif os.path.isfile(source_path):
                    os.remove(os.path.normpath(source_path))
            except OSError:
                LOGGER.warning('Unable to remove %s', source_path, exc_info=True)

    def post_move_from_storage_service(self, staging_path=None, destination_path=None, package=None, *args, **kwargs):
        """ Hook for any actions that need to be taken after moving from the storage service to the final destination. """
        try:
            self.get_child_space().post_move_from_storage_service(
                staging_path=staging_path,
                destination_path=destination_path,
                package=package,
                *args, **kwargs)
        except AttributeError:
            # This is optional for the child class to implement
            pass

    def update_package_status(self, package):
        """
        Check and update the status of `package` stored in this Space.
        """
        try:
            return self.get_child_space().update_package_status(package)
        except AttributeError:
            message = '{} space has not implemented update_package_status'.format(self.get_access_protocol_display())
            return (None, message)


    # HELPER FUNCTIONS

    def _move_locally(self, source_path, destination_path, mode=None):
        """ Moves a file from source_path to destination_path on the local filesystem. """
        # FIXME this does not work properly when moving folders troubleshoot
        # and fix before using.
        # When copying from folder/. to folder2/. it failed because the folder
        # already existed.  Copying folder/ or folder to folder/ or folder also
        # has errors.  Should uses shutil.move()
        LOGGER.info("Moving from %s to %s", source_path, destination_path)

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
        LOGGER.info("Rsyncing from %s to %s", source, destination)

        if source == destination:
            return

        # Rsync file over
        # TODO Do this asyncronously, with restarting failed attempts
        command = ['rsync', '-vv', '--chmod=ugo+rw', '-r', source, destination]
        LOGGER.info("rsync command: %s", command)

        p = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        stdout, _ = p.communicate()
        if p.returncode != 0:
            s = "Rsync failed with status {}: {}".format(p.returncode, stdout)
            LOGGER.warning(s)
            raise StorageException(s)

    def _create_local_directory(self, path, mode=None):
        """ Creates a local directory at 'path' with 'mode' (default 775). """
        if mode is None:
            mode = (stat.S_IRUSR + stat.S_IWUSR + stat.S_IXUSR +
                    stat.S_IRGRP + stat.S_IWGRP + stat.S_IXGRP +
                    stat.S_IROTH +                stat.S_IXOTH)
        try:
            os.makedirs(os.path.dirname(path), mode)
        except os.error as e:
            # If the leaf node already exists, that's fine
            if e.errno != errno.EEXIST:
                LOGGER.warning("Could not create storage directory: %s", e)
                raise

        # os.makedirs may ignore the mode when creating directories, so force
        # the permissions here. Some spaces (eg CIFS) doesn't allow chmod, so
        # wrap it in a try-catch and ignore the failure.
        try:
            os.chmod(os.path.dirname(path), mode)
        except os.error as e:
            LOGGER.warning(e)

    def _browse_local(self, path):
        """
        Returns browse results for a locally accessible filesystem.
        """
        if isinstance(path, unicode):
            path = str(path)
        if not os.path.exists(path):
            LOGGER.info('%s in %s does not exist', path, self)
            return {'directories': [], 'entries': []}
        # Sorted list of all entries in directory, excluding hidden files
        entries = [name for name in os.listdir(path) if name[0] != '.']
        entries = sorted(entries, key=lambda s: s.lower())
        directories = []
        for name in entries:
            full_path = os.path.join(path, name)
            if os.path.isdir(full_path) and os.access(full_path, os.R_OK):
                directories.append(name)
        return {'directories': directories, 'entries': entries}

    def _delete_path_local(self, delete_path):
        """
        Deletes `delete_path` in this space, assuming it is locally accessible.
        """
        try:
            if os.path.isfile(delete_path):
                os.remove(delete_path)
            if os.path.isdir(delete_path):
                shutil.rmtree(delete_path)
        except (os.error, shutil.Error):
            LOGGER.warning("Error deleting package %s", delete_path, exc_info=True)
            raise
