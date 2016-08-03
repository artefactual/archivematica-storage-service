from __future__ import absolute_import
# stdlib, alphabetical
import datetime
import distutils.dir_util
import json
import logging
from lxml import etree
import os
import re
import requests
import shutil
import subprocess
import tempfile

# Core Django, alphabetical
from django.db import models
from django.utils import timezone

# Third party dependencies, alphabetical
import bagit
import jsonfield
from django_extensions.db.fields import UUIDField

# This project, alphabetical
from common import utils

# This module, alphabetical
from . import StorageException
from .location import Location
from .space import Space
from .event import File
from .fixity_log import FixityLog

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
    related_packages = models.ManyToManyField('self', related_name='related')

    PENDING = 'PENDING'
    STAGING = 'STAGING'
    UPLOADED = 'UPLOADED'
    VERIFIED = 'VERIFIED'
    DEL_REQ = 'DEL_REQ'
    DELETED = 'DELETED'
    RECOVER_REQ = 'RECOVER_REQ'
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
    PACKAGE_TYPE_CAN_RECOVER = (AIP, AIC)
    PACKAGE_TYPE_CAN_REINGEST = (AIP, AIC)

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

    # Reingest type options
    METADATA_ONLY = 'metadata'
    OBJECTS = 'objects'
    REINGEST_CHOICES = (METADATA_ONLY, OBJECTS)

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

    @property
    def latest_fixity_check_datetime(self):
        latest_check = self._latest_fixity_check()
        return latest_check.datetime_reported if latest_check is not None else None

    @property
    def latest_fixity_check_result(self):
        latest_check = self._latest_fixity_check()
        return latest_check.success if latest_check is not None else None

    def _latest_fixity_check(self):
        try:
            return FixityLog.objects.filter(package=self).order_by('-datetime_reported')[0]  # limit 1
        except IndexError:
            return None

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
        (success, failures, message, _) = temp_aip.check_fixity(force_local=True)

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
        destination_space.post_move_from_storage_service(
            staging_path=None,
            destination_path=None)

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
        destination_space.post_move_from_storage_service(
            staging_path=None,
            destination_path=None)

        temp_aip.delete()

        # Do fixity check of AIP with recovered files
        success, failures, message, _ = self.check_fixity(force_local=True)
        return success, failures, message

    def store_aip(self, origin_location, origin_path, related_package_uuid=None):
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
        if related_package_uuid is not None:
            related_package = Package.objects.get(uuid=related_package_uuid)
            self.related_packages.add(related_package)
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
        try:
            basename = self.get_base_directory()
        except subprocess.CalledProcessError:
            raise StorageException('Error determining basename during extraction')

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
            if rc:
                raise StorageException('Extraction error')
        else:
            LOGGER.info('Copying AIP from: %s to %s', full_path, output_path)
            shutil.copytree(full_path, output_path)

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
            cleanup_events = mets.xpath('m:amdSec[@ID="digiprov-{}"]/m:digiprovMD/m:mdWrap/m:xmlData/p:event/p:eventType[text()="name cleanup"]/../p:eventOutcomeInformation/p:eventOutcomeDetail/p:eventOutcomeDetailNote/text()'.format(uuid), namespaces=namespaces, smart_strings=False)
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

    def check_fixity(self, force_local=False, delete_after=True):
        """ Scans the package to verify its checksums.

        This will check if the Space can run a fixity and use that. If not, it will run fixity locally.
        This is implemented using bagit-python module, using the checksums from the
        bag's manifest. Note that this does not support packages which are not bags.

        Returns a tuple containing (success, [errors], message, timestamp)
        Success will be True or False if the verification succeeds or fails, and
        None if the scan could not start (for instance, if this package is not
        a bag).

        [errors] will be a list of zero or more classes representing different
        classes of errors.

        message will be a human-readable string explaining the report;
        it will be empty for successful scans.

        timestamp will be an ISO-formated string with the datetime of the last
        fixity check or None. If the check was performed by an external system,
        this will be provided by that system. If not or on error, it will be None.

        Note that if the package is not compressed, the fixity scan will occur
        in-place. If fixity scans will happen periodically, if packages are very
        large, or if scans are otherwise expected to contribute to heavy disk load,
        it is recommended to store packages uncompressed.

        :param bool force_local: If True, will always fetch and run fixity locally. If not, it will use a Space's fixity check if available.
        :param bool delete_after: If True and the package was copied to a local path, will delete the temporary copy once fixity is run.
        """

        if self.package_type not in (self.AIC, self.AIP):
            return (None, [], "Unable to scan; package is not a bag (AIP or AIC)", None)

        if not force_local:
            try:
                success, failures, message, timestamp = self.current_location.space.check_package_fixity(self)
            except NotImplementedError:
                pass
            else:
                return (success, failures, message, timestamp)

        if self.is_compressed:
            # bagit can't deal with compressed files, so extract before
            # starting the fixity check.
            try:
                 path, temp_dir = self.extract_file()
            except StorageException:
                 return (None, [], 'Error extracting file')
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

        return (success, failures, message, None)

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

    # REINGEST

    def start_reingest(self, pipeline, reingest_type):
        """
        Copies this package to `pipeline` for reingest.

        Fetches the AIP from storage, extracts and runs fixity on it to verify integrity.
        If reingest_type is METADATA_ONLY, sends the METS and all files in the metadata directory.
        If reingest_type is OBJECTS, sends METS, all files in metadata directory and all objects, preservation and original.
        Calls Archivematica endpoint /api/ingest/reingest/ to start reingest.

        :param pipeline: Pipeline object to send reingested AIP to.
        :param reingest_type: Type of reingest to start, one of REINGEST_CHOICES.
        :return: Dict with keys 'error', 'status_code' and 'message'
        """
        if self.package_type not in Package.PACKAGE_TYPE_CAN_REINGEST:
            return {'error': True, 'status_code': 405,
                'message': 'Package with type {} cannot be re-ingested.'.format(self.get_package_type_display())}

        # Check and set reingest pipeline
        if self.misc_attributes.get('reingest_pipeline', None):
            return {'error': True, 'status_code': 409,
                'message': 'This AIP already being reingested on {}'.format(self.misc_attributes['reingest_pipeline'])}
        self.misc_attributes.update({'reingest_pipeline': pipeline.uuid})

        # Fetch and extract if needed
        if self.is_compressed:
            local_path, temp_dir = self.extract_file()
            LOGGER.debug('Reingest: extracted to %s', local_path)
        else:
            local_path = self.fetch_local_path()
            temp_dir = ''
            LOGGER.debug('Reingest: uncompressed at %s', local_path)

        # Run fixity
        # Fixity will fetch & extract package if needed
        success, _, error_msg, _ = self.check_fixity(delete_after=False)
        LOGGER.debug('Reingest: Fixity response: %s, %s', success, error_msg)
        if not success:
            return {'error': True, 'status_code': 500, 'message': error_msg}

        # Make list of folders to move
        current_location = self.local_path_location or self.current_location
        relative_path = local_path.replace(current_location.full_path, '', 1).lstrip('/')
        reingest_files = [
            os.path.join(relative_path, 'data', 'METS.' + self.uuid + '.xml')
        ]
        if reingest_type == self.OBJECTS:
            # All in objects except submissionDocumentation dir
            for f in os.listdir(os.path.join(local_path, 'data', 'objects')):
                if f in ('submissionDocumentation'):
                    continue
                abs_path = os.path.join(local_path, 'data', 'objects', f)
                if os.path.isfile(abs_path):
                    reingest_files.append(os.path.join(relative_path, 'data', 'objects', f))
                elif os.path.isdir(abs_path):
                    # Dirs must be / terminated to make the move functions happy
                    reingest_files.append(os.path.join(relative_path, 'data', 'objects', f, ''))
        elif reingest_type == self.METADATA_ONLY:
            reingest_files.append(os.path.join(relative_path, 'data', 'objects', 'metadata', ''))

        LOGGER.info('Reingest: files: %s', reingest_files)

        # Copy to pipeline
        try:
            currently_processing = Location.active.filter(pipeline=pipeline).get(purpose=Location.CURRENTLY_PROCESSING)
        except (Location.DoesNotExist, Location.MultipleObjectsReturned):
            return {'error': True, 'status_code': 412,
                'message': 'No currently processing Location is associated with pipeline {}'.format(pipeline.uuid)}
        LOGGER.debug('Reingest: Current location: %s', current_location)
        dest_basepath = os.path.join(currently_processing.relative_path, 'tmp', '')
        for path in reingest_files:
            current_location.space.move_to_storage_service(
                source_path=os.path.join(current_location.relative_path, path),
                destination_path=path,
                destination_space=currently_processing.space,
            )
            currently_processing.space.move_from_storage_service(
                source_path=path,
                destination_path=os.path.join(dest_basepath, path),
            )

        # Delete local copy of extraction
        if self.local_path != self.full_path:
            shutil.rmtree(local_path)
        if temp_dir:
            shutil.rmtree(temp_dir)

        # Call reingest AIP API
        reingest_url = 'http://' + pipeline.remote_name + '/api/ingest/reingest'
        params = {
            'username': pipeline.api_username,
            'api_key': pipeline.api_key,
            'name': relative_path,
            'uuid': self.uuid,
        }
        LOGGER.debug('Reingest: URL: %s; params: %s', reingest_url, params)
        try:
            response = requests.post(reingest_url, data=params, allow_redirects=True)
        except requests.exceptions.RequestException:
            LOGGER.exception('Unable to connect to pipeline %s', pipeline)
            return {'error': True, 'status_code': 502,
                'message': 'Unable to connect to pipeline'}
        LOGGER.debug('Response: %s %s', response.status_code, response.text)
        if response.status_code != requests.codes.ok:
            try:
                json_error = response.json().get('message',
                    'Error in approve reingest API.')
            except ValueError:  # Failed to decode JSON
                json_error = 'Error in approve reingest API.'
            LOGGER.error(json_error)
            return {'error': True, 'status_code': 502,
                'message': 'Error from pipeline: %s' % json_error}

        self.save()

        return {'error': False, 'status_code': 202, 'message': 'Package {} sent to pipeline {} for re-ingest'.format(self.uuid, pipeline)}

    def finish_reingest(self, origin_location, origin_path, reingest_location, reingest_path):
        """
        Updates an existing AIP with the reingested version.

        Fetches the AIP from the origin_location.
        Replaces the METS with the updated one.
        Copies the new metadata directory over the old one. New files will be added, updated files will be overwritten.
        Recreate the bagit manifest.
        Compress the AIP according to what was selected during reingest in Archivematica.
        Store the AIP in the reingest_location.
        Update the pointer file.

        :param Location origin_location: Location the AIP was procesed on.
        :param str origin_path: Path to AIP in current location.
        :param Location reingest_location: Location to store the updated AIP in.
        :param str reingest_path: Path to store the updated AIP at.
        """
        # Check origin pipeline against stored pipeline
        if self.origin_pipeline.uuid != self.misc_attributes.get('reingest_pipeline'):
            LOGGER.info('Reingest: Received pipeline %s did not match expected pipeline %s', self.origin_pipeline.uuid, self.misc_attributes.get('reingest_pipeline'))
            raise Exception('%s did not match the pipeline this AIP was reingested on.' % self.origin_pipeline.uuid)
        self.misc_attributes.update({'reingest_pipeline': None})
        self.save()

        src_space = origin_location.space
        ss_internal = Location.objects.get(purpose=Location.STORAGE_SERVICE_INTERNAL)
        internal_space = ss_internal.space
        dest_space = reingest_location.space

        # Take note of whether old version of AIP was compressed
        was_compressed = self.is_compressed

        # Copy actual AIP to ss_internal, extract if needed
        path, temp_dir = self.extract_file()  # AIP always copied

        # Move reingest AIP to ss_internal
        src_space.move_to_storage_service(
            source_path=os.path.join(origin_location.relative_path, origin_path),
            destination_path=reingest_path,  # This should include Location.path
            destination_space=internal_space)
        internal_space.move_from_storage_service(
            source_path=reingest_path,  # This should include Location.path
            destination_path=os.path.join(ss_internal.relative_path, reingest_path),
        )
        reingest_full_path = os.path.join(ss_internal.full_path, reingest_path)

        # Take note of whether new version of AIP should be compressed
        to_be_compressed = os.path.isfile(reingest_full_path)

        # Extract if needed
        if os.path.isfile(reingest_full_path):
            # TODO modify extract_file and get_base_directory to handle reingest paths?  Update self.local_path sooner?
            # Extract
            command = ['unar', '-force-overwrite', '-o', ss_internal.full_path, reingest_full_path]
            LOGGER.info('Extracting with: {}'.format(command))
            rc = subprocess.call(command)
            LOGGER.debug('Extract file RC: %s', rc)
            # Get output path
            command = ['lsar', '-ja', reingest_full_path]
            try:
                output = subprocess.check_output(command)
                j = json.loads(output)
                bname = sorted([d['XADFileName'] for d in j['lsarContents'] if d.get('XADIsDirectory', False)], key=len)[0]
            except (subprocess.CalledProcessError, ValueError):
                bname = os.path.splitext(os.path.basename(reingest_full_path))[0]
                LOGGER.warning('Unable to parse base directory from package, using basename %s', bname)
            else:
                LOGGER.debug('AIP extracted, removing original package %s', reingest_full_path)
                os.remove(reingest_full_path)
                reingest_full_path = os.path.join(ss_internal.full_path, bname)
        LOGGER.debug('Reingest AIP full path: %s', reingest_full_path)

        # Copy pointer file if exists
        # TODO what do if LOCKSS?
        if self.package_type in (Package.AIP, Package.AIC) and to_be_compressed:
            reingest_pointer_src = os.path.join(origin_location.relative_path, os.path.dirname(origin_path), 'pointer.xml')

            # If reingesting a previously compressed AIP, make a temporary "reingest" pointer (otherwise make a normal one)
            if was_compressed:
                reingest_pointer_name = 'pointer.' + self.uuid + '.reingest.xml'
                reingest_pointer_dst = os.path.join(ss_internal.relative_path, reingest_pointer_name)
            else:
                reingest_pointer_name = 'pointer.' + self.uuid + '.xml'
                reingest_pointer_dst = os.path.join(ss_internal.relative_path, utils.uuid_to_path(self.uuid), reingest_pointer_name)

                self.pointer_file_location = Location.active.get(purpose=Location.STORAGE_SERVICE_INTERNAL)
                self.pointer_file_path = os.path.join(utils.uuid_to_path(self.uuid), 'pointer.{}.xml'.format(self.uuid))

            src_space.move_to_storage_service(reingest_pointer_src, reingest_pointer_name, internal_space)
            internal_space.move_from_storage_service(reingest_pointer_name, reingest_pointer_dst)

            if was_compressed:
                reingest_pointer = os.path.join(ss_internal.full_path, reingest_pointer_name)
            else:
                reingest_pointer = os.path.join(ss_internal.full_path, utils.uuid_to_path(self.uuid), reingest_pointer_name)

                # Remove initial copy of pointer
                os.remove(os.path.join(ss_internal.full_path, reingest_pointer_name))

        # Replace METS
        original_mets_path = os.path.join(path, 'data', 'METS.' + self.uuid + '.xml')
        reingest_mets_path = os.path.join(reingest_full_path, 'data', 'METS.' + self.uuid + '.xml')
        LOGGER.info('Replacing original METS %s with reingested METS %s', original_mets_path, reingest_mets_path)
        os.remove(original_mets_path)
        os.rename(reingest_mets_path, original_mets_path)

        # Replace new metadata files
        reingest_metadata_dir = os.path.join(reingest_full_path, 'data', 'objects', 'metadata')
        original_metadata_dir = os.path.join(path, 'data', 'objects', 'metadata')
        LOGGER.info('Replacing original metadata directory %s with reingested metadata directory %s', original_metadata_dir, reingest_metadata_dir)
        if os.path.isdir(reingest_metadata_dir):
            distutils.dir_util.copy_tree(reingest_metadata_dir,
                original_metadata_dir)

        # Update bag payload and verify
        bag = bagit.Bag(path)
        bag.save(manifests=True)
        bag.validate()  # Raises exception in case of problem

        # Compress if necessary
        if to_be_compressed:
            reingest_root = etree.parse(reingest_pointer)
            # If updating, rather than creating a new pointer file, delete this pointer file
            if was_compressed:
                os.remove(reingest_pointer)
            puid = reingest_root.findtext('.//premis:formatRegistryKey', namespaces=utils.NSMAP)
            if puid == 'fmt/484':  # 7 Zip
                algo = reingest_root.find('.//mets:transformFile', namespaces=utils.NSMAP).get('TRANSFORMALGORITHM')
                if algo == 'bzip2':
                    compression = self.COMPRESSION_7Z_BZIP
                elif algo == 'lzma':
                    compression = self.COMPRESSION_7Z_LZMA
                else:
                    compression = self.COMPRESSION_7Z_BZIP
                    LOGGER.warning('Reingest: Unable to determine reingested compression algorithm, defaulting to bzip2.')
            elif puid == 'x-fmt/268':  # Bzipped (probably tar)
                compression = self.COMPRESSION_TAR_BZIP2
            else:
                compression = self.COMPRESSION_7Z_BZIP
                LOGGER.warning('Reingest: Unable to determine reingested file format, defaulting recompression algorithm to %s.', compression)
            LOGGER.info('Reingest: compressing with %s', compression)
            # FIXME Do we need compression output for event?
            out_path, out_dir = self.compress_package(compression)
            compress_output = ''

            # Delete working files
            shutil.rmtree(reingest_full_path)
            shutil.rmtree(temp_dir)
        else:
            out_path = self.fetch_local_path()
            out_dir = os.path.dirname(out_path)

        # Recalculate size - may have changed because of preservation derivatives or metadata-only reingest
        # If AIP is a directory, calculate size recursively
        if os.path.isdir(out_path):
            size = 0
            for dirpath, _, filenames in os.walk(out_path):
                for filename in filenames:
                    file_path = os.path.join(dirpath, filename)
                    size += os.path.getsize(file_path)
        else:
            size = os.path.getsize(out_path)
        self.size = size

        # Move to final destination
        src_path = out_path.replace(ss_internal.space.path, '', 1).lstrip('/')

        # This allows uncompressed AIP to be rsynced properly
        if not to_be_compressed:
            src_path = src_path + '/'

        uuid_path = utils.uuid_to_path(self.uuid)
        dest_path = out_path.replace(out_dir, '', 1).lstrip('/')
        dest_path = os.path.join(uuid_path, dest_path)
        internal_space.move_to_storage_service(
            source_path=src_path,
            destination_path=dest_path,  # This should include Location.path
            destination_space=dest_space)
        dest_space.move_from_storage_service(
            source_path=dest_path,  # This should include Location.path
            destination_path=os.path.join(reingest_location.relative_path, dest_path),
        )

        # Delete old copy of AIP if different
        if self.current_path != dest_path or self.current_location != reingest_location:
            LOGGER.info('Old copy of reingested AIP is at a different location.  Deleting %s', self.full_path)
            self.current_location.space.delete_path(self.full_path)

        self.current_location = reingest_location
        self.current_path = dest_path

        if to_be_compressed:
            # Update pointer file
            root = etree.parse(self.full_pointer_file_path)

            # Add compression event (if compressed)
            amdsec = root.find('mets:amdSec', namespaces=utils.NSMAP)
            if compression in (self.COMPRESSION_7Z_BZIP, self.COMPRESSION_7Z_LZMA):
                try:
                    version = [x for x in subprocess.check_output('7z').splitlines() if 'Version' in x][0]
                    event_detail = 'program="7z"; version="{}"'.format(version)
                except (subprocess.CalledProcessError, Exception):
                    event_detail = 'program="7z"'
            elif compression in (self.COMPRESSION_TAR_BZIP2, self.COMPRESSION_TAR):
                try:
                    version = subprocess.check_output(['tar', '--version']).splitlines()[0]
                    event_detail = 'program="tar"; version="{}"'.format(version)
                except (subprocess.CalledProcessError, Exception):
                    event_detail = 'program="tar"'
            else:
                LOGGER.warning('Unknown compression algorithm, cannot correctly update pointer file')
                event_detail = 'Unknown compression'
            utils.mets_add_event(
                amdsec,
                'compression',
                event_detail=event_detail,
                event_outcome_detail_note=compress_output,
            )

            self.update_pointer_file(compression, root=root, path=out_path)
        elif was_compressed:
            # AIP used to be compressed, but is no longer so delete pointer file
            os.remove(self.full_pointer_file_path)
            self.pointer_file_location = None
            self.pointer_file_path = None

        self.save()

        # Delete working files
        shutil.rmtree(out_dir)

    def update_pointer_file(self, compression, root=None, path=None):
        if not root:
            root = etree.parse(self.full_pointer_file_path)
        if not path:
            path = self.fetch_local_path()

        # Update FLocat to full path
        file_ = root.find('.//mets:fileGrp[@USE="Archival Information Package"]/mets:file', namespaces=utils.NSMAP)
        flocat = file_.find('mets:FLocat[@OTHERLOCTYPE="SYSTEM"][@LOCTYPE="OTHER"]', namespaces=utils.NSMAP)
        flocat.set(utils.PREFIX_NS['xlink'] + 'href', self.full_path)

        # Update fixity checksum
        fixity_elem = root.find('.//premis:fixity', namespaces=utils.NSMAP)
        algorithm = fixity_elem.findtext('premis:messageDigestAlgorithm', namespaces=utils.NSMAP)
        try:
            checksum = utils.generate_checksum(path, algorithm)
        except ValueError:
            # If incorrectly parsed algorithm, default to sha512, since that is
            # what AM uses
            checksum = utils.generate_checksum(path, 'sha512')
        fixity_elem.find('premis:messageDigest', namespaces=utils.NSMAP).text = checksum.hexdigest()

        # Update size
        root.find('.//premis:size', namespaces=utils.NSMAP).text = str(os.path.getsize(path))

        # Set compression related data
        comp_level = '1'
        transform_file = []
        if compression in (self.COMPRESSION_7Z_BZIP, self.COMPRESSION_7Z_LZMA):
            if compression == self.COMPRESSION_7Z_BZIP:
                algo = 'bzip2'
            elif compression == self.COMPRESSION_7Z_LZMA:
                algo = 'lzma'
            transform_file.append(
                etree.Element(utils.PREFIX_NS['mets'] + "transformFile",
                    TRANSFORMORDER='1',
                    TRANSFORMTYPE='decompression',
                    TRANSFORMALGORITHM=algo,
                )
            )
            version = [x for x in subprocess.check_output('7z').splitlines() if 'Version' in x][0]
            format_info = {
                'name': '7Zip format',
                'registry_name': 'PRONOM',
                'registry_key': 'fmt/484',
                'program_name': '7-Zip',
                'program_version': version,
            }

        elif compression in (self.COMPRESSION_TAR_BZIP2, self.COMPRESSION_TAR):
            transform_order = '1'
            if compression == self.COMPRESSION_TAR_BZIP2:
                comp_level = '2'
                transform_file.append(
                    etree.Element(utils.PREFIX_NS['mets'] + "transformFile",
                        TRANSFORMORDER='1',
                        TRANSFORMTYPE='decompression',
                        TRANSFORMALGORITHM='bzip2',
                    )
                )
                transform_order = '2'

            transform_file.append(
                etree.Element(utils.PREFIX_NS['mets'] + "transformFile",
                    TRANSFORMORDER=transform_order,
                    TRANSFORMTYPE='decompression',
                    TRANSFORMALGORITHM='tar',
                )
            )
            version = subprocess.check_output(['tar', '--version']).splitlines()[0]
            format_info = {
                'name': 'BZIP2 Compressed Archive',
                'registry_name': 'PRONOM',
                'registry_key': 'x-fmt/268',
                'program_name': 'tar',
                'program_version': version,
            }

        # Update compositionLevel
        root.find('.//premis:compositionLevel', namespaces=utils.NSMAP).text = comp_level

        # Set new format info
        fmt = root.find('.//premis:format', namespaces=utils.NSMAP)
        fmt.clear()
        fd = etree.SubElement(fmt, utils.PREFIX_NS['premis'] + 'formatDesignation')
        etree.SubElement(fd, utils.PREFIX_NS['premis'] + 'formatName').text = format_info.get('name')
        etree.SubElement(fd, utils.PREFIX_NS['premis'] + 'formatVersion').text = format_info.get('version')
        fr = etree.SubElement(fmt, utils.PREFIX_NS['premis'] + 'formatRegistry')
        etree.SubElement(fr, utils.PREFIX_NS['premis'] + 'formatRegistryName').text = format_info.get('registry_name')
        etree.SubElement(fr, utils.PREFIX_NS['premis'] + 'formatRegistryKey').text = format_info.get('registry_key')

        # Creating application info
        now = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        app = root.find('.//premis:creatingApplication', namespaces=utils.NSMAP)
        app.clear()
        etree.SubElement(app, utils.PREFIX_NS['premis'] + 'creatingApplicationName').text = format_info.get('program_name')
        etree.SubElement(app, utils.PREFIX_NS['premis'] + 'creatingApplicationVersion').text = format_info.get('program_version')
        etree.SubElement(app, utils.PREFIX_NS['premis'] + 'dateCreatedByApplication').text = str(now)

        # Remove existing transformFiles
        to_delete = file_.findall('mets:transformFile', namespaces=utils.NSMAP)
        for elem in to_delete:
            file_.remove(elem)
        # Add new ones
        for elem in transform_file:
            file_.append(elem)

        # Write out pointer file again
        with open(self.full_pointer_file_path, 'w') as f:
            f.write(etree.tostring(root, pretty_print=True))

    # SWORD-related methods
    def has_been_submitted_for_processing(self):
        return 'deposit_completion_time' in self.misc_attributes
