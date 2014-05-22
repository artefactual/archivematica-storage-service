# stdlib, alphabetical
import ast
import datetime
import errno
import json
import logging
from lxml import etree
import math
import os
import shutil
import stat
import subprocess
import tempfile

# Core Django, alphabetical
from django.conf import settings
from django.core import validators
from django.core.exceptions import ValidationError
from django.core.urlresolvers import reverse
from django.db import models

# Third party dependencies, alphabetical
import bagit
import jsonfield
from django_extensions.db.fields import UUIDField
import sword2

# This project, alphabetical
from common import utils

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
    LOM = 'LOM'
    # FEDORA = 'FEDORA'
    ACCESS_PROTOCOL_CHOICES = (
        (LOCAL_FILESYSTEM, "Local Filesystem"),
        (NFS, "NFS"),
        (PIPELINE_LOCAL_FS, "Pipeline Local Filesystem"),
        (LOM, "LOCKSS-o-matic")
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

    mounted_locally = set([LOCAL_FILESYSTEM, NFS])
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
            pass  # TODO should this be required?
            # raise NotImplementedError('{} space has not implemented update_package_status'.format(self.get_access_protocol_display()))


    # HELPER FUNCTIONS

    def _move_locally(self, source_path, destination_path, mode=None):
        """ Moves a file from source_path to destination_path on the local filesystem. """
        # FIXME this does not work properly when moving folders troubleshoot
        # and fix before using.
        # When copying from folder/. to folder2/. it failed because the folder
        # already existed.  Copying folder/ or folder to folder/ or folder also
        # has errors.  Should uses shutil.move()
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
        except subprocess.CalledProcessError as e:
            logging.warning("Rsync failed: {}".format(e))
            raise

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
                logging.warning("Could not create storage directory: {}".format(e))
                raise

        # os.makedirs may ignore the mode when creating directories, so force
        # the permissions here. Some spaces (eg CIFS) doesn't allow chmod, so
        # wrap it in a try-catch and ignore the failure.
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

    def move_from_storage_service(self, source_path, destination_path):
        """ Moves self.staging_path/src_path to dest_path. """
        self.space._create_local_directory(destination_path)
        return self.space._move_rsync(source_path, destination_path)

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

    def move_from_storage_service(self, source_path, destination_path):
        """ Moves self.staging_path/src_path to dest_path. """
        # TODO optimization - check if the staging path and destination path are on the same device and use os.rename/self.space._move_locally if so
        self.space._create_local_directory(destination_path)
        return self.space._move_rsync(source_path, destination_path)

    def post_move_from_storage_service(self, staging_path, destination_path, package):
        # TODO Remove the staging file, since rsync leaves it behind
        pass

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
        #     command = 'mkdir -p "{dest_dir}" && mv "{src_path}" "{dest_path}"'.format(
        #         dest_dir=os.path.dirname(dest_path),
        #         src_user=self.remote_user, src_host=self.remote_name,
        #         src_path=src_path, dest_path=dest_path,
        #         )
        #     ssh_command = ["ssh", self.remote_user+"@"+self.remote_name, command]
        #     logging.info("ssh+mv command: {}".format(ssh_command))
        #     try:
        #         subprocess.check_call(ssh_command)
        #     except subprocess.CalledProcessError as e:
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

    def move_from_storage_service(self, source_path, destination_path):
        """ Moves self.staging_path/src_path to dest_path. """

        # Need to make sure destination exists
        command = 'mkdir -p {}'.format(os.path.dirname(destination_path))
        ssh_command = ["ssh", self.remote_user+"@"+self.remote_name, command]
        logging.info("ssh+mkdir command: {}".format(ssh_command))
        try:
            subprocess.check_call(ssh_command)
        except subprocess.CalledProcessError as e:
            logging.warning("ssh+mkdir failed: {}".format(e))
            raise

        # Prepend user and host to destination
        destination_path = "{user}@{host}:{path}".format(
            user=self.remote_user,
            host=self.remote_name,
            path=destination_path)

        # Move file
        return self.space._move_rsync(source_path, destination_path)

    def post_move_from_storage_service(self, staging_path, destination_path, package):
        # TODO Remove the staging file, since rsync leaves it behind
        pass


class Lockssomatic(models.Model):
    """ Spaces that store their contents in LOCKSS, via LOCKSS-o-matic. """
    space = models.OneToOneField('Space', to_field='uuid')

    # staging location is Space.path
    au_size = models.BigIntegerField(verbose_name="AU Size", null=True, blank=True,
        help_text="Size in bytes of an Allocation Unit")
    sd_iri = models.URLField(max_length=256, verbose_name="Service Document IRI",
        help_text="URL of LOCKSS-o-matic service document IRI, eg. http://lockssomatic.example.org/api/sword/2.0/sd-iri")
    collection_iri = models.CharField(max_length=256, null=True, blank=True, verbose_name="Collection IRI",
        help_text="URL to post the packages to, eg. http://lockssomatic.example.org/api/sword/2.0/col-iri/12")
    content_provider_id = models.CharField(max_length=32,
        verbose_name='Content Provider ID',
        help_text='On-Behalf-Of value when communicating with LOCKSS-o-matic')
    external_domain = models.URLField(verbose_name='Externally available domain',
        help_text='Base URL for this server that LOCKSS will be able to access.  Probably the URL for the home page of the Storage Service.')
    checksum_type = models.CharField(max_length=64, null=True, blank=True, verbose_name='Checksum type', help_text='Checksum type to send to LOCKSS-o-matic for verification.  Eg. md5, sha1, sha256')
    keep_local = models.BooleanField(blank=True, default=True, verbose_name="Keep local copy?",
        help_text="If checked, keep a local copy even after the AIP is stored in the LOCKSS network.")

    # Uses the SWORD protocol to talk to LOM
    sword_connection = None
    # Parsed pointer file
    pointer_root = None

    def move_to_storage_service(self, source_path, destination_path, dest_space):
        """ Moves source_path to dest_space.staging_path/destination_path. """
        # Check if in SS internal, if not then fetch from LOM
        raise NotImplementedError('LOCKSS-o-matic has not implemented retrieval.')

    def move_from_storage_service(self, source_path, destination_path):
        """ Moves self.staging_path/source_path to destination_path. """
        self.space._create_local_directory(destination_path)
        return self.space._move_rsync(source_path, destination_path)

    def post_move_from_storage_service(self, staging_path, destination_path, package):
        # LOCKSS can only save packages in the storage service, since it needs
        # to track information on it over time
        if package is None:
            return
        # Post to Lockss-o-matic with the create resource atom entry
        logging.info('Storing %s in LOCKSS', package.current_path)

        # Update Service Document, including maxUploadSize and Collection IRI
        # If SD cannot be updated, LOM probably down.  Terminate now, as
        # updating LOM can be repeated
        if not self.update_service_document():
            return
        # Split the files and record their locations.  If already split, just
        # returns list of output files
        output_files = self._split_package(package)

        # Create the atom entry XML
        entry, slug = self._create_resource(package, output_files)

        # Post to SWORD2 server
        receipt = self.sword_connection.create(col_iri=self.collection_iri, metadata_entry=entry, suggested_identifier=slug)
        try:
            state_iri = receipt.atom_statement_iri
            edit_iri = receipt.edit
        except AttributeError:
            # If something goes wrong with the parsing, receipt may not be a
            # sword.Deposit_Recipt (might be None, or sword.Error_Document) and
            # may not have the required attributes
            logging.warning('Unable to contact LOCKSS for package %s', package.uuid)
        else:
            logging.info("LOCKSS State IRI for %s: %s", package.uuid, state_iri)
            logging.info("LOCKSS Edit IRI for %s: %s", package.uuid, edit_iri)

            if state_iri and edit_iri:
                misc = {'state_iri': state_iri, 'edit_iri': edit_iri, 'num_files': len(output_files)}
                package.misc_attributes.update(misc)

        package.save()

    def update_package_status(self, package):
        """
        Poll LOM for SWORD statement and update status from response.

        Query the state_iri for this package and parse it for the server states.
        If all are in agreement, add those URLs to the pointer file for each
        LOCKSS chunk.
        """
        status = package.status

        # Need to have state and edit IRI to talk to LOM
        if 'state_iri' not in package.misc_attributes or 'edit_iri' not in package.misc_attributes:
            self.post_move_from_storage_service(None, None, package)

        # After retry - verify that state & edit IRI exist now
        if 'state_iri' not in package.misc_attributes or 'edit_iri' not in package.misc_attributes:
            return (None, 'Unable to contact Lockss-o-matic')

        if not self.sword_connection and not self.update_service_document():
            return (None, 'Error contacting LOCKSS-o-matic.')

        # SWORD2 client has only experimental support for getting SWORD2
        # statements, so implementing the fetch and parse here. (March 2014)
        response = self.sword_connection.get_resource(package.misc_attributes['state_iri'], headers = {'Accept':'application/atom+xml;type=feed'})

        if response.code != 200:
            return (None, 'Error polling LOCKSS-o-matic for SWORD statement.')

        statement_root = etree.fromstring(response.content)

        # TODO Check that number of lom:content entries is same as number of chunks
        # TODO what to do if was quorum, and now not??

        # Package not safely stored, return immediately
        servers = statement_root.findall('.//lom:server', namespaces=utils.NSMAP)
        logging.info('All states are agreement: %s', all(s.get('state') == 'agreement' for s in servers))
        if not all(s.get('state') == 'agreement' for s in servers):
            # TODO update pointer file for new failed status?
            return (status, 'LOCKSS servers not in agreement')

        status = Package.UPLOADED

        # Add LOCKSS URLs to each chunk
        if not self.pointer_root:
            self.pointer_root = etree.parse(package.full_pointer_file_path())
        files = self.pointer_root.findall(".//mets:fileSec/mets:fileGrp[@USE='LOCKSS chunk']/mets:file", namespaces=utils.NSMAP)
        # If not files, find AIP fileGrp (package unsplit)
        if not files:
            files = self.pointer_root.findall(".//mets:fileSec/mets:fileGrp[@USE='Archival Information Package']/mets:file", namespaces=utils.NSMAP)

        # Add new FLocat elements for each LOCKSS URL to each file element
        for index, file_e in enumerate(files):
            logging.debug('file element: %s', etree.tostring(file_e, pretty_print=True))
            if len(files) == 1:
                lom_id = self._download_url(package.uuid)
            else:
                lom_id = self._download_url(package.uuid, index+1)
            logging.debug('LOM id: %s', lom_id)
            lom_servers = statement_root.find(".//lom:content[@id='{}']/lom:serverlist".format(lom_id), namespaces=utils.NSMAP)
            logging.debug('lom_servers: %s', lom_servers)
            # Remove existing LOCKSS URLs, if they exist
            for old_url in file_e.findall("mets:FLocat[@LOCTYPE='URL']", namespaces=utils.NSMAP):
                file_e.remove(old_url)
            # Add URLs from SWORD statement
            for server in lom_servers:
                # TODO check that size and checksum are the same
                # TODO what to do if size & checksum different?
                logging.debug('LOM URL: %s', server.get('src'))
                flocat = etree.SubElement(file_e, 'FLocat', LOCTYPE="URL")
                flocat.set('{'+utils.NSMAP['xlink']+'}href', server.get('src'))

        # Delete local files
        # Note: This will tell LOCKSS to stop harvesting, even if the file was
        # not split, and will not be deleted locally
        lom_content = statement_root.findall('.//lom:content', namespaces=utils.NSMAP)
        delete_lom_ids = [e.get('id') for e in lom_content]
        error = self._delete_update_lom(package, delete_lom_ids)
        if error is None:
            self._delete_files()

        logging.info('update_package_status: new status: %s', status)

        # Write out pointer file again
        with open(package.full_pointer_file_path(), 'w') as f:
            f.write(etree.tostring(self.pointer_root, pretty_print=True))

        # Update value if different
        package.status = status
        package.save()
        return (status, error)

    def _delete_update_lom(self, package, delete_lom_ids):
        """
        Notifys LOM that AUs with `delete_lom_ids` will be deleted.

        Helper to update_package_status.
        """
        # Update LOM that local copies will be deleted
        entry = sword2.Entry(id='urn:uuid:{}'.format(package.uuid))
        entry.register_namespace('lom', utils.NSMAP['lom'])
        for lom_id in delete_lom_ids:
            if lom_id:
                etree.SubElement(entry.entry, '{'+utils.NSMAP['lom']+'}content', recrawl='false').text = lom_id
        logging.debug('edit entry: %s', entry)
        # SWORD2 client doesn't handle 202 respose correctly - implementing here
        # Correct function is self.sword_connection.update_metadata_for_resource
        headers = {
            'Content-Type': "application/atom+xml;type=entry",
            'Content-Length': str(len(str(entry))),
            'On-Behalf-Of': str(self.content_provider_id),
        }
        response, content = self.sword_connection.h.request(
            uri=package.misc_attributes['edit_iri'],
            method='PUT',
            headers=headers,
            payload=str(entry))

        # Return with error message if response not 200
        logging.debug('response code: %s', response['status'])
        if response['status'] != 200:
            if response['status'] == 202:  # Accepted - pushing new config
                return 'Lockss-o-matic is updating the config to stop harvesting.  Please try again to delete local files.'
            if response['status'] == 204:  # No Content - no matching AIP
                return 'Package {} is not found in LOCKSS'.format(package.uuid)
            if response['status'] == 409:  # Conflict - Files in AU with recrawl
                return "There are files in the LOCKSS Archival Unit (AU) that do not have 'recrawl=false'."
            return 'Error {} when requesting LOCKSS stop harvesting deleted files.'.format(response['status'])
        return None

    def _delete_files(self):
        """
        Delete AIP local files once stored in LOCKSS from disk and pointer file.

        Helper to update_package_status.
        """
        # Get paths to delete
        if self.keep_local:
            # Get all LOCKSS chucks local path FLocats
            delete_elements = self.pointer_root.xpath(".//mets:fileGrp[@USE='LOCKSS chunk']/*/mets:FLocat[@LOCTYPE='OTHER' and @OTHERLOCTYPE='SYSTEM']", namespaces=utils.NSMAP)
        else:
            # Get all local path FLocats
            delete_elements = self.pointer_root.xpath(".//mets:FLocat[@LOCTYPE='OTHER' and @OTHERLOCTYPE='SYSTEM']", namespaces=utils.NSMAP)
        logging.debug('delete_elements: %s', delete_elements)

        # Delete paths from delete_elements from disk, and remove from METS
        for element in delete_elements:
            path = element.get('{'+utils.NSMAP['xlink']+'}href')
            logging.debug('path to delete: %s', path)
            try:
                os.remove(path)
            except os.error as e:
                if e.errno != errno.ENOENT:
                    logging.exception('Could not delete {}'.format(path))
            element.getparent().remove(element)

        # Update pointer file
        # If delete_elements is false, then this function has probably already
        # been run, and we don't want to add another delete event
        if not self.keep_local and delete_elements:
            amdsec = self.pointer_root.find('mets:amdSec', namespaces=utils.NSMAP)
            # Add 'deletion' PREMIS:EVENT
            digiprov_id = 'digiprovMD_{}'.format(len(amdsec))
            digiprov_split = utils.mets_add_event(
                digiprov_id=digiprov_id,
                event_type='deletion',
                event_outcome_detail_note='AIP deleted from local storage',
            )
            logging.info('PREMIS:EVENT division: %s', etree.tostring(digiprov_split, pretty_print=True))
            amdsec.append(digiprov_split)

            # Add PREMIS:AGENT for storage service
            digiprov_id = 'digiprovMD_{}'.format(len(amdsec))
            digiprov_agent = utils.mets_ss_agent(amdsec, digiprov_id)
            if digiprov_agent is not None:
                logging.info('PREMIS:AGENT SS: %s', etree.tostring(digiprov_agent, pretty_print=True))
                amdsec.append(digiprov_agent)
            # If file was split
            if self.pointer_root.find(".//mets:fileGrp[@USE='LOCKSS chunk']", namespaces=utils.NSMAP) is not None:
                # Delete fileGrp USE="AIP"
                del_elem = self.pointer_root.find(".//mets:fileGrp[@USE='Archival Information Package']", namespaces=utils.NSMAP)
                del_elem.getparent().remove(del_elem)
                # Delete structMap div TYPE='Local copy'
                del_elem = self.pointer_root.find(".//mets:structMap/*/mets:div[@TYPE='Local copy']", namespaces=utils.NSMAP)
                del_elem.getparent().remove(del_elem)
        return None

    def update_service_document(self):
        """ Fetch the service document from self.sd_iri and updates based on that.

        Updates AU size and collection IRI.

        Returns True on success, False on error.  No updates performed on error."""
        try:
            self.sword_connection = sword2.Connection(self.sd_iri, download_service_document=True,
                on_behalf_of=self.content_provider_id)
        except Exception:  # TODO make this more specific
            logging.exception("Error getting service document from SWORD server.")
            return False
        # AU size
        self.au_size = self.sword_connection.maxUploadSize * 1000  # Convert from kB

        # Collection IRI
        # Workspaces are a list of ('workspace name', [collections]) tuples
        # Currently only support one workspace, so take the first one
        try:
            self.collection_iri = self.sword_connection.workspaces[0][1][0].href
        except IndexError:
            logging.warning("No collection IRI found in LOCKSS-o-matic service document.")
            return False

        # Checksum type - LOM specific tag
        root = self.sword_connection.sd.service_dom
        self.checksum_type = root.findtext('lom:uploadChecksumType', namespaces=utils.NSMAP)

        self.save()
        return True

    def _split_package(self, package):
        """
        Splits the package into chunks of size self.au_size. Returns list of paths to the chunks.

        If the package has already been split (and an event is in the pointer
        file), returns the list if file paths from the pointer file.

        Updates the pointer file with the new LOCKSS chunks, and adds 'division'
        event.
        """
        # Parse pointer file
        if not self.pointer_root:
            self.pointer_root = etree.parse(package.full_pointer_file_path())

        # Check if file is already split, and if so just return split files
        if self.pointer_root.xpath('.//premis:eventType[text()="division"]', namespaces=utils.NSMAP):
            chunks = self.pointer_root.findall(".//mets:div[@TYPE='Archival Information Package']/mets:div[@TYPE='LOCKSS chunk']", namespaces=utils.NSMAP)
            output_files = [c.find('mets:fptr', namespaces=utils.NSMAP).get('FILEID') for c in chunks]
            return output_files

        file_path = package.full_path()
        expected_num_files = math.ceil(os.path.getsize(file_path) / float(self.au_size))
        logging.debug('expected_num_files: %s', expected_num_files)

        # No split needed - just return the file path
        if expected_num_files <= 1:
            logging.debug('Only one file expected, not splitting')
            output_files = [file_path]
            # No events or structMap changes needed
            logging.info('LOCKSS: after splitting: {}'.format(output_files))
            return output_files

        # Split file
        # Strip extension, add .tar-1 ('-1' to make rename script happy)
        output_path = os.path.splitext(file_path)[0]+'.tar-1'
        command = ['tar', '--create', '--multi-volume',
            '--tape-length', str(self.au_size),
            '--new-volume-script', 'common/tar_new_volume.sh',
            '-f', output_path, file_path]
        # TODO reserve space in quota for extra files
        logging.info('LOCKSS split command: %s', command)
        try:
            subprocess.check_call(command)
        except Exception:
            logging.exception("Split of %s failed with command %s", file_path, command)
            raise
        output_path = output_path[:-2]  # Remove '-1'
        dirname, basename = os.path.split(output_path)
        output_files = sorted([os.path.join(dirname, entry) for entry in os.listdir(dirname) if entry.startswith(basename)])

        # Update pointer file
        amdsec = self.pointer_root.find('mets:amdSec', namespaces=utils.NSMAP)

        # Add 'division' PREMIS:EVENT
        try:
            event_detail = subprocess.check_output(['tar', '--version'])
        except subprocess.CalledProcessError as e:
            event_detail = e.output or 'Error: getting tool info; probably GNU tar'
        digiprov_id = 'digiprovMD_{}'.format(len(amdsec))
        digiprov_split = utils.mets_add_event(
            digiprov_id=digiprov_id,
            event_type='division',
            event_detail=event_detail,
            event_outcome_detail_note='{} LOCKSS chunks created'.format(len(output_files)),
        )
        logging.debug('PREMIS:EVENT division: %s', etree.tostring(digiprov_split, pretty_print=True))
        amdsec.append(digiprov_split)

        # Add PREMIS:AGENT for storage service
        digiprov_id = 'digiprovMD_{}'.format(len(amdsec))
        digiprov_agent = utils.mets_ss_agent(amdsec, digiprov_id)
        if digiprov_agent is not None:
            logging.debug('PREMIS:AGENT SS: %s', etree.tostring(digiprov_agent, pretty_print=True))
            amdsec.append(digiprov_agent)

        # Update structMap & fileSec
        self.pointer_root.find('mets:structMap', namespaces=utils.NSMAP).set('TYPE', 'logical')
        aip_div = self.pointer_root.find("mets:structMap/mets:div[@TYPE='Archival Information Package']", namespaces=utils.NSMAP)
        filesec = self.pointer_root.find('mets:fileSec', namespaces=utils.NSMAP)
        filegrp = etree.SubElement(filesec, 'fileGrp', USE='LOCKSS chunk')

        # Move ftpr to Local copy div
        local_ftpr = aip_div.find('mets:fptr', namespaces=utils.NSMAP)
        if local_ftpr is not None:
            div = etree.SubElement(aip_div, 'div', TYPE='Local copy')
            div.append(local_ftpr)  # This moves local_fptr

        # Add each split chunk to structMap & fileSec
        for idx, out_path in enumerate(output_files):
            # Add div to structMap
            div = etree.SubElement(aip_div, 'div', TYPE='LOCKSS chunk', ORDER=str(idx+1))
            etree.SubElement(div, 'fptr', FILEID=os.path.basename(out_path))
            # Get checksum and size for fileSec
            try:
                checksum = utils.generate_checksum(out_path, self.checksum_type)
            except ValueError:  # Invalid checksum type
                checksum = utils.generate_checksum(out_path, 'md5')
            checksum_name = checksum.name.upper().replace('SHA', 'SHA-')
            size = os.path.getsize(out_path)
            # Add file & FLocat to fileSec
            file_e = etree.SubElement(filegrp, 'file',
                ID=os.path.basename(out_path), SIZE=str(size),
                CHECKSUM=checksum.hexdigest(), CHECKSUMTYPE=checksum_name)
            flocat = etree.SubElement(file_e, 'FLocat', OTHERLOCTYPE="SYSTEM", LOCTYPE="OTHER")
            flocat.set('{'+utils.NSMAP['xlink']+'}href', out_path)

        # Write out pointer file again
        with open(package.full_pointer_file_path(), 'w') as f:
            f.write(etree.tostring(self.pointer_root, pretty_print=True))

        return output_files

    def _download_url(self, uuid, index=None):
        """
        Returns externally available download URL for a file.

        If index is None, returns URL for a file.  Otherwise, returns URL for a
        LOCKSS chunk with the given index.
        """
        if index is not None:  # Chunk of split file
            download_url = reverse('download_lockss', kwargs={'api_name': 'v1', 'resource_name': 'file', 'uuid': uuid, 'chunk_number': str(index)})
        else:  # Single file - not split
            download_url = reverse('download_request', kwargs={'api_name': 'v1', 'resource_name': 'file', 'uuid': uuid})
        # Prepend domain name
        download_url = self.external_domain+download_url
        return download_url

    def _create_resource(self, package, output_files):
        """ Given a package, create an Atom resource entry to send to LOCKSS.

        Parses metadata for the Atom entry from the METS file, uses
        LOCKSS-o-matic-specific tags to describe size and checksums.
        """

        # Parse METS to get information for atom entry
        relative_mets_path = os.path.join(
            os.path.splitext(os.path.basename(package.current_path))[0],
            "data",
            'METS.{}.xml'.format(package.uuid))
        (mets_path, temp_dir) = package.extract_file(relative_mets_path)
        mets = etree.parse(mets_path)
        # Delete temp dir if created
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

        # Parse out name and description if found
        slug = str(package.uuid)
        title = os.path.basename(package.current_path)
        summary = 'AIP generated by Archivematica with uuid {}'.format(package.uuid)
        dublincore = mets.find('mets:dmdSec/mets:mdWrap[@MDTYPE="DC"]/mets:xmlData/dcterms:dublincore', namespaces=utils.NSMAP)
        if dublincore is not None:
            title = dublincore.findtext('dcterms:title', namespaces=utils.NSMAP, default=title)
            slug = dublincore.findtext('dcterms:title', namespaces=utils.NSMAP, default=slug)
            summary = dublincore.findtext('dcterms:description', namespaces=utils.NSMAP, default=summary)
        # Parse out Agent for author
        authors = mets.xpath(".//mets:mdWrap[@MDTYPE='PREMIS:AGENT']//mets:agentType[text()='organization']/ancestor::mets:agent/*/mets:agentIdentifierValue", namespaces=utils.NSMAP)
        author = authors[0].text if authors else None

        # Create atom entry
        entry = sword2.Entry(
            title=title,
            id='urn:uuid:'+package.uuid,
            author={'name': author},
            summary=summary)

        # Add each chunk to the atom entry
        if not self.pointer_root:
            self.pointer_root = etree.parse(package.full_pointer_file_path())
        entry.register_namespace('lom', utils.NSMAP['lom'])
        for index, file_path in enumerate(output_files):
            # Get external URL
            if len(output_files) == 1:
                external_url = self._download_url(package.uuid)
            else:
                external_url = self._download_url(package.uuid, index+1)

            # Get checksum and size from pointer file (or generate if not found)
            file_e = self.pointer_root.find(".//mets:fileGrp[@USE='LOCKSS chunk']/mets:file[@ID='{}']".format(os.path.basename(file_path)), namespaces=utils.NSMAP)
            if file_e is not None:
                checksum_name = file_e.get('CHECKSUMTYPE')
                checksum_value = file_e.get('CHECKSUM')
                size = int(file_e.get('SIZE'))
            else:
                # Not split, generate
                try:
                    checksum = utils.generate_checksum(file_path,
                        self.checksum_type)
                except ValueError:  # Invalid checksum type
                    checksum = utils.generate_checksum(file_path, 'md5')
                checksum_name = checksum.name.upper().replace('SHA', 'SHA-')
                checksum_value = checksum.hexdigest()
                size = os.path.getsize(file_path)

            # Convert size to kB
            size = str(math.ceil(size/1000.0))

            # Add new content entry and values
            entry.add_field('lom_content', external_url)
            content_entry = entry.entry[-1]
            content_entry.set('size', size)
            content_entry.set('checksumType', checksum_name)
            content_entry.set('checksumValue', checksum_value)

        logging.debug('LOCKSS atom entry: {}'.format(entry))
        return entry, slug

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
#     def move_from_storage_service(self, source_path, destination_path):
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
    DIP_STORAGE = 'DS'
    # QUARANTINE = 'QU'
    BACKLOG = 'BL'
    CURRENTLY_PROCESSING = 'CP'
    STORAGE_SERVICE_INTERNAL = 'SS'

    PURPOSE_CHOICES = (
        (TRANSFER_SOURCE, 'Transfer Source'),
        (AIP_STORAGE, 'AIP Storage'),
        (DIP_STORAGE, 'DIP Storage'),
        # (QUARANTINE, 'Quarantine'),
        (BACKLOG, 'Transfer Backlog'),
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


class LocationPipeline(models.Model):
    location = models.ForeignKey('Location', to_field='uuid')
    pipeline = models.ForeignKey('Pipeline', to_field='uuid')

    class Meta:
        verbose_name = "Location associated with a Pipeline"

    def __unicode__(self):
        return u'{} is associated with {}'.format(self.location, self.pipeline)

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
    size = models.IntegerField(default=0, help_text='Size in bytes of the package')

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
    STAGING = 'STAGING'
    UPLOADED = 'UPLOADED'
    VERIFIED = 'VERIFIED'
    DEL_REQ = 'DEL_REQ'
    DELETED = 'DELETED'
    FAIL = 'FAIL'
    STATUS_CHOICES = (
        (PENDING, "Upload Pending"),  # Still on Archivematica
        (STAGING, "Staged on Storage Service"), # In Storage Service staging dir
        (UPLOADED, "Uploaded"),  # In final storage location
        (VERIFIED, "Verified"),  # Verified to be in final storage location
        (FAIL, "Failed"),  # Error occured - may or may not be at final location
        (DEL_REQ, "Delete requested"),
        (DELETED, "Deleted"),
    )
    status = models.CharField(max_length=8, choices=STATUS_CHOICES,
        default=FAIL,
        help_text="Status of the package in the storage service.")
    # NOTE Do not put anything important here because you cannot easily query
    # JSONFields! Add a new column if you need to query it
    misc_attributes = jsonfield.JSONField(blank=True, null=True, default={},
        help_text='For storing flexible, often Space-specific, attributes')

    PACKAGE_TYPE_CAN_DELETE = (AIP, AIC, TRANSFER)
    PACKAGE_TYPE_CAN_EXTRACT = (AIP, AIC)

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

    def is_compressed(self):
        """ Determines whether or not the package is a compressed file. """
        full_path = self.full_path()
        if os.path.isdir(full_path):
            return False
        elif os.path.isfile(full_path):
            return True
        else:
            if not os.path.exists(full_path):
                message = "Package {} (located at {}) does not exist".format(self.uuid, full_path)
            else:
                message = "{} is neither a file nor a directory".format(full_path)
            raise StorageException(message)

    def get_download_path(self, lockss_au_number=None):
        full_path = self.full_path()
        if lockss_au_number is None:
            path = full_path
        elif self.current_location.space.access_protocol == Space.LOM:
            # Only LOCKSS breaks files into AUs
            # TODO Get path from pointer file
            # self.pointer_root.find("mets:structMap/*/mets:div[@ORDER='{}']".format(lockss_au_number), namespaces=NSMAP)
            path = os.path.splitext(full_path)[0] + '.tar-' + str(lockss_au_number)
        else:  # LOCKSS AU number specified, but not a LOCKSS package
            logging.warning('Trying to download LOCKSS chunk for a non-LOCKSS package.')
            path = full_path
        return path

    def _check_quotas(self, dest_space, dest_location):
        """
        Verify that there is enough storage space on dest_space and dest_location for this package.  All sizes in bytes.
        """
        # Check if enough space on the space and location
        # All sizes expected to be in bytes
        if dest_space.size is not None and dest_space.used + self.size > dest_space.size:
            raise StorageException(
                "Not enough space for AIP on storage device {space}; Used: {used}; Size: {size}; AIP size: {aip_size}".format(
                space=dest_space, used=dest_space.used, size=dest_space.size,
                aip_size=self.size))
        if (dest_location.quota is not None and
                dest_location.used + self.size > dest_location.quota):
            raise StorageException(
                "AIP too big for quota on {location}; Used: {used}; Quota: {quota}; AIP size: {aip_size}".format(
                    location=dest_location,
                    used=dest_location.used,
                    quota=dest_location.quota,
                    aip_size=self.size)
            )

    def _update_quotas(self, space, location):
        """
        Add this package's size to the space and location.
        """
        space.used += self.size
        space.save()
        location.used += self.size
        location.save()

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
        src_space = self.origin_location.space
        dest_space = self.current_location.space
        self._check_quotas(dest_space, self.current_location)

        # Store AIP at
        # destination_location/uuid/split/into/chunks/destination_path
        uuid_path = utils.uuid_to_path(self.uuid)
        self.current_path = os.path.join(uuid_path, self.current_path)
        self.save()

        # Store AIP Pointer File at
        # internal_usage_location/uuid/split/into/chunks/pointer.xml
        if self.package_type in (Package.AIP, Package.AIC):
            self.pointer_file_location = Location.active.get(purpose=Location.STORAGE_SERVICE_INTERNAL)
            self.pointer_file_path = os.path.join(uuid_path, 'pointer.xml')
            pointer_file_src = os.path.join(self.origin_location.relative_path, os.path.dirname(self.origin_path), 'pointer.xml')
            pointer_file_dst = self.full_pointer_file_path()

        self.status = Package.PENDING
        self.save()

        # Move pointer file
        if self.package_type in (Package.AIP, Package.AIC):
            pointer_file_name = 'pointer-'+self.uuid+'.xml'
            try:
                src_space.move_to_storage_service(pointer_file_src, pointer_file_name, self.pointer_file_location.space)
                self.pointer_file_location.space.move_from_storage_service(pointer_file_name, pointer_file_dst)
            except:
                logging.warning("No pointer file found")
                self.pointer_file_location = None
                self.pointer_file_path = None
                self.save()

        # Move AIP
        src_space.move_to_storage_service(
            source_path=os.path.join(self.origin_location.relative_path, self.origin_path),
            destination_path=self.current_path,  # This should include Location.path
            destination_space=dest_space)
        src_space.post_move_to_storage_service()
        dest_space.move_from_storage_service(
            source_path=self.current_path,  # This should include Location.path
            destination_path=os.path.join(self.current_location.relative_path, self.current_path),
            )
        dest_space.post_move_from_storage_service(
            staging_path=self.current_path,
            destination_path=os.path.join(self.current_location.relative_path, self.current_path),
            package=self)

        # Save new space/location usage, package status
        self._update_quotas(dest_space, self.current_location)
        if dest_space.access_protocol == Space.LOM:
            self.status = Package.STAGING
        else:
            self.status = Package.UPLOADED
        self.save()

        # Update pointer file's location information
        if self.pointer_file_path and self.package_type in (Package.AIP, Package.AIC):
            root = etree.parse(pointer_file_dst)
            element = root.find('.//mets:file', namespaces=utils.NSMAP)
            flocat = element.find('mets:FLocat', namespaces=utils.NSMAP)
            if self.uuid in element.get('ID', '') and flocat is not None:
                flocat.set('{{{ns}}}href'.format(ns=utils.NSMAP['xlink']), self.full_path())
            # Add USE="Archival Information Package" to fileGrp.  Required for
            # LOCKSS, and not provided in Archivematica <=1.1
            if not root.find('.//mets:fileGrp[@USE="Archival Information Package"]', namespaces=utils.NSMAP):
                root.find('.//mets:fileGrp', namespaces=utils.NSMAP).set('USE', 'Archival Information Package')

            with open(pointer_file_dst, 'w') as f:
                f.write(etree.tostring(root, pretty_print=True))

    def extract_file(self, relative_path='', extract_path=None):
        """
        Attempts to extract this package.

        If `relative_path` is provided, will extract only that file.  Otherwise,
        will extract entire package.
        If `extract_path` is provided, will extract there, otherwise to a temp
        directory.

        Returns path to the extracted file and a temp dir that needs to be
        deleted.
        """
        if extract_path is None:
            extract_path = tempfile.mkdtemp()
        full_path = self.full_path()

        # The basename is the base directory containing a package
        # like an AIP inside the compressed file.
        if self.is_compressed():
            # Use lsar's JSON output to determine the directories in a
            # compressed file. Since the index of the base directory may
            # not be consistent, determine it by filtering all entries
            # for directories, then determine the directory with the
            # shortest name. (e.g. foo is the parent of foo/bar)
            # NOTE: lsar's JSON output is broken in certain circumstances in
            #       all released versions; make sure to use a patched version
            #       for this to work.
            command = ['lsar', '-ja', full_path]
            output = json.loads(subprocess.check_output(command))
            directories = [d['XADFileName'] for d in output['lsarContents'] if d.get('XADIsDirectory', False)]
            directories = sorted(directories, key=len)
            basename = directories[0]
        else:
            basename = os.path.basename(full_path)

        if relative_path:
            output_path = os.path.join(extract_path, relative_path)
        else:
            output_path = os.path.join(extract_path, basename)

        if self.is_compressed():
            command = ['unar', '-force-overwrite', '-o', extract_path, full_path]
            if relative_path:
                command.append(relative_path)

            logging.info('Extracting file with: {} to {}'.format(command, output_path))
            rc = subprocess.call(command)
            logging.debug('Extract file RC: %s', rc)
        else:
            aip_path = os.path.join(full_path, basename)
            logging.info('Copying AIP from: {} to {}'.format(aip_path, output_path))
            shutil.copytree(aip_path, output_path)

        return (output_path, extract_path)

    def compress_package(self, extract_path=None):
        """
        Produces a compressed copy of the package.

        If `extract_path` is provided, will compress there, otherwise to a temp
        directory.

        Returns path to the compressed file and its parent directory. Given that
        compressed packages are likely to be large, this should generally
        be deleted after use if a temporary directory was used.
        """

        if extract_path is None:
            extract_path = tempfile.mkdtemp()

        full_path = self.full_path()
        basename = os.path.splitext(os.path.basename(full_path))[0]
        relative_path = ''.join(full_path.rsplit(basename, 1))
        compressed_filename = os.path.join(extract_path, basename + '.tar')

        command = [
            "tar", "-cf", compressed_filename,
            "-C", relative_path, full_path
        ]
        logging.info('Compressing package with: {} to {}'.format(command, compressed_filename))
        rc = subprocess.call(command)
        logging.debug('Extract file RC: %s', rc)

        return (compressed_filename, extract_path)

    def backlog_transfer(self, origin_location, origin_path):
        """
        Stores a package in backlog.

        Invokes different transfer mechanisms depending on what the source and
        destination Spaces are.  Checks if there is space in the Space and
        Location for the AIP, and raises a StorageException if not.  All sizes
        expected to be in bytes.
        """
        self.origin_location = origin_location
        self.origin_path = origin_path

        # Check if enough space on the space and location
        # All sizes expected to be in bytes
        src_space = self.origin_location.space
        dest_space = self.current_location.space
        self._check_quotas(dest_space, self.current_location)

        # No pointer file
        self.pointer_file_location = None
        self.pointer_file_path = None

        self.status = Package.PENDING
        self.save()

        # Move transfer
        src_space.move_to_storage_service(
            source_path=os.path.join(self.origin_location.relative_path, self.origin_path),
            destination_path=self.current_path,  # This should include Location.path
            destination_space=dest_space)
        dest_space.move_from_storage_service(
            source_path=self.current_path,  # This should include Location.path
            destination_path=os.path.join(self.current_location.relative_path, self.current_path),
            )

        # Save new space/location usage, package status
        self._update_quotas(dest_space, self.current_location)
        self.status = Package.UPLOADED
        self.save()

    def check_fixity(self):
        """ Scans the package to verify its checksums.

        This is implemented using bagit-python module, using the checksums from the
        bag's manifest. Note that this does not support packages which are not bags.

        Returns a tuple containing (success, [errors], message).
        Success will be True or False if the verification succeeds or fails, and
        None if the scan could not start (for instance, if this package is not
        a bag).

        [errors] will be a list of zero or more classes representing different
        classes of errors.

        message will be a human-readable string explaining the report;
        it will be empty for successful scans.

        Note that if the package is not compressed, the fixity scan will occur
        in-place. If fixity scans will happen periodically, if packages are very
        large, or if scans are otherwise expected to contribute to heavy disk load,
        it is recommended to store packages uncompressed. """

        if not self.package_type in (self.AIC, self.AIP):
            return (None, [], "Unable to scan; package is not a bag (AIP or AIC)")

        if self.is_compressed():
            # bagit can't deal with compressed files, so extract before
            # starting the fixity check.
            path, temp_dir = self.extract_file()
        else:
            path = self.full_path()

        bag = bagit.Bag(path)
        try:
            success = bag.validate()
            failures = []
            message = ""
        except bagit.BagValidationError as failure:
            success = False
            failures = failure.details
            message = failure.message

        if self.is_compressed():
            shutil.rmtree(temp_dir)

        return (success, failures, message)

    def delete_from_storage(self):
        """ Deletes the package from filesystem and updates metadata.

        Returns (True, None) on success, and (False, error_msg) on failure. """
        # TODO move to protocol Spaces
        error = None
        if self.current_location.space.access_protocol in Space.mounted_locally:
            delete_path = self.full_path()
            try:
                if os.path.isfile(delete_path):
                    os.remove(delete_path)
                if os.path.isdir(delete_path):
                    shutil.rmtree(delete_path)
            except (os.error, shutil.Error) as e:
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
            command = 'rm -rf '+self.full_path()
            ssh_command = ["ssh", user+"@"+host, command]
            logging.info("ssh+rm command: %s", ssh_command)
            try:
                subprocess.check_call(ssh_command)
            except Exception as e:
                logging.exception("ssh+rm failed.")
                return False, "Error connecting to Location"
        elif self.current_location.space.access_protocol == Space.LOM:
            # Notify LOM that files will be deleted
            if 'num_files' in self.misc_attributes:
                lom = self.current_location.space.get_child_space()
                lom.update_service_document()
                delete_lom_ids = [lom._download_url(self.uuid, idx+1) for idx in range(self.misc_attributes['num_files'])]
                error = lom._delete_update_lom(self, delete_lom_ids)
            # Delete local copy
            try:
                shutil.rmtree(os.path.dirname(self.full_path()))
            except os.error as e:
                logging.exception("Error deleting local copy of LOCKSS package.")
                return False, e.strerror
            # Remove uuid quad directories if they're empty
            utils.removedirs(os.path.dirname(self.current_path),
                base=self.current_location.full_path())
        else:
            return (False, "Unknown access protocol for storing Space")

        # Remove pointer file, and the UUID quad directories if they're empty
        pointer_path = self.full_pointer_file_path()
        if pointer_path:
            try:
                os.remove(pointer_path)
            except os.error as e:
                logging.exception("Error deleting pointer file {} for package {}".format(pointer_path, self.uuid))
            utils.removedirs(os.path.dirname(self.pointer_file_path),
                base=self.pointer_file_location.full_path())

        self.status = self.DELETED
        self.save()
        return True, error

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
            {'default': 'default_dip_storage',
             'new': 'new_dip_storage',
             'purpose': Location.DIP_STORAGE},
            {'default': 'default_backlog',
             'new': 'new_backlog',
             'purpose': Location.BACKLOG},
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
