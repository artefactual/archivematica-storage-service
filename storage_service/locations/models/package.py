# stdlib, alphabetical
import json
import logging
from lxml import etree
import os
import re
import shutil
import subprocess
import tempfile

# Core Django, alphabetical
from django.db import models

# Third party dependencies, alphabetical
import bagit
import jsonfield
from django_extensions.db.fields import UUIDField

# This project, alphabetical
from common import utils

# This module, alphabetical
from . import StorageException
from location import Location
from space import Space
from event import File

__all__ = ('Package', )

LOGGER = logging.getLogger(__name__)


class Package(models.Model):
    """ A package stored in a specific location. """
    uuid = UUIDField(editable=False, unique=True, version=4,
        help_text="Unique identifier")
    description = models.CharField(max_length=256, default=None,
        null=True, blank=True, help_text="Human-readable description.")
    origin_pipeline = models.ForeignKey('Pipeline', to_field='uuid', null=True, blank=True)
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
    DEPOSIT = 'deposit'
    PACKAGE_TYPE_CHOICES = (
        (AIP, 'AIP'),
        (AIC, 'AIC'),
        (SIP, 'SIP'),
        (DIP, 'DIP'),
        (TRANSFER, 'Transfer'),
        (FILE, 'Single File'),
        (DEPOSIT, 'FEDORA Deposit')
    )
    package_type = models.CharField(max_length=8, choices=PACKAGE_TYPE_CHOICES)

    PENDING = 'PENDING'
    STAGING = 'STAGING'
    UPLOADED = 'UPLOADED'
    VERIFIED = 'VERIFIED'
    DEL_REQ = 'DEL_REQ'
    DELETED = 'DELETED'
    RECOVER_REQ = 'RECOVER_REQ'
    MOVING = 'MOVING'
    MOVE_FAILED = 'MOVE_FAILED'
    FAIL = 'FAIL'
    FINALIZED = 'FINALIZE'
    STATUS_CHOICES = (
        (PENDING, "Upload Pending"),  # Still on Archivematica
        (STAGING, "Staged on Storage Service"),  # In Storage Service staging dir
        (UPLOADED, "Uploaded"),  # In final storage location
        (VERIFIED, "Verified"),  # Verified to be in final storage location
        (FAIL, "Failed"),  # Error occured - may or may not be at final location
        (DEL_REQ, "Delete requested"),
        (DELETED, "Deleted"),
        (FINALIZED, "Deposit Finalized")
    )
    status = models.CharField(max_length=8, choices=STATUS_CHOICES,
        default=FAIL,
        help_text="Status of the package in the storage service.")
    # NOTE Do not put anything important here because you cannot easily query
    # JSONFields! Add a new column if you need to query it
    misc_attributes = jsonfield.JSONField(blank=True, null=True, default={},
        help_text='For storing flexible, often Space-specific, attributes')

    # Temporary attributes to track path on locally accessible filesystem
    local_path = None
    local_path_location = None

    PACKAGE_TYPE_CAN_DELETE = (AIP, AIC, TRANSFER)
    PACKAGE_TYPE_CAN_EXTRACT = (AIP, AIC)
    PACKAGE_TYPE_CAN_RECOVER = (AIP)

    # Compression options
    COMPRESSION_7Z_BZIP = '7z with bzip'
    COMPRESSION_7Z_LZMA = '7z with lzma'
    COMPRESSION_TAR = 'tar'
    COMPRESSION_TAR_BZIP2 = 'tar bz2'
    COMPRESSION_ALGORITHMS = (
        COMPRESSION_7Z_BZIP,
        COMPRESSION_7Z_LZMA,
        COMPRESSION_TAR,
        COMPRESSION_TAR_BZIP2,
    )

    class Meta:
        verbose_name = "Package"
        app_label = 'locations'

    def __unicode__(self):
        return u"{uuid}: {path}".format(
            uuid=self.uuid,
            path=self.full_path,
        )
        # return "File: {}".format(self.uuid)

    # Attributes
    @property
    def full_path(self):
        """ Return the full path of the package's current location.

        Includes the space, location, and package paths joined. """
        return os.path.normpath(
            os.path.join(self.current_location.full_path, self.current_path))

    @property
    def full_pointer_file_path(self):
        """ Return the full path of the AIP's pointer file, None if not an AIP.

        Includes the space, location and package paths joined."""
        if not self.pointer_file_location:
            return None
        else:
            return os.path.join(self.pointer_file_location.full_path,
                self.pointer_file_path)

    @property
    def is_compressed(self):
        """ Determines whether or not the package is a compressed file. """
        full_path = self.fetch_local_path()
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
        full_path = self.fetch_local_path()
        if lockss_au_number is None:
            if not self.is_compressed:
                raise StorageException("Cannot return a download path for an uncompressed package")
            path = full_path
        elif self.current_location.space.access_protocol == Space.LOM:
            # Only LOCKSS breaks files into AUs
            # TODO Get path from pointer file
            # self.pointer_root.find("mets:structMap/*/mets:div[@ORDER='{}']".format(lockss_au_number), namespaces=NSMAP)
            path = os.path.splitext(full_path)[0] + '.tar-' + str(lockss_au_number)
        else:  # LOCKSS AU number specified, but not a LOCKSS package
            LOGGER.warning('Trying to download LOCKSS chunk for a non-LOCKSS package.')
            path = full_path
        return path

    def get_local_path(self):
        """
        Return a locally accessible path to this Package if available.

        If a cached copy of the local path is available (possibly from
        fetch_local_path), return that. If the package is available locally,
        return self.full_path. Otherwise, local_path is None.

        :returns: Local path to this package or None
        """
        # Return cached copy
        if self.local_path is not None and os.path.exists(self.local_path):
            return self.local_path
        # Package is locally accessible
        if os.path.exists(self.full_path):
            # TODO use Space protocol to determine if this is possible?
            self.local_path = self.full_path
            return self.local_path
        return None

    def fetch_local_path(self):
        """
        Fetches a local copy of the package.

        Returns local path if package is already available locally. Otherwise,
        copy to SS Internal Location, and return that path.

        :returns: Local path to this package.
        """
        local_path = self.get_local_path()
        if local_path:
            return local_path
        # Not locally accessible, so copy to SS internal temp dir
        ss_internal = Location.active.get(purpose=Location.STORAGE_SERVICE_INTERNAL)
        temp_dir = tempfile.mkdtemp(dir=ss_internal.full_path)
        int_path = os.path.join(temp_dir, self.current_path)
        self.current_location.space.move_to_storage_service(
            source_path=os.path.join(self.current_location.relative_path, self.current_path),
            destination_path=self.current_path,
            destination_space=ss_internal.space,
        )
        relative_path = int_path.replace(ss_internal.space.path, '', 1).lstrip('/')
        ss_internal.space.move_from_storage_service(
            source_path=self.current_path,
            destination_path=relative_path,
        )
        self.local_path_location = ss_internal
        self.local_path = int_path
        return self.local_path

    def get_base_directory(self):
        """
        Returns the base directory of a package. This is the directory in
        which all of the contents of the package are nested. For example,
        given the following bag:

        .
        |-- package-00000000-0000-0000-0000-000000000000
            |-- bagit.txt
            |-- manifest-sha512.txt
            ...

        The string "package-00000000-0000-0000-0000-000000000000" would be
        returned.

        Note that this currently only supports locally-available packages.
        If the package is stored externally, raises NotImplementedError.
        """
        full_path = self.get_local_path()
        if full_path is None:
            raise NotImplementedError("This method currently only retrieves base directories for locally-available AIPs.")

        if self.is_compressed:
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
            return directories[0]
        else:
            return os.path.basename(full_path)

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

    def move_to_location(self, destination_location_uuid):
        """
        Move a package to another location (that has the same purpose as package's current location).
        """
        destination_location = Location.active.get(uuid=destination_location_uuid)

        if self.current_location == destination_location:
            return

        if self.current_location.purpose != destination_location.purpose:
            raise ValueError('Location purpose mismatch for location %s' % destination_location_uuid)

        if self.status == Package.MOVING:
            raise StorageException("Can't move package {} as it's already being moved.".format(self.uuid))

        self.status = Package.MOVING
        self.save()

        try:
            # Move to internal storage
            ss_internal = Location.active.get(purpose=Location.STORAGE_SERVICE_INTERNAL)

            source_path = os.path.join(
                self.current_location.relative_path,
                self.current_path)

            origin_space = self.current_location.space
            origin_space.move_to_storage_service(
                source_path=source_path,
                destination_path='move',
                destination_space=ss_internal.space)
            origin_space.post_move_to_storage_service()

            # Move to destination location
            source_path = os.path.join(
                'move',
                os.path.basename(self.current_path))
            destination_path = os.path.join(
                destination_location.relative_path,
                self.current_path)

            destination_space = destination_location.space
            destination_space.move_from_storage_service(
                source_path=source_path,
                destination_path=destination_path)
            destination_space.post_move_from_storage_service(
                staging_path=source_path,
                destination_path=destination_path,
                package=self)

            # Update location
            self.current_location = destination_location
            self.status = Package.UPLOADED
            self.save()
            self.current_location.space.update_package_status(self)

            # Update pointer file's location information
            if self.pointer_file_path and self.package_type in (Package.AIP, Package.AIC):
                root = etree.parse(self.full_pointer_file_path)
                element = root.find('.//mets:file', namespaces=utils.NSMAP)
                flocat = element.find('mets:FLocat', namespaces=utils.NSMAP)
                if self.uuid in element.get('ID', '') and flocat is not None:
                    # TODO: use PREFIX_NS in later version
                    flocat.set('{{{ns}}}href'.format(ns=utils.NSMAP['xlink']), self.full_path)
                # Add USE="Archival Information Package" to fileGrp.  Required for
                # LOCKSS, and not provided in Archivematica <=1.1
                if root.find('.//mets:fileGrp[@USE="Archival Information Package"]', namespaces=utils.NSMAP) is None:
                    root.find('.//mets:fileGrp', namespaces=utils.NSMAP).set('USE', 'Archival Information Package')

                with open(self.full_pointer_file_path, 'w') as f:
                    f.write(etree.tostring(root, pretty_print=True))

        except Exception:
            LOGGER.info('Attempt to move package %s to location %s failed', self.uuid, destination_location_uuid, exc_info=True)
            self.status = Package.MOVE_FAILED
            self.save()

    def recover_aip(self, origin_location, origin_path):
        """ Recovers an AIP using files at a given location.

        Creates a temporary package associated with recovery AIP files within
        a space. Does fixity check on recovery AIP package. Makes backup of
        AIP files being replaced by recovery files. Replaces AIP files with
        recovery files.
        """

        # Create temporary AIP package
        temp_aip = Package()
        temp_aip.package_type = 'AIP'
        temp_aip.origin_pipeline = self.origin_pipeline
        temp_aip.current_location = origin_location
        temp_aip.current_path = origin_path
        temp_aip.save()

        # Check integrity of temporary AIP package
        (success, failures, message) = temp_aip.check_fixity()

        # If the recovered AIP doesn't pass check, delete and return error info
        if not success:
            temp_aip.delete()
            return (success, failures, message)

        origin_space = temp_aip.current_location.space
        destination_space = self.current_location.space

        # Copy corrupt files to storage service staging
        source_path = os.path.join(
            self.current_location.relative_path,
            self.current_path)
        destination_path = os.path.join(
            origin_location.relative_path,
            'backup')

        origin_space.move_to_storage_service(
            source_path=source_path,
            destination_path=destination_path,
            destination_space=destination_space)
        origin_space.post_move_to_storage_service()

        # Copy corrupt files from staging to backup directory
        destination_space.move_from_storage_service(
            source_path=destination_path,
            destination_path=destination_path)
        destination_space.post_move_from_storage_service()

        # Copy recovery files to storage service staging
        source_path = os.path.join(
            temp_aip.current_location.relative_path, origin_path)
        destination_path = os.path.join(
            self.current_location.relative_path,
            os.path.dirname(self.current_path))

        origin_space.move_to_storage_service(
            source_path=source_path,
            destination_path=destination_path,
            destination_space=destination_space)
        origin_space.post_move_to_storage_service()

        # Copy recovery files from staging to AIP store
        destination_space.move_from_storage_service(
            source_path=destination_path,
            destination_path=destination_path)
        destination_space.post_move_from_storage_service()

        temp_aip.delete()

        # Do fixity check of AIP with recovered files
        return self.check_fixity() 

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
        # internal_usage_location/uuid/split/into/chunks/pointer.uuid.xml
        if self.package_type in (Package.AIP, Package.AIC):
            self.pointer_file_location = Location.active.get(purpose=Location.STORAGE_SERVICE_INTERNAL)
            self.pointer_file_path = os.path.join(uuid_path, 'pointer.{}.xml'.format(self.uuid))
            pointer_file_src = os.path.join(self.origin_location.relative_path, os.path.dirname(self.origin_path), 'pointer.xml')
            pointer_file_dst = os.path.join(self.pointer_file_location.relative_path, self.pointer_file_path)

        self.status = Package.PENDING
        self.save()

        # Move pointer file
        if self.package_type in (Package.AIP, Package.AIC):
            try:
                src_space.move_to_storage_service(pointer_file_src, self.pointer_file_path, self.pointer_file_location.space)
                self.pointer_file_location.space.move_from_storage_service(self.pointer_file_path, pointer_file_dst)
            except:
                LOGGER.warning("No pointer file found")
                self.pointer_file_location = None
                self.pointer_file_path = None
                self.save()

        # Move AIP
        src_space.move_to_storage_service(
            source_path=os.path.join(self.origin_location.relative_path, self.origin_path),
            destination_path=self.current_path,  # This should include Location.path
            destination_space=dest_space)
        self.status = Package.STAGING
        self.save()
        src_space.post_move_to_storage_service()

        dest_space.move_from_storage_service(
            source_path=self.current_path,  # This should include Location.path
            destination_path=os.path.join(self.current_location.relative_path, self.current_path),
        )
        # Update package status once transferred to SS
        if dest_space.access_protocol not in (Space.LOM, Space.ARKIVUM):
            self.status = Package.UPLOADED
        self.save()
        dest_space.post_move_from_storage_service(
            staging_path=self.current_path,
            destination_path=os.path.join(self.current_location.relative_path, self.current_path),
            package=self)

        self._update_quotas(dest_space, self.current_location)

        # Update pointer file's location information
        if self.pointer_file_path and self.package_type in (Package.AIP, Package.AIC):
            pointer_absolute_path = self.full_pointer_file_path
            root = etree.parse(pointer_absolute_path)
            element = root.find('.//mets:file', namespaces=utils.NSMAP)
            flocat = element.find('mets:FLocat', namespaces=utils.NSMAP)
            if self.uuid in element.get('ID', '') and flocat is not None:
                flocat.set('{{{ns}}}href'.format(ns=utils.NSMAP['xlink']), self.full_path)
            # Add USE="Archival Information Package" to fileGrp.  Required for
            # LOCKSS, and not provided in Archivematica <=1.1
            if root.find('.//mets:fileGrp[@USE="Archival Information Package"]', namespaces=utils.NSMAP) is not None:
                root.find('.//mets:fileGrp', namespaces=utils.NSMAP).set('USE', 'Archival Information Package')

            with open(pointer_absolute_path, 'w') as f:
                f.write(etree.tostring(root, pretty_print=True))

    def extract_file(self, relative_path='', extract_path=None):
        """
        Attempts to extract this package.

        If `relative_path` is provided, will extract only that file.  Otherwise,
        will extract entire package.
        If `extract_path` is provided, will extract there, otherwise to a temp
        directory in the SS internal location.
        If extracting the whole package, will set local_path to the extracted path.
        Fetches the file from remote storage before extracting, if necessary.

        Returns path to the extracted file and a temp dir that needs to be
        deleted.
        """
        if extract_path is None:
            ss_internal = Location.active.get(purpose=Location.STORAGE_SERVICE_INTERNAL)
            extract_path = tempfile.mkdtemp(dir=ss_internal.full_path)
        full_path = self.fetch_local_path()

        # The basename is the base directory containing a package
        # like an AIP inside the compressed file.
        basename = self.get_base_directory()

        if relative_path:
            output_path = os.path.join(extract_path, relative_path)
        else:
            output_path = os.path.join(extract_path, basename)

        if self.is_compressed:
            command = ['unar', '-force-overwrite', '-o', extract_path, full_path]
            if relative_path:
                command.append(relative_path)

            LOGGER.info('Extracting file with: %s to %s', command, output_path)
            rc = subprocess.call(command)
            LOGGER.debug('Extract file RC: %s', rc)
        else:
            aip_path = os.path.join(full_path, basename)
            LOGGER.info('Copying AIP from: %s to %s', aip_path, output_path)
            shutil.copytree(aip_path, output_path)

        if not relative_path:
            self.local_path_location = ss_internal
            self.local_path = output_path

        return (output_path, extract_path)

    def compress_package(self, algorithm, extract_path=None):
        """
        Produces a compressed copy of the package.

        :param algorithm: Compression algorithm to use. Should be one of
            :const:`Package.COMPRESSION_ALGORITHMS`
        :param str extract_path: Path to compress to. If not provided, will
            compress to a temp directory in the SS internal location.
        :return: Tuple with (path to the compressed file, parent directory of
            compressed file)  Given that compressed packages are likely to
            be large, this should generally be deleted after use if a temporary
            directory was used.
        """

        if extract_path is None:
            ss_internal = Location.active.get(purpose=Location.STORAGE_SERVICE_INTERNAL)
            extract_path = tempfile.mkdtemp(dir=ss_internal.full_path)
        if algorithm not in self.COMPRESSION_ALGORITHMS:
            raise ValueError('Algorithm %s not in %s' % algorithm, self.COMPRESSION_ALGORITHMS)

        full_path = self.fetch_local_path()

        if os.path.isfile(full_path):
            basename = os.path.splitext(os.path.basename(full_path))[0]
        else:
            basename = os.path.basename(full_path)

        if algorithm in (self.COMPRESSION_TAR, self.COMPRESSION_TAR_BZIP2):
            compressed_filename = os.path.join(extract_path, basename + '.tar')
            relative_path = os.path.dirname(full_path)
            algo = ''
            if algorithm == self.COMPRESSION_TAR_BZIP2:
                algo = '-j'  # Compress with bzip2
                compressed_filename += '.bz2'
            command = [
                'tar', 'c',  # Create tar
                algo,  # Optional compression flag
                '-C', relative_path,  # Work in this directory
                '-f', compressed_filename,  # Output file
                os.path.basename(full_path),   # Relative path to source files
            ]
        elif algorithm in (self.COMPRESSION_7Z_BZIP, self.COMPRESSION_7Z_LZMA):
            compressed_filename = os.path.join(extract_path, basename + '.7z')
            if algorithm == self.COMPRESSION_7Z_BZIP:
                algo = 'bzip2'
            elif algorithm == self.COMPRESSION_7Z_LZMA:
                algo = 'lzma'
            command = [
                '7z', 'a',  # Add
                '-bd',  # Disable percentage indicator
                '-t7z',  # Type of archive
                '-y',  # Assume Yes on all queries
                '-m0=' + algo,  # Compression method
                '-mtc=on', '-mtm=on', '-mta=on',  # Keep timestamps (create, mod, access)
                '-mmt=on',  # Multithreaded
                compressed_filename,  # Destination
                full_path,  # Source
            ]
        else:
            raise NotImplementedError('Algorithm %s not implemented' % algorithm)

        LOGGER.info('Compressing package with: %s to %s', command, compressed_filename)
        rc = subprocess.call(command)
        LOGGER.debug('Extract file RC: %s', rc)

        return (compressed_filename, extract_path)

    def _parse_mets(self, prefix=None, relative_path=['metadata', 'submissionDocumentation', 'METS.xml']):
        """
        Parses a transfer's METS file, and returns a dict with metadata about
        the transfer and each file it contains.

        :param prefix: The location of the transfer containing the METS file
            to parse. If not provided, self.full_path is used.
        :param relative_path: An array containing one or more path components.
            These will be joined together with the prefix to produce the
            complete path of the METS within this transfer.
        :return: A dict in the following structure:
            {
                "transfer_uuid": "The UUID of the originating transfer",
                "creation_date": "The date the transfer METS was created, in ISO 8601 format",
                "dashboard_uuid": "The UUID of the originating dashboard",
                "files": [
                    # An array of zero or more dicts representing file
                    # metadata, in the following format:
                    {
                        "file_uuid": "The UUID of the file",
                        "path": "The full path of the file within the transfer,
                                 including the transfer's root directory."
                    }
                ]
            }
        :raises StorageException: if the requested METS file cannot be found,
            or if required elements are missing.
        """
        if prefix is None:
            prefix = self.full_path

        mets_path = os.path.join(prefix, *relative_path)
        if not os.path.isfile(mets_path):
            raise StorageException("No METS found at location: {}".format(mets_path))

        doc = etree.parse(mets_path)

        namespaces = {'m': utils.NSMAP['mets'],
                      'p': utils.NSMAP['premis']}
        mets = doc.xpath('/m:mets', namespaces=namespaces)
        if not mets:
            raise StorageException("<mets> element not found in METS file!")
        else:
            mets = mets[0]

        try:
            transfer_uuid = mets.attrib['OBJID']
        except KeyError:
            raise StorageException("<mets> element did not have an OBJID attribute!")

        header = doc.find('m:metsHdr', namespaces=namespaces)
        if header is None:
            raise StorageException("<metsHdr> element not found in METS file!")

        try:
            creation_date = header.attrib['CREATEDATE']
        except KeyError:
            raise StorageException("<metsHdr> element did not have a CREATEDATE attribute!")

        accession_id = header.findtext('./m:altRecordID[@TYPE="Accession number"]', namespaces=namespaces) or ''

        agent = header.xpath('./m:agent[@ROLE="CREATOR"][@TYPE="OTHER"][@OTHERTYPE="SOFTWARE"]/m:note[.="Archivematica dashboard UUID"]/../m:name',
                             namespaces=namespaces)
        if not agent:
            raise StorageException("No <agent> element found!")
        dashboard_uuid = agent[0].text

        files = mets.xpath('.//m:FLocat', namespaces=namespaces)
        package_basename = os.path.basename(self.current_path)

        files_data = []
        for f in files:
            file_id = f.getparent().attrib['ID']

            # Only include files listed in the "processed" structMap;
            # some files may not be present in this transfer.
            if mets.find('./m:structMap[@LABEL="processed"]//m:fptr[@FILEID="{}"]'.format(file_id), namespaces=namespaces) is None:
                continue

            relative_path = f.attrib['{' + utils.NSMAP['xlink'] + '}href']
            uuid = file_id[-36:]

            # If the filename has been sanitized, the path in the fileSec
            # may be outdated; check for a cleanup event and use that,
            # if present.
            cleanup_events = mets.xpath('m:amdSec[@ID="digiprov-{}"]/m:digiprovMD/m:mdWrap/m:xmlData/p:event/p:eventType[text()="name cleanup"]/../p:eventOutcomeInformation/p:eventOutcomeDetail/p:eventOutcomeDetailNote/text()'.format(uuid), namespaces=namespaces)
            if cleanup_events:
                cleaned_up_name = re.match(r'.*cleaned up name="(.*)"$', cleanup_events[0])
                if cleaned_up_name:
                    relative_path = cleaned_up_name.groups()[0].replace('%transferDirectory%', '', 1)

            file_data = {
                "path": os.path.join(package_basename, relative_path),
                "file_uuid": uuid
            }

            files_data.append(file_data)

        return {
            "transfer_uuid": transfer_uuid,
            "creation_date": creation_date,
            "dashboard_uuid": dashboard_uuid,
            "accession_id": accession_id,
            "files": files_data
        }

    def index_file_data_from_transfer_mets(self, prefix=None):
        """
        Attempts to read an Archivematica transfer METS file inside this
        package, then uses the retrieved metadata to generate one entry in the
        File table in the database for each file inside the package.

        :param prefix: The location of the transfer containing the METS file
            to parse. If not provided, self.full_path is used.
        :raises StorageException: if the transfer METS cannot be found,
            or if required elements are missing.
        """
        if prefix is None:
            prefix = self.full_path

        file_data = self._parse_mets(prefix=prefix)

        for f in file_data['files']:
            File.objects.create(source_id=f['file_uuid'],
                                source_package=file_data['transfer_uuid'],
                                accessionid=file_data['accession_id'],
                                package=self,
                                name=f['path'],
                                origin=file_data['dashboard_uuid'])


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

        try:
            self.index_file_data_from_transfer_mets(prefix=os.path.join(dest_space.staging_path, self.current_path))  # create File entries for every file in the transfer
        except StorageException as e:
            LOGGER.warning("Transfer METS data could not be read: %s", str(e))

        dest_space.move_from_storage_service(
            source_path=self.current_path,  # This should include Location.path
            destination_path=os.path.join(self.current_location.relative_path, self.current_path),
        )

        # Save new space/location usage, package status
        self._update_quotas(dest_space, self.current_location)
        self.status = Package.UPLOADED
        self.save()

    def check_fixity(self, delete_after=True):
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

        if self.package_type not in (self.AIC, self.AIP):
            return (None, [], "Unable to scan; package is not a bag (AIP or AIC)")

        if self.is_compressed:
            # bagit can't deal with compressed files, so extract before
            # starting the fixity check.
            path, temp_dir = self.extract_file()
        else:
            path = self.fetch_local_path()
            temp_dir = None

        bag = bagit.Bag(path)
        try:
            success = bag.validate()
            failures = []
            message = ""
        except bagit.BagValidationError as failure:
            success = False
            failures = failure.details
            message = failure.message

        if temp_dir and delete_after and (self.local_path_location != self.current_location or self.local_path != self.full_path):
            shutil.rmtree(temp_dir)

        return (success, failures, message)

    def delete_from_storage(self):
        """ Deletes the package from filesystem and updates metadata.

        Returns (True, None) on success, and (False, error_msg) on failure. """
        error = None
        # LOCKSS must notify LOM before deleting
        if self.current_location.space.access_protocol == Space.LOM:
            # Notify LOM that files will be deleted
            if 'num_files' in self.misc_attributes:
                lom = self.current_location.space.get_child_space()
                lom.update_service_document()
                delete_lom_ids = [lom._download_url(self.uuid, idx + 1) for idx in range(self.misc_attributes['num_files'])]
                error = lom._delete_update_lom(self, delete_lom_ids)

        try:
            self.current_location.space.delete_path(self.full_path)
        except Exception as e:
            error = e.message

        # Remove pointer file, and the UUID quad directories if they're empty
        pointer_path = self.full_pointer_file_path
        if pointer_path:
            try:
                os.remove(pointer_path)
            except OSError as e:
                LOGGER.info("Error deleting pointer file %s for package %s", pointer_path, self.uuid, exc_info=True)
            utils.removedirs(os.path.dirname(self.pointer_file_path),
                base=self.pointer_file_location.full_path)

        self.status = self.DELETED
        self.save()
        return True, error

    # SWORD-related methods
    def has_been_submitted_for_processing(self):
        return 'deposit_completion_time' in self.misc_attributes
