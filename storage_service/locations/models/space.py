# stdlib, alphabetical
import datetime
import errno
import logging
import os
import re
import shutil
import stat
import subprocess
import tempfile

# Core Django, alphabetical
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import ugettext_lazy as _

# Third party dependencies, alphabetical
import scandir
from django_extensions.db.fields import UUIDField

# This project, alphabetical
from common import utils

LOGGER = logging.getLogger(__name__)

# This module, alphabetical
from . import StorageException  # noqa: E402

__all__ = ("Space", "PosixMoveUnsupportedError")


def validate_space_path(path):
    """ Validation for path in Space.  Must be absolute. """
    if path[0] != "/":
        raise ValidationError(_("Path must begin with a /"))


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
#    'fields' is a allowlist of fields to display to the user
#  locations/migrations/####_<spacename>.py
#   Run `manage.py makemigrations locations` to create a migration.
#   Rename the migration after the feature. Eg. 0005_auto_20160331_1337.py -> 0005_dspace.py
#  locations/tests/test_<spacename>.py
#   Add class for tests. Example template below

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
#     def move_from_storage_service(self, source_path, destination_path, package=None):
#         """ Moves self.staging_path/src_path to dest_path. """
#         pass


# from django.test import TestCase
# import vcr
#
# from locations import models
#
# THIS_DIR = os.path.dirname(os.path.abspath(__file__))
# FIXTURES_DIR = os.path.abspath(os.path.join(THIS_DIR, '..', 'fixtures'))
#
# class TestExample(TestCase):
#
#     fixtures = ['base.json', 'example.json']
#
#     def setUp(self):
#         self.example_object = models.Example.objects.all()[0]
#
#     @vcr.use_cassette(os.path.join(FIXTURES_DIR, 'vcr_cassettes', 'example_browse.yaml'))
#     def test_browse(self):
#         pass
#
#     @vcr.use_cassette(os.path.join(FIXTURES_DIR, 'vcr_cassettes', 'example_delete.yaml'))
#     def test_delete(self):
#         pass
#
#     @vcr.use_cassette(os.path.join(FIXTURES_DIR, 'vcr_cassettes', 'example_move_from_ss.yaml'))
#     def test_move_from_ss(self):
#         pass
#
#     @vcr.use_cassette(os.path.join(FIXTURES_DIR, 'vcr_cassettes', 'example_move_to_ss.yaml'))
#     def test_move_to_ss(self):
#         pass


class Space(models.Model):
    """Common storage space information.

    Knows what protocol to use to access a storage space, but all protocol
    specific information is in children classes with ForeignKeys to Space."""

    uuid = UUIDField(
        editable=False, unique=True, version=4, help_text=_("Unique identifier")
    )

    # Max length 8 (see access_protocol definition)
    ARKIVUM = "ARKIVUM"
    DATAVERSE = "DV"
    DURACLOUD = "DC"
    DSPACE = "DSPACE"
    DSPACE_REST = "DSPC_RST"
    FEDORA = "FEDORA"
    LOCAL_FILESYSTEM = "FS"
    LOM = "LOM"
    NFS = "NFS"
    OFFLINE_REPLICA_STAGING = "REPLICA"
    PIPELINE_LOCAL_FS = "PIPE_FS"
    SWIFT = "SWIFT"
    GPG = "GPG"
    S3 = "S3"
    # These will not be displayed in the Space Create GUI (see locations/forms.py)
    BETA_PROTOCOLS = {}
    OBJECT_STORAGE = {DATAVERSE, DSPACE, DSPACE_REST, DURACLOUD, SWIFT, S3}
    ACCESS_PROTOCOL_CHOICES = (
        (ARKIVUM, _("Arkivum")),
        (DATAVERSE, _("Dataverse")),
        (DURACLOUD, _("DuraCloud")),
        (DSPACE, _("DSpace via SWORD2 API")),
        (DSPACE_REST, _("DSpace via REST API")),
        (FEDORA, _("FEDORA via SWORD2")),
        (GPG, _("GPG encryption on Local Filesystem")),
        (LOCAL_FILESYSTEM, _("Local Filesystem")),
        (LOM, _("LOCKSS-o-matic")),
        (NFS, _("NFS")),
        (OFFLINE_REPLICA_STAGING, _("Write-Only Replica Staging on Local Filesystem")),
        (PIPELINE_LOCAL_FS, _("Pipeline Local Filesystem")),
        (SWIFT, _("Swift")),
        (S3, _("S3")),
    )
    access_protocol = models.CharField(
        max_length=8,
        choices=ACCESS_PROTOCOL_CHOICES,
        verbose_name=_("Access protocol"),
        help_text=_("How the space can be accessed."),
    )
    size = models.BigIntegerField(
        default=None,
        null=True,
        blank=True,
        verbose_name=_("Size"),
        help_text=_("Size in bytes (optional)"),
    )
    used = models.BigIntegerField(
        default=0, verbose_name=_("Used"), help_text=_("Amount used in bytes")
    )
    path = models.TextField(
        default="",
        blank=True,
        verbose_name=_("Path"),
        help_text=_("Absolute path to the space on the storage service machine."),
    )
    staging_path = models.TextField(
        validators=[validate_space_path],
        verbose_name=_("Staging path"),
        help_text=_(
            "Absolute path to a staging area.  Must be UNIX filesystem compatible, preferably on the same filesystem as the path."
        ),
    )
    verified = models.BooleanField(
        default=False,
        verbose_name=_("Verified"),
        help_text=_("Whether or not the space has been verified to be accessible."),
    )
    last_verified = models.DateTimeField(
        default=None,
        null=True,
        blank=True,
        verbose_name=_("Last verified"),
        help_text=_("Time this location was last verified to be accessible."),
    )

    class Meta:
        verbose_name = _("Space")
        app_label = "locations"

    def __str__(self):
        return "{uuid}: {path} ({access_protocol}".format(
            uuid=self.uuid,
            access_protocol=self.get_access_protocol_display(),
            path=self.path,
        )

    def clean(self):
        # Object storage spaces do not require a path, or for it to start with /
        if self.access_protocol not in self.OBJECT_STORAGE:
            if not self.path:
                raise ValidationError(_("Path is required"))
            validate_space_path(self.path)

    def get_child_space(self):
        """ Returns the protocol-specific space object. """
        # Importing PROTOCOL here because importing locations.constants at the
        # top of the file causes a circular dependency
        from ..constants import PROTOCOL

        protocol_model = PROTOCOL[self.access_protocol]["model"]
        protocol_space = protocol_model.objects.get(space=self)
        # TODO try-catch AttributeError if remote_user or remote_name not exist?
        return protocol_space

    def browse(self, path, *args, **kwargs):
        """
        Return information about the objects (files, directories) at `path`.

        Attempts to call the child space's implementation.  If not found, falls
        back to looking for the path locally.

        Returns a dictionary with keys 'entries', 'directories' and 'properties'.

        'entries' is a list of strings, one for each entry in that directory, both file-like and folder-like.
        'directories' is a list of strings for each folder-like entry. Each entry should also be listed in 'entries'.
        'properties' is a dictionary that may contain additional information for the entries.  Keys are the entry name found in 'entries', values are a dictionary containing extra information. 'properties' may not contain all values from 'entries'.

        E.g.
        {
            'entries': ['BagTransfer.zip', 'Images', 'Multimedia', 'OCRImage'],
            'directories': ['Images', 'Multimedia', 'OCRImage'],
            'properties': {
                'Images': {'object count': 10},
                'Multimedia': {'object count': 7},
                'OCRImage': {'object count': 1}
            },
        }

        Values in the properties dict vary depending on the providing Space but may include:
        'size': Size of the object
        'object count': Number of objects in the directory, including children
        'timestamp': Last modified timestamp.
        'verbose name': Verbose name of the object
        See each Space's browse for details.

        :param str path: Full path to return info for
        :return: Dictionary of object information detailed above.
        """
        LOGGER.info("path: %s", path)
        try:
            return self.get_child_space().browse(path, *args, **kwargs)
        except AttributeError as e:
            LOGGER.debug("AttributeError while browsing %s: %r", path, e)
            LOGGER.debug("Falling back to default browse local", exc_info=False)
            return self.browse_local(path)

    def delete_path(self, delete_path, *args, **kwargs):
        """
        Deletes `delete_path` stored in this space.

        `delete_path` is a full path in this space.

        If not implemented in the child space, looks locally.
        """
        # Enforce delete_path is in self.path
        if not delete_path.startswith(self.path):
            raise ValueError(
                _("%(delete_path)s is not within %(path)s"),
                {"delete_path": delete_path, "path": self.path},
            )
        try:
            return self.get_child_space().delete_path(delete_path, *args, **kwargs)
        except AttributeError:
            return self._delete_path_local(delete_path)

    def posix_move(
        self, source_path, destination_path, destination_space, package=None
    ):
        """
        Move self.path/source_path direct to destination_space.path/destination_path bypassing staging.
        """
        if not hasattr(self.get_child_space(), "posix_move") or not hasattr(
            destination_space.get_child_space(), "posix_move"
        ):
            LOGGER.debug(
                "posix_move: not supported as %s and %s are not both POSIX filesystems",
                type(self.get_child_space()),
                type(destination_space.get_child_space()),
            )
            raise PosixMoveUnsupportedError()

        LOGGER.debug("posix_move: source_path: %s", source_path)
        LOGGER.debug("posix_move: destination_path: %s", destination_path)
        LOGGER.debug("posix_move: destination_space.path: %s", destination_space.path)

        source_path = os.path.join(self.path, source_path)

        if os.path.isabs(destination_path):
            destination_path = destination_path.lstrip(os.sep)

        abs_destination_path = os.path.join(destination_space.path, destination_path)

        return self.get_child_space().posix_move(
            source_path, abs_destination_path, destination_space, package
        )

    def move_to_storage_service(
        self, source_path, destination_path, destination_space, *args, **kwargs
    ):
        """Move source_path to destination_path in the staging area of destination_space.

        If source_path is not an absolute path, it is assumed to be relative to
        Space.path.

        destination_path must be relative and destination_space.staging_path
        MUST be locally accessible to the storage service.

        This is implemented by the child protocol spaces.
        """
        LOGGER.debug("TO: src: %s", source_path)
        LOGGER.debug("TO: dst: %s", destination_path)
        LOGGER.debug("TO: staging: %s", destination_space.staging_path)

        # TODO enforce source_path is inside self.path
        # Path pre-processing
        source_path = os.path.join(self.path, source_path)
        # dest_path must be relative
        if os.path.isabs(destination_path):
            destination_path = destination_path.lstrip(os.sep)
            # Alternative implementation
            # os.path.join(*destination_path.split(os.sep)[1:]) # Strips up to first os.sep
        destination_path = os.path.join(
            destination_space.staging_path, destination_path
        )

        try:
            self.get_child_space().move_to_storage_service(
                source_path, destination_path, destination_space, *args, **kwargs
            )
        except AttributeError:
            raise NotImplementedError(
                _("%(protocol)s space has not implemented %(method)s")
                % {
                    "protocol": self.get_access_protocol_display(),
                    "method": "move_to_storage_service",
                }
            )

    def post_move_to_storage_service(self, *args, **kwargs):
        """ Hook for any actions that need to be taken after moving to the storage service. """
        try:
            self.get_child_space().post_move_to_storage_service(*args, **kwargs)
        except AttributeError:
            # This is optional for the child class to implement
            pass

    def _move_from_path_mangling(self, staging_path, destination_path):
        """
        Does path pre-processing before passing to move_from_* functions.

        Given a staging_path relative to self.staging_path, converts to an absolute path.
        If staging_path is absolute (starts with /), force to be relative.
        If staging_path is a directory, ensure ends with /
        Given a destination_path relative to this space, converts to an absolute path.

        :param str staging_path: Path to the staging copy relative to the SS internal location.
        :param str destination_path: Path to the destination copy relative to this Space's path.
        :return: Tuple of absolute paths (staging_path, destination_path)
        """
        # Path pre-processing
        # source_path must be relative
        if os.path.isabs(staging_path):
            staging_path = staging_path.lstrip(os.sep)
            # Alternate implementation:
            # os.path.join(*staging_path.split(os.sep)[1:]) # Strips up to first os.sep
        staging_path = os.path.join(self.staging_path, staging_path)
        if os.path.isdir(staging_path):
            staging_path += os.sep
        destination_path = os.path.join(self.path, destination_path)

        # TODO enforce destination_path is inside self.path

        return staging_path, destination_path

    def move_from_storage_service(self, source_path, destination_path, *args, **kwargs):
        """Move source_path in this Space's staging area to destination_path in this Space.

        That is, moves self.staging_path/source_path to self.path/destination_path.

        If destination_path is not an absolute path, it is assumed to be
        relative to Space.path.

        source_path must be relative to self.staging_path.

        This is implemented by the child protocol spaces.
        """
        LOGGER.debug("FROM: src: %s", source_path)
        LOGGER.debug("FROM: dst: %s", destination_path)

        source_path, destination_path = self._move_from_path_mangling(
            source_path, destination_path
        )
        child_space = self.get_child_space()
        if hasattr(child_space, "move_from_storage_service"):
            return child_space.move_from_storage_service(
                source_path, destination_path, *args, **kwargs
            )
        else:
            raise NotImplementedError(
                _("%(protocol)s space has not implemented %(method)s")
                % {
                    "protocol": self.get_access_protocol_display(),
                    "method": "move_from_storage_service",
                }
            )

    def post_move_from_storage_service(
        self, staging_path, destination_path, package=None, *args, **kwargs
    ):
        """
        Hook for any actions that need to be taken after moving from the storage
        service to the final destination.

        :param str staging_path: Path to the staging copy relative to the SS internal location. Can be None if destination_path is also None.
        :param str destination_path: Path to the destination copy relative to this Space's path. Can be None if staging_path is also None.
        :param package: (Optional) :class:`Package` that is being moved.
        """
        if staging_path is None or destination_path is None:
            staging_path = destination_path = None
        if staging_path and destination_path:
            staging_path, destination_path = self._move_from_path_mangling(
                staging_path, destination_path
            )
        try:
            self.get_child_space().post_move_from_storage_service(
                staging_path=staging_path,
                destination_path=destination_path,
                package=package,
                *args,
                **kwargs,
            )
        except AttributeError:
            # This is optional for the child class to implement
            pass
        # Delete staging copy
        if staging_path != destination_path:
            try:
                if os.path.isdir(staging_path):
                    # Need to convert this to an str - if this is a
                    # unicode string, rmtree will use os.path.join
                    # on the directory and the names of its children,
                    # which can result in an attempt to join mixed encodings;
                    # this blows up if the filename cannot be converted to
                    # unicode
                    shutil.rmtree(utils.coerce_str(os.path.normpath(staging_path)))
                elif os.path.isfile(staging_path):
                    os.remove(os.path.normpath(staging_path))
            except OSError:
                logging.warning("Unable to remove %s", staging_path, exc_info=True)

    def update_package_status(self, package):
        """
        Check and update the status of `package` stored in this Space.
        """
        try:
            return self.get_child_space().update_package_status(package)
        except AttributeError:
            message = _("%(protocol)s space has not implemented %(method)s") % {
                "protocol": self.get_access_protocol_display(),
                "method": "update_package_status",
            }
            return (None, message)

    def check_package_fixity(self, package):
        """
        Check and return the fixity status of `package` stored in this space.

        :param package: Package to check
        """
        child = self.get_child_space()
        if hasattr(child, "check_package_fixity"):
            return child.check_package_fixity(package)
        else:
            raise NotImplementedError(
                _("Space %(protocol)s does not implement check_package_fixity")
                % {"protocol": self.get_access_protocol_display()}
            )

    def isfile(self, path):
        """Verify that something is a file in the context of a given space."""
        child = self.get_child_space()
        if hasattr(child, "isfile"):
            return child.isfile(path)
        else:
            raise NotImplementedError(
                _("Space %(protocol)s does not implement isfile")
                % {"protocol": self.get_access_protocol_display()}
            )

    # HELPER FUNCTIONS

    def move_rsync(
        self,
        source,
        destination,
        try_mv_local=False,
        assume_rsync_daemon=False,
        rsync_password=None,
    ):
        """Moves a file from source to destination.

        By default, uses rsync to move files.
        All directories leading to destination must exist; Space.create_local_directory may be useful.

        If try_mv_local is True, will attempt to use os.rename, which only works on the same device.
        This will not leave a copy at the source.

        :param source: Path to source file or directory. May have user@host: at beginning.
        :param destination: Path to destination file or directory. May have user@host: at the beginning.
        :param bool try_mv_local: If true, try moving/renaming instead of copying.  Should be False if source or destination specify a user@host.  Warning: this will not leave a copy at the source.
        :param bool assume_rsync_daemon: If true, will use rsync daemon-style commands instead of the default rsync with remote shell transport
        :param rsync_password: used if assume_rsync_daemon is true, to specify value of RSYNC_PASSWORD environment variable
        """
        source = utils.coerce_str(source)
        destination = utils.coerce_str(destination)
        LOGGER.info("Moving from %s to %s", source, destination)

        if source == destination:
            return

        if try_mv_local:
            # Try using mv, and if that fails, fallback to rsync
            chmod_command = ["chmod", "--recursive", "ug+rw,o+r", destination]
            try:
                os.rename(source, destination)
                # Set permissions (rsync does with --chmod=ugo+rw)
                subprocess.call(chmod_command)
                return
            except OSError:
                LOGGER.debug("os.rename failed, trying with normalized paths")
            source_norm = os.path.normpath(source)
            dest_norm = os.path.normpath(destination)
            try:
                os.rename(source_norm, dest_norm)
                # Set permissions (rsync does with --chmod=ugo+rw)
                subprocess.call(chmod_command)
                return
            except OSError:
                LOGGER.debug(
                    "os.rename failed, falling back to rsync. Source: %s; Destination: %s",
                    source_norm,
                    dest_norm,
                )

        # Rsync file over
        # TODO Do this asyncronously, with restarting failed attempts
        command = [
            "rsync",
            "-t",
            "-O",
            "--protect-args",
            "-vv",
            "--chmod=Fug+rw,o-rwx,Dug+rwx,o-rwx",
            "-r",
            source,
            destination,
        ]
        LOGGER.info("rsync command: %s", command)
        kwargs = {"stdout": subprocess.PIPE, "stderr": subprocess.STDOUT}
        if assume_rsync_daemon:
            kwargs["env"] = {"RSYNC_PASSWORD": rsync_password}
        p = subprocess.Popen(command, **kwargs)
        stdout, _ = p.communicate()
        if p.returncode != 0:
            s = f"Rsync failed with status {p.returncode}: {stdout}"
            LOGGER.warning(s)
            raise StorageException(s)

    def create_local_directory(self, path, mode=None):
        """
        Creates directory structure for `path` with `mode` (default 775).
        :param path: path to create the directories for.  Should end with a / or
            a filename, or final directory may not be created. If path is empty,
            no directories are created.
        :param mode: (optional) Permissions to create the directories with
            represented in octal (like bash or the stat module)
        """
        if mode is None:
            mode = (
                stat.S_IRUSR
                + stat.S_IWUSR
                + stat.S_IXUSR
                + stat.S_IRGRP
                + stat.S_IWGRP
                + stat.S_IXGRP
                + stat.S_IROTH
                + stat.S_IXOTH
            )
        dir_path = os.path.dirname(path)
        if not dir_path:
            return
        try:
            os.makedirs(dir_path, mode)
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

    def create_rsync_directory(self, destination_path, user, host):
        """
        Creates a remote directory structure for destination_path.

        :param path: path to create the directories for.  Should end with a / or
            a filename, or final directory may not be created. If path is empty,
            no directories are created.
        :param user: Username on remote host
        :param host: Hostname of remote host
        """
        # Assemble a set of directories to create on the remote server;
        # these will be created one at a time
        directories = []
        path = destination_path
        while path != "" and path != "/":
            directories.insert(0, path)
            path = os.path.dirname(path)

        # Syncing an empty directory will ensure no files get transferred
        temp_dir = os.path.join(tempfile.mkdtemp(), "")

        # Creates the destination_path directory without copying any files
        # Dir must end in a / for rsync to create it
        for directory in directories:
            path = os.path.join(os.path.dirname(directory), "")
            path = f"{user}@{host}:{utils.coerce_str(path)}"
            cmd = [
                "rsync",
                "-vv",
                "--protect-args",
                "--chmod=ug=rwx,o=rx",
                "--recursive",
                temp_dir,
                path,
            ]
            LOGGER.info("rsync path creation command: %s", cmd)
            try:
                subprocess.check_call(cmd)
            except subprocess.CalledProcessError as e:
                shutil.rmtree(temp_dir)
                LOGGER.warning("rsync path creation failed: %s", e)
                raise

        shutil.rmtree(temp_dir)

    def browse_local(self, path):
        """
        Returns browse results for a locally accessible filesystem.

        Properties provided:
        'size': Size of the object, as determined by os.path.getsize. May be misleading for directories, suggest use 'object count'
        'object count': Number of objects in the directory, including children
        """
        if isinstance(path, str):
            path = str(path)
        if not os.path.exists(path):
            LOGGER.info("%s in %s does not exist", path, self)
            return {"directories": [], "entries": [], "properties": {}}
        return path2browse_dict(path)

    def browse_rsync(
        self, path, ssh_key=None, assume_rsync_daemon=False, rsync_password=None
    ):
        """
        Returns browse results for a ssh (rsync) accessible space.

        See Space.browse for full documentation.

        Properties provided:
        'size': Size of the object
        'timestamp': Last modified timestamp of the object or directory

        :param path: Path to query, including user & hostname. E.g. user@host:/path/to/browse/  Must end in with / to browse directories.
        :param ssh_key: Path to the SSH key on disk. If None, will use default.
        :param bool assume_rsync_daemon: If true, will use rsync daemon-style commands instead of the default rsync with remote shell transport
        :param rsync_password: used if assume_rsync_daemon is true, to specify value of RSYNC_PASSWORD environment variable
        :return: See docstring for Space.browse
        """
        if ssh_key is None:
            ssh_key = "/var/lib/archivematica/.ssh/id_rsa"

        # Form command string used to get entries
        command = [
            "rsync",
            "--protect-args",
            "--list-only",
            "--exclude",
            ".*",  # Ignore hidden files
        ]
        if not assume_rsync_daemon:
            # Specify identity file
            command += ["--rsh", "ssh -i " + ssh_key]
        command += [path]

        LOGGER.info("rsync list command: %s", command)
        LOGGER.debug('"%s"', '" "'.join(command))  # For copying to shell
        try:
            env = os.environ.copy()
            if assume_rsync_daemon:
                env["RSYNC_PASSWORD"] = rsync_password
            output = subprocess.check_output(command, env=env)
        except Exception as error:
            LOGGER.warning("rsync list failed: %s", error, exc_info=True)
            entries = []
            directories = []
        else:
            output = output.decode("utf-8").splitlines()
            # Output is lines in format:
            # <type><permissions>  <size>  <date> <time> <path>
            # Eg: drwxrws---          4,096 2015/03/02 17:05:20 tmp
            # Eg: -rw-r--r--            201 2013/05/13 13:26:48 LICENSE.md
            # Eg: lrwxrwxrwx             78 2015/02/19 12:13:40 sharedDirectory
            # Parse out the path and type
            # Define groups for type, permissions, size, timestamp and name
            regex = r"^(?P<type>.)(?P<permissions>.{9}) +(?P<size>[\d,]+) (?P<timestamp>..../../.. ..:..:..) (?P<name>.*)$"
            matches = [re.match(regex, e) for e in output]
            # Take the last entry. Ignore empty lines and '.'
            entries = [e.group("name") for e in matches if e and e.group("name") != "."]
            # Only items whose type is not '-'. Links count as dirs.
            directories = [
                e.group("name")
                for e in matches
                if e and e.group("name") != "." and e.group("type") != "-"
            ]
            # Generate properties for each entry
            properties = {}
            for e in matches:
                name = e.group("name")
                if name not in entries:
                    continue
                properties[name] = {}
                properties[name]["timestamp"] = datetime.datetime.strptime(
                    e.group("timestamp"), "%Y/%m/%d %H:%M:%S"
                ).isoformat()
                if name not in directories:
                    properties[name]["size"] = int(e.group("size").replace(",", ""))

        directories = sorted(directories, key=lambda s: s.lower())
        entries = sorted(entries, key=lambda s: s.lower())
        LOGGER.debug("entries: %s", entries)
        LOGGER.debug("directories: %s", directories)
        return {"directories": directories, "entries": entries}

    @staticmethod
    def _del_package(delete_path):
        """Delete the package whether it is a file or directory at the
        leaf of the branch, i.e. the last directory or file at the end
        of the absolute given path.

        :param delete_path: absolute path to an Archivematica package
            (path-string)
        """
        try:
            if os.path.isfile(delete_path):
                os.remove(delete_path)
            if os.path.isdir(delete_path):
                shutil.rmtree(delete_path)
        except (os.error, shutil.Error):
            LOGGER.warning("Error deleting package %s", delete_path, exc_info=True)
            raise

    @staticmethod
    def _retrieve_dirs_to_delete(delete_path):
        """Given an absolute path to an Archivematica AIP (file or
        uncompressed directory), retrieve the base and relative
        directories that contain it.

        :param delete_path: absolute path to an Archivematica package
            (path-string)
        :return: quad_directory_structure (path-string), base_dir
            (path-string) (tuple)
        """
        UUID_MASK = os.path.join(
            "1111", "1111", "1111", "1111", "1111", "1111", "1111", "1111"
        )
        absolute_path_to_aip = os.path.split(delete_path)[0]
        base_dir = absolute_path_to_aip[: -len(UUID_MASK)]
        quad_dir_structure = absolute_path_to_aip.split(base_dir)[1]
        return quad_dir_structure, base_dir

    def _delete_quad_dir_structure(self, delete_path):
        """Given an absolute path to a package which is expected to have
        been deleted, split the object to then enable deletion of the
        quad-directory structure that the package used to sit within.

        :param delete_path: absolute path to an Archivematica package
            (path-string)
        """
        quad_dir, base_dir = self._retrieve_dirs_to_delete(delete_path)
        utils.removedirs(quad_dir, base=base_dir)

    def _delete_path_local(self, delete_path):
        """
        Deletes `delete_path` in this space, assuming it is locally accessible.
        """
        if not os.path.exists(delete_path):
            LOGGER.debug("Attempted to delete '%s' but path does not exist")
            return
        self._del_package(delete_path)
        self._delete_quad_dir_structure(delete_path)


# Thrown when posix_move is handed a non POSIX space
class PosixMoveUnsupportedError(Exception):
    pass


def _scandir_public(path):
    """Generate all directory entries, excluding hidden files."""
    for entry in scandir.scandir(path):
        if not entry.name.startswith("."):
            yield entry


def _scandir_files(path):
    """Generate all files, descending into subdirs."""
    try:
        for entry in scandir.scandir(path):
            if entry.is_dir():
                yield from _scandir_files(entry.path)
            else:
                yield entry
    except OSError:
        return


def path2browse_dict(path):
    """Given a path on disk, return a dict with keys for directories, entries
    and properties.
    """
    should_count = not utils.get_setting("object_counting_disabled", False)

    entries = []
    directories = []
    properties = {}

    for entry in sorted(_scandir_public(path), key=lambda e: e.name.lower()):
        entries.append(entry.name)
        if not entry.is_dir():
            properties[entry.name] = {"size": entry.stat().st_size}
        elif os.access(entry.path, os.R_OK):
            directories.append(entry.name)
            if should_count:
                properties[entry.name] = {
                    "object count": count_objects_in_directory(entry.path)
                }

    return {"directories": directories, "entries": entries, "properties": properties}


def count_objects_in_directory(path):
    """
    Returns all the files in a directory, including children.
    """
    count = 0
    for entry in _scandir_files(path):
        count += 1

        # Limit the number of files counted to keep it from being too slow
        if count >= 5000:
            return "5000+"

    return count
