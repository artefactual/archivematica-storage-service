from __future__ import absolute_import
# stdlib, alphabetical
from collections import namedtuple
import distutils.dir_util
import json
import logging
from lxml import etree
import os
import re
import shutil
import subprocess
import tempfile
from uuid import uuid4

# Core Django, alphabetical
from django.conf import settings
from django.db import models
from django.utils.translation import ugettext as _, ugettext_lazy as _l
from django.utils import timezone

# Third party dependencies, alphabetical
import bagit
import jsonfield
from django_extensions.db.fields import UUIDField
import metsrw
import requests

# This project, alphabetical
from common import utils
from locations import signals

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
                     help_text=_l("Unique identifier"))
    description = models.CharField(
        max_length=256, default=None, null=True, blank=True,
        help_text=_l("Human-readable description."))
    origin_pipeline = models.ForeignKey('Pipeline', to_field='uuid', null=True,
                                        blank=True)
    current_location = models.ForeignKey(Location, to_field='uuid')
    current_path = models.TextField()
    pointer_file_location = models.ForeignKey(
        Location, to_field='uuid', related_name='+', null=True, blank=True)
    pointer_file_path = models.TextField(null=True, blank=True)
    size = models.IntegerField(default=0,
                               help_text=_l('Size in bytes of the package'))
    encryption_key_fingerprint = models.CharField(
        max_length=512, blank=True, null=True, default=None,
        help_text=_l('The fingerprint of the GPG key used to encrypt the'
                     ' package, if applicable'))
    replicated_package = models.ForeignKey('Package', to_field='uuid',
                                           null=True, blank=True,
                                           related_name='replicas')

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
        (TRANSFER, _l('Transfer')),
        (FILE, _l('Single File')),
        (DEPOSIT, _l('FEDORA Deposit'))
    )
    package_type = models.CharField(max_length=8, choices=PACKAGE_TYPE_CHOICES)
    related_packages = models.ManyToManyField('self', related_name='related')

    DEFAULT_CHECKSUM_ALGORITHM = 'sha256'

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
        (PENDING, _l("Upload Pending")),  # Still on Archivematica
        (STAGING, _l("Staged on Storage Service")),  # In Storage Service staging dir
        (UPLOADED, _l("Uploaded")),  # In final storage location
        (VERIFIED, _l("Verified")),  # Verified to be in final storage location
        (FAIL, _l("Failed")),  # Error occured - may or may not be at final location
        (DEL_REQ, _l("Delete requested")),
        (DELETED, _l("Deleted")),
        (FINALIZED, _l("Deposit Finalized")),
    )
    status = models.CharField(
        max_length=8, choices=STATUS_CHOICES, default=FAIL,
        help_text=_l("Status of the package in the storage service."))
    # NOTE Do not put anything important here because you cannot easily query
    # JSONFields! Add a new column if you need to query it
    misc_attributes = jsonfield.JSONField(
        blank=True, null=True, default={},
        help_text=_l('For storing flexible, often Space-specific, attributes'))

    # Temporary attributes to track path on locally accessible filesystem
    local_path = None
    local_path_location = None

    PACKAGE_TYPE_CAN_DELETE = (AIP, AIC, TRANSFER)
    PACKAGE_TYPE_CAN_EXTRACT = (AIP, AIC)
    PACKAGE_TYPE_CAN_RECOVER = (AIP, AIC)
    PACKAGE_TYPE_CAN_REINGEST = (AIP, AIC)

    # Reingest type options
    METADATA_ONLY = 'metadata'  # Re-ingest metadata only
    OBJECTS = 'objects'         # Re-ingest metadata and objects for DIP generation
    FULL = 'full'               # Full re-ingest
    REINGEST_CHOICES = (METADATA_ONLY, OBJECTS, FULL)

    class Meta:
        verbose_name = _l("Package")
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
        return os.path.join(self.pointer_file_location.full_path,
                            self.pointer_file_path)

    def is_encrypted(self, local_path):
        """Determines whether or not the package at ``local_path`` is
        encrypted. Note that we can't compare the type of the child space to
        GPG because that would cause a circular import.
        """
        space_is_encr = getattr(self.current_location.space.get_child_space(),
                                'encrypted_space',
                                False)
        is_file = os.path.isfile(local_path)
        return space_is_encr and is_file

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
                message = _('Package %(uuid)s (located at %(path)s) does not exist') % {'uuid': self.uuid, 'path': full_path}

            else:
                message = _('%(path)s is neither a file nor a directory') % {'path': full_path}
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
                raise StorageException(_("Cannot return a download path for an uncompressed package"))
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
        """Return a locally accessible path to this Package if available.

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
        """Fetches a local copy of the package.

        Return local path if package is already available locally. Otherwise,
        copy to SS Internal Location, and return that path.

        :returns: Local path to this package.
        """
        local_path = self.get_local_path()
        if local_path and not self.is_encrypted(local_path):
            return local_path
        # Not locally accessible, so copy to SS internal temp dir
        ss_internal = Location.active.get(
            purpose=Location.STORAGE_SERVICE_INTERNAL)
        temp_dir = tempfile.mkdtemp(dir=ss_internal.full_path)
        int_path = os.path.join(temp_dir, self.current_path)

        # If encrypted, this will decrypt.
        self.current_location.space.move_to_storage_service(
            source_path=os.path.join(
                self.current_location.relative_path, self.current_path),
            destination_path=self.current_path,
            destination_space=ss_internal.space,
        )

        relative_path = int_path.replace(
            ss_internal.space.path, '', 1).lstrip('/')

        ss_internal.space.move_from_storage_service(
            source_path=self.current_path,
            destination_path=relative_path,
            package=self,
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
            raise NotImplementedError(_("This method currently only retrieves base directories for locally-available AIPs."))

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
            output = subprocess.check_output(command)
            output = json.loads(output)
            directories = [d['XADFileName'] for d in output['lsarContents'] if
                           d.get('XADIsDirectory', False)]
            directories = sorted(directories, key=len)
            return directories[0]
        return os.path.basename(full_path)

    def _check_quotas(self, dest_space, dest_location):
        """
        Verify that there is enough storage space on dest_space and dest_location for this package.  All sizes in bytes.
        """
        # Check if enough space on the space and location
        # All sizes expected to be in bytes
        if dest_space.size is not None and dest_space.used + self.size > dest_space.size:
            raise StorageException(_('Not enough space for AIP on storage device %(space)s; Used: %(used)s; Size: %(size)s; AIP size: %(aip_size)s') % {'space': dest_space, 'used': dest_space.used, 'size': dest_space.size, 'aip_size': self.size})
        if (dest_location.quota is not None and
                dest_location.used + self.size > dest_location.quota):
            raise StorageException(_('AIP too big for quota on %(location)s; Used: %(used)s; Quota: %(quota)s; AIP size: %(aip_size)s') % {'location': dest_location, 'used': dest_location.used, 'quota': dest_location.quota, 'aip_size': self.size})

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
        (success, failures, message, __) = temp_aip.check_fixity(force_local=True)

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
            destination_path=destination_path,
            package=self)
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
            destination_path=destination_path,
            package=self)
        destination_space.post_move_from_storage_service(
            staging_path=None,
            destination_path=None)

        temp_aip.delete()

        # Do fixity check of AIP with recovered files
        success, failures, message, __ = self.check_fixity(force_local=True)
        return success, failures, message

    def replicate(self, replicator_location_uuid):
        """Replicate this package in the database and on disk by
        1. creating a new ``Package`` model instance that references this one in
           its ``replicated_package`` attribute,
        2. copying the AIP on disk to a new path in the replicator location
           referenced by ``replicator_location_uuid``,
        3. creating a new pointer file for the replica, which encodes the
           replication event, and
        4. updating the pointer file for the replicated AIP, which encodes the
           replication event.
        """
        self_uuid = self.uuid
        replicator_location = Location.objects.get(
            uuid=replicator_location_uuid)
        # Replicandum is the package to be replicated, i.e., ``self``
        replicandum_location = self.current_location
        replicandum_path = self.current_path
        replicandum_uuid = self.uuid
        LOGGER.info('Replicating package %s to replicator location %s',
                    replicandum_uuid, replicator_location_uuid)
        replica_package = _replicate_package_mdl_inst(self)

        # It is necessary to re-retrieve ``self`` here because otherwise the
        # package model instance replication will cause ``self`` to reference
        # the replica.
        self = Package.objects.get(uuid=self_uuid)

        # Remove the /uuid/path from the replica's current_path and replace the
        # old UUID in the basename with the new UUID.
        replica_package.current_path = os.path.basename(
            replicandum_path.rstrip('/')).replace(
            replicandum_uuid, replica_package.uuid, 1)
        replica_package.current_location = replicator_location

        # Check if enough space on the space and location
        src_space = replicandum_location.space
        dest_space = replica_package.current_location.space
        self._check_quotas(dest_space, replica_package.current_location)

        # Replicate AIP at
        # destination_location/uuid/split/into/chunks/destination_path
        uuid_path = utils.uuid_to_path(replica_package.uuid)
        replica_package.current_path = os.path.join(
            uuid_path, replica_package.current_path)
        replica_destination_path = os.path.join(
            replica_package.current_location.relative_path,
            replica_package.current_path)
        replica_package.status = Package.PENDING
        replica_package.save()

        # Get the master AIP's pointer file and extract the checksum details
        master_ptr = self.get_pointer_instance()
        master_ptr_aip_fsentry = master_ptr.get_file(file_uuid=self.uuid)
        master_premis_object = master_ptr_aip_fsentry.get_premis_objects()[0]
        master_checksum_algorithm = master_premis_object.message_digest_algorithm
        master_checksum = master_premis_object.message_digest

        # Copy replicandum AIP from its source location to the SS
        src_space.move_to_storage_service(
            source_path=os.path.join(replicandum_location.relative_path,
                                     replicandum_path),
            destination_path=replica_package.current_path,
            destination_space=dest_space)
        replica_package.status = Package.STAGING
        replica_package.save()
        src_space.post_move_to_storage_service()

        # Calculate the checksum of the replica while we have it locally,
        # compare it to the master's checksum and create a PREMIS validation
        # event out of the result.
        replica_local_path = self.get_local_path()
        replica_checksum = utils.generate_checksum(
            replica_local_path, master_checksum_algorithm).hexdigest()
        checksum_report = _get_checksum_report(
            master_checksum, self.uuid, replica_checksum, replica_package.uuid,
            master_checksum_algorithm)
        replication_validation_event = (
            replica_package.get_replication_validation_event(
                checksum_report=checksum_report,
                master_aip_uuid=self.uuid))

        # Create and write to disk the pointer file for the replica, which
        # contains the PREMIS replication event.
        replication_event_uuid = str(uuid4())
        # replica_package_pointer_file_full_path = os.path.join(
        #     replica_package.pointer_file_location.space.path,
        #     replica_package.pointer_file_location.relative_path,
        #     replica_package.pointer_file_path)
        replica_pointer_file = self.create_replica_pointer_file(
            replica_package, replication_event_uuid,
            replication_validation_event, master_ptr=master_ptr)
        write_pointer_file(replica_pointer_file,
                           replica_package.full_pointer_file_path)
        replica_package.save()

        # Copy replicandum AIP from the SS to replica package's replicator
        # location.
        replica_storage_effects = dest_space.move_from_storage_service(
            source_path=replica_package.current_path,
            destination_path=replica_destination_path,
            package=replica_package)
        if dest_space.access_protocol not in (Space.LOM, Space.ARKIVUM):
            replica_package.status = Package.UPLOADED
        replica_package.save()
        dest_space.post_move_from_storage_service(
            staging_path=replica_package.current_path,
            destination_path=replica_destination_path,
            package=replica_package)
        self._update_quotas(dest_space, replica_package.current_location)

        # Any effects resulting from AIP storage (e.g., encryption) are
        # recorded in the replica's pointer file.
        if replica_storage_effects:
            revised_replica_pointer_file = (
                replica_package.create_new_pointer_file_given_storage_effects(
                    replica_pointer_file, replica_storage_effects))
            write_pointer_file(revised_replica_pointer_file,
                               replica_package.full_pointer_file_path)

        # Update the pointer file of the replicated AIP (master) so that it
        # contains a record of its replication.
        new_master_pointer_file = self.create_new_pointer_file_with_replication(
            master_ptr, replica_package, replication_event_uuid)
        write_pointer_file(new_master_pointer_file, self.full_pointer_file_path)

        LOGGER.info('Finished replicating package %s as replica package %s',
                    replicandum_uuid, replica_package.uuid)

    def should_have_pointer_file(self, package_full_path=None,
                                 package_type=None):
        """Returns ``True`` if the package is both an AIP/AIC and is a file.
        Note: because storage in certain locations (e.g., GPG encrypted
        locations) can result in packaging and hence transformation of an AIP
        directory to an AIP file, this predicate may return ``True`` after
        ``move_from_storage_service`` is called but ``False`` before.
        """
        if not package_full_path:
            package_full_path = os.path.join(
                self.current_location.space.path,
                self.current_location.relative_path,
                self.current_path)
        if not package_type:
            package_type = self.package_type
        isfile = os.path.isfile(package_full_path)
        isaip = package_type in (Package.AIP, Package.AIC)
        ret = isfile or isaip
        if not ret:
            if not isfile:
                LOGGER.info('Package should not have a pointer file because %s'
                            ' is not a file', package_full_path)
            if not isaip:
                LOGGER.info('Package should not have a pointer file because it'
                            ' is not an AIP or an AIC; it is a(n) %s', package_type)
        return ret

    # ==========================================================================
    # Store AIP methods
    # ==========================================================================

    def store_aip(self, origin_location, origin_path, related_package_uuid=None,
                  premis_events=None, premis_agents=None, aip_subtype=None):
        """Stores an AIP in the correct Location.

        Invokes different transfer mechanisms depending on what the source and
        destination Spaces are. High-level steps (see auxiliary methods for
        details):

        1. Get AIP to the "pending" stage: check space quotas (raising
           ``StorageException if insufficient) and get needed vars into ``v``.
        2. Get AIP to the "uploaded" stage: move the AIP to its AIP Storage
           location and update space quotas after move.
        3. Ensure the AIP has a pointer file, if applicable.
        4. Create replicas of the AIP, if applicable.

        The AIP is initially located in location ``origin_location`` at
        relative path ``origin_path``. Once stored, the AIP should be in
        location ``self.current_location`` at relative path
        ``<UUID_AS_PATH>/self.current_path``. In the course of this method,
        values on the ``Package`` instance are updated (including status) and
        periodically saved to the db.
        """
        LOGGER.info('store_aip called in Package class of SS')
        v = self._store_aip_to_pending(origin_location, origin_path)
        storage_effects = self._store_aip_to_uploaded(v, related_package_uuid)
        self._store_aip_ensure_pointer_file(
            v, premis_events=premis_events, premis_agents=premis_agents,
            aip_subtype=aip_subtype)
        if storage_effects:
            pointer_file = self.get_pointer_instance()
            revised_pointer_file = (
                self.create_new_pointer_file_given_storage_effects(
                    pointer_file, storage_effects))
            write_pointer_file(revised_pointer_file,
                               self.full_pointer_file_path)
        self.create_replicas()

    def _store_aip_to_pending(self, origin_location, origin_path):
        """Get this AIP to the "pending" stage of ``store_aip`` by
        1. settting and persisting attributes on ``self`` (including
           ``status=Package.PENDING``),
        2. checking that the destination space has enough space for the AIP to
           be stored (and raising an exception if not), and
        3. returning a simple object with attributes needed in the rest of
           ``store_aip``.
        """
        V = namedtuple('V', ['src_space', 'dest_space', 'should_have_pointer',
                             'pointer_file_src', 'pointer_file_dst',
                             'already_generated_ptr_exists'])
        self.origin_location = origin_location
        self.origin_path = origin_path
        origin_full_path = os.path.join(
            self.origin_location.space.path,
            self.origin_location.relative_path,
            self.origin_path)
        # Check if enough space on the space and location
        # All sizes expected to be in bytes
        src_space = self.origin_location.space
        dest_space = self.current_location.space
        self._check_quotas(dest_space, self.current_location)
        # Store AIP at
        # destination_location/uuid/split/into/chunks/destination_path
        uuid_path = utils.uuid_to_path(self.uuid)
        self.current_path = os.path.join(uuid_path, self.current_path)
        self.status = Package.PENDING
        self.save()
        # If applicable, we will store the AIP pointer file at
        # internal_usage_location/uuid/split/into/chunks/pointer.uuid.xml
        should_have_pointer = self.should_have_pointer_file(
            package_full_path=origin_full_path)
        pointer_file_src = pointer_file_dst = already_generated_ptr_exists = \
            None
        if should_have_pointer:
            self.pointer_file_location = Location.active.get(
                purpose=Location.STORAGE_SERVICE_INTERNAL)
            self.pointer_file_path = os.path.join(
                uuid_path, 'pointer.{}.xml'.format(self.uuid))
            pointer_file_src = os.path.join(
                self.origin_location.relative_path,
                os.path.dirname(self.origin_path),
                'pointer.xml')
            pointer_file_dst = os.path.join(
                self.pointer_file_location.relative_path,
                self.pointer_file_path)
            already_generated_ptr_full_path = os.path.join(
                self.origin_location.space.path,
                pointer_file_src)
            already_generated_ptr_exists = os.path.isfile(
                already_generated_ptr_full_path)
        return V(
            src_space=src_space,
            dest_space=dest_space,
            should_have_pointer=should_have_pointer,
            pointer_file_src=pointer_file_src,
            pointer_file_dst=pointer_file_dst,
            already_generated_ptr_exists=already_generated_ptr_exists)

    def _store_aip_to_uploaded(self, v, related_package_uuid):
        """Get this AIP to the "uploaded" stage of ``store_aip`` by
        1. moving it to the SS internal location,
        2. setting its status to "staging",
        3. calling ``post_move_to_storage_service`` on the source space,
        4. moving it to the destination space/location,
        5. setting the status to "uploaded" (if applicable),
        6. setting a related package (if applicable),
        7. calling ``post_move_from_storage_service`` on the destination space,
        8. updating quotas on the destination space, and
        9. persisting the package to the database.
        :param namedtuple v: object with attributes needed for processing.
        :param str related_package_uuid: UUID of a related package.
        :returns NoneType None:
        """
        v.src_space.move_to_storage_service(
            source_path=os.path.join(self.origin_location.relative_path,
                                     self.origin_path),
            destination_path=self.current_path,  # This should include Location.path
            destination_space=v.dest_space)
        self.status = Package.STAGING
        self.save()
        v.src_space.post_move_to_storage_service()
        storage_effects = v.dest_space.move_from_storage_service(
            source_path=self.current_path,  # This should include Location.path
            destination_path=os.path.join(
                self.current_location.relative_path,
                self.current_path),
            package=self,
        )
        # Update package status once transferred to SS
        if v.dest_space.access_protocol not in (Space.LOM, Space.ARKIVUM):
            self.status = Package.UPLOADED
        if related_package_uuid is not None:
            related_package = Package.objects.get(uuid=related_package_uuid)
            self.related_packages.add(related_package)
        self.save()
        v.dest_space.post_move_from_storage_service(
            staging_path=self.current_path,
            destination_path=os.path.join(
                self.current_location.relative_path, self.current_path),
            package=self)
        self._update_quotas(v.dest_space, self.current_location)
        return storage_effects

    def _store_aip_ensure_pointer_file(self, v, premis_events=None,
                                       premis_agents=None, aip_subtype=None):
        """Ensure that this newly stored AIP has a pointer file by moving an
        AM-created pointer file to the appropriate SS location if such a
        pointer file exists or by creating a pointer file (if necessary)
        otherwise. Set pointer file-related attributes on the model instance
        and save to the database. Optional args are only used if a pointer file
        must be created; see ``create_pointer_file`` for details.
        :param namedtuple v: object with attributes needed for processing.
        :returns NoneType None:
        """
        if v.should_have_pointer:
            if v.already_generated_ptr_exists:
                # Move an already-generated pointer file if exists.
                v.src_space.move_to_storage_service(
                    v.pointer_file_src,
                    self.pointer_file_path,
                    self.pointer_file_location.space)
                self.pointer_file_location.space.move_from_storage_service(
                    self.pointer_file_path,
                    v.pointer_file_dst,
                    package=None)
                self._update_existing_ptr_loc_info()  # Update its location info
            else:  # Otherwise, create a pointer file here.
                self._store_aip_create_pointer_file(
                    v.pointer_file_dst, premis_events,
                    premis_agents=premis_agents, aip_subtype=aip_subtype)
        else:  # This package should not have a pointer file
            self.pointer_file_location = None
            self.pointer_file_path = None
        self.save()

    def _store_aip_create_pointer_file(self, pointer_file_dst, premis_events,
                                       premis_agents=None, aip_subtype=None):
        """Create a pointer file and write it to disk for the ``store_aip``
        method.
        :param str pointer_file_dst:
        :param list premis_events:
        :param list premis_agents:
        :param str aip_subtype:
        :returns NoneType None:
        See ``create_pointer_file`` for details.
        """
        pointer_file_dst = os.path.join(
            self.pointer_file_location.space.path, pointer_file_dst)
        checksum_algorithm = Package.DEFAULT_CHECKSUM_ALGORITHM
        checksum = utils.generate_checksum(
            self.fetch_local_path(), checksum_algorithm).hexdigest()
        premis_events = [
            metsrw.PREMISEvent(data=event) for event in premis_events]
        compression_event = _find_compression_event(premis_events)
        if not compression_event:
            raise StorageException(_(
                'Failed to store AIP %(aip_uuid)s This AIP needs a'
                ' pointer file, however the Archivematica pipeline did'
                ' not create one and it also did not provide the'
                ' compression event needed for the Storage Service to'
                ' create one.' % {'aip_uuid': self.uuid}))
        __, compression_program_version, archive_tool = (
            compression_event.compression_details)
        premis_object = self._create_aip_premis_object(
            checksum_algorithm, checksum, archive_tool,
            compression_program_version)
        pointer_file = self.create_pointer_file(
            premis_object, premis_events, premis_agents=premis_agents,
            package_subtype=aip_subtype)
        if pointer_file is None:
            self.pointer_file_location = None
            self.pointer_file_path = None
        else:
            write_pointer_file(pointer_file, pointer_file_dst)

    def _update_existing_ptr_loc_info(self):
        """Update an AM-created pointer file's location information."""
        pointer_absolute_path = self.full_pointer_file_path
        root = etree.parse(pointer_absolute_path)
        element = root.find('.//mets:file', namespaces=utils.NSMAP)
        flocat = element.find('mets:FLocat', namespaces=utils.NSMAP)
        if self.uuid in element.get('ID', '') and flocat is not None:
            flocat.set('{{{ns}}}href'.format(ns=utils.NSMAP['xlink']),
                       self.full_path)
        # Add USE="Archival Information Package" to fileGrp. Required for
        # LOCKSS, and not provided in Archivematica <=1.1
        if root.find('.//mets:fileGrp[@USE="Archival Information Package"]',
                     namespaces=utils.NSMAP) is not None:
            root.find('.//mets:fileGrp', namespaces=utils.NSMAP).set(
                'USE', 'Archival Information Package')
        with open(pointer_absolute_path, 'w') as f:
            f.write(etree.tostring(root, pretty_print=True, xml_declaration=True, encoding='utf-8'))

    # ==========================================================================
    # END Store AIP methods
    # ==========================================================================

    def get_pointer_instance(self):
        """Return this package's pointer file as a ``metsrw.METSDocument``
        instance.
        """
        if not self.should_have_pointer_file():
            return None
        ptr_path = self.full_pointer_file_path
        if not ptr_path:
            return None
        return metsrw.METSWithPREMISDocument.fromfile(ptr_path)

    def create_replica_pointer_file(self, replica_package,
                                    replication_event_uuid,
                                    replication_validation_event,
                                    master_ptr=None):
        """Create and write to disk a new pointer file for the replica package
        Model instance ``replica_package``. Assume that ``self`` is the
        source/master of the replica.

        NOTE: Fixity check results are not currently included in the
        replication alidation event because of a circular dependency issue: the
        pointer file must exist (so we can get the used compression command
        from it) before we can extract the package in order to check its
        fixity. Here's how it could be done::

            >>> __, fixity_report = (
                replica_package.get_fixity_check_report_send_signals())
            >>> replication_validation_event = (
                replica_package.get_replication_validation_event(
                    checksum_report=checksum_report,
                    master_aip_uuid=self.uuid,
                    fixity_report=fixity_report,
                    agents=replica_premis_agents))

        Given that a checksum is calculated for the replica and that checksum
        is compared for equality to the master's checksum, it seems overkill to
        perform a BagIt fixity check as well. Is checksum comparison sufficient
        for replication validation or does a fixity check need to be performed
        also?
        """

        # 1. Set attrs and get full path to pointer file.
        should_have_pointer = replica_package.should_have_pointer_file()
        if not master_ptr:
            master_ptr = self.get_pointer_instance()
        if not should_have_pointer or not master_ptr:
            return
        uuid_path = utils.uuid_to_path(replica_package.uuid)
        replica_package.pointer_file_location = Location.active.get(
            purpose=Location.STORAGE_SERVICE_INTERNAL)
        replica_package.pointer_file_path = os.path.join(
            uuid_path, 'pointer.{}.xml'.format(replica_package.uuid))
        master_aip_uuid = self.uuid

        # 2. Get the master AIP's pointer file and extract what we need from it
        # in order to create the replica's pointer file.
        master_ptr_aip_fsentry = master_ptr.get_file(file_uuid=self.uuid)
        master_package_subtype = master_ptr_aip_fsentry.mets_div_type
        master_compression_event = [
            pe for pe in master_ptr_aip_fsentry.get_premis_events()
            if pe.event_type == 'compression'][0]
        master_premis_object = master_ptr_aip_fsentry.get_premis_objects()[0]
        master_checksum_algorithm = master_premis_object.message_digest_algorithm
        master_checksum = master_premis_object.message_digest
        master_premis_agents = master_ptr_aip_fsentry.get_premis_agents()

        # 3. Construct the pointer file and return it
        replica_premis_creation_agents = utils.get_ss_premis_agents()
        __, compression_program_version, archive_tool = (
            master_compression_event.compression_details)
        replica_premis_relationships = [
            _get_replication_derivation_relationship(master_aip_uuid,
                replication_event_uuid)]
        replica_premis_object = replica_package._create_aip_premis_object(
            master_checksum_algorithm, master_checksum, archive_tool,
            compression_program_version,
            premis_relationships=replica_premis_relationships)
        replica_premis_creation_event = (
            replica_package.get_premis_aip_creation_event(
                master_aip_uuid=master_aip_uuid,
                agents=replica_premis_creation_agents))
        replica_premis_agents = list(
            set(master_premis_agents + replica_premis_creation_agents))
        replica_premis_events = [
            master_compression_event,
            replica_premis_creation_event,
            replication_validation_event
        ]
        return replica_package.create_pointer_file(
            replica_premis_object,
            replica_premis_events,
            premis_agents=replica_premis_agents,
            package_subtype=master_package_subtype)

    def create_new_pointer_file_with_replication(self, old_pointer_file,
                                                 replica_package,
                                                 replication_event_uuid):
        """Create a new pointer file that is identical to ``old_pointer_file``,
        but which documents the replication of the AIP referenced by the old
        pointer file. Steps:
        1. Add a PREMIS event for the replication.
        2. Add a PREMIS relationship relating the AIP qua PREMIS object to its
           replica.
        3. Add any PREMIS agents of the replication event, if not already
           present in the mets:amdSec.
        To do this, we parse the existing pointer file and return a new one
        based on the old.
        """
        old_fsentry = old_pointer_file.get_file(file_uuid=self.uuid)
        package_subtype = old_fsentry.mets_div_type
        old_premis_object = old_fsentry.get_premis_objects()[0]
        old_premis_events = old_fsentry.get_premis_events()
        old_premis_agents = old_fsentry.get_premis_agents()
        ss_agents = utils.get_ss_premis_agents()
        replication_event = self.create_replication_event(
            replica_package, event_uuid=replication_event_uuid,
            agents=ss_agents)
        old_premis_events.append(replication_event)
        replication_relationship = _get_replication_derivation_relationship(
            replica_package.uuid, replication_event_uuid)
        old_premis_object = list(old_premis_object.data)
        old_premis_object.append(replication_relationship)
        new_premis_object = metsrw.PREMISObject(data=old_premis_object)
        for ss_agent in ss_agents:
            if ss_agent not in old_premis_agents:
                old_premis_agents.append(ss_agent)
        return self.create_pointer_file(
            new_premis_object, old_premis_events,
            premis_agents=old_premis_agents, package_subtype=package_subtype)

    def create_new_pointer_file_given_storage_effects(self, old_pointer_file,
                                                      storage_effects):
        """Create a new pointer file that is identical to ``old_pointer_file``,
        but which is altered in accordance with the effects of storing the AIP.
        This is useful when, for example, storage results in encryption.
        """
        old_fsentry = old_pointer_file.get_file(file_uuid=self.uuid)
        package_subtype = old_fsentry.mets_div_type
        old_premis_object = old_fsentry.get_premis_objects()[0]
        old_composition_level = old_premis_object.composition_level
        old_premis_events = old_fsentry.get_premis_events()
        old_premis_agents = old_fsentry.get_premis_agents()
        new_premis_events = list(
            set(old_premis_events + storage_effects.events))
        new_premis_agents = list(
            set(old_premis_agents + utils.get_ss_premis_agents()))
        new_composition_level = old_composition_level
        if storage_effects.composition_level_updater:
            new_composition_level = storage_effects.composition_level_updater(
                old_composition_level)
        new_inhibitors = storage_effects.inhibitors or []
        new_premis_object = metsrw.PREMISObject(
            xsi_type=old_premis_object.xsi_type,
            identifier_value=old_premis_object.identifier_value,
            message_digest_algorithm=old_premis_object.message_digest_algorithm,
            message_digest=old_premis_object.message_digest,
            size=old_premis_object.size,
            format_name=old_premis_object.format_name,
            format_registry_key=old_premis_object.format_registry_key,
            creating_application_name=old_premis_object.creating_application_name,
            creating_application_version=old_premis_object.creating_application_version,
            date_created_by_application=old_premis_object.date_created_by_application,
            relationships=old_premis_object.relationships,
            # New attributes:
            inhibitors=new_inhibitors,
            composition_level=new_composition_level,
        )
        return self.create_pointer_file(
            new_premis_object,
            new_premis_events,
            premis_agents=new_premis_agents,
            package_subtype=package_subtype)

    def create_replication_event(self, replica_package, event_uuid=None,
                                 agents=None, inst=True):
        """Return a PREMIS:EVENT for replication of an AIP, as a
        metsrw.premisrw.PREMISEvent or, if ``inst`` is ``False``, as a python
        Python tuple.
        """
        outcome_detail_note = (
            'Replicated Archival Information Package (AIP) {} by creating'
            ' replica {}.'.format(self.uuid, replica_package.uuid))
        if not agents:
            agents = utils.get_ss_premis_agents()
        if not event_uuid:
            event_uuid = str(uuid4())
        event = [
            'event',
            metsrw.PREMIS_META,
            (
                'event_identifier',
                ('event_identifier_type', 'UUID'),
                ('event_identifier_value', event_uuid),
            ),
            ('event_type', 'replication'),
            ('event_date_time', utils.mets_file_now()),
            ('event_detail', 'Replication of an Archival Information Package'),
            (
                'event_outcome_information',
                ('event_outcome', 'success'),
                (
                    'event_outcome_detail',
                    ('event_outcome_detail_note', outcome_detail_note)
                )
            )
        ]
        event = tuple(utils.add_agents_to_event_as_list(event, agents))
        if inst:
            return metsrw.PREMISEvent(data=event)
        return event

    def get_premis_aip_creation_event(self, master_aip_uuid=None, agents=None,
                                      inst=True):
        """Return a PREMIS:EVENT for creation of an AIP as a Python tuple."""
        if master_aip_uuid:
            outcome_detail_note = (
                'Created Archival Information Package (AIP) {} by replicating'
                ' previously created AIP {}'.format(self.uuid, master_aip_uuid))
        else:
            outcome_detail_note = (
                'Created Archival Information Package (AIP) {}'.format(
                    self.uuid))
        if not agents:
            agents = utils.get_ss_premis_agents()
        event = [
            'event',
            metsrw.PREMIS_META,
            (
                'event_identifier',
                ('event_identifier_type', 'UUID'),
                ('event_identifier_value', str(uuid4())),
            ),
            # Question: use the more specific 'information package creation'
            # PREMIS event?
            ('event_type', 'creation'),
            ('event_date_time', utils.mets_file_now()),
            ('event_detail', 'Creation of an Archival Information Package'),
            (
                'event_outcome_information',
                ('event_outcome', 'success'),
                (
                    'event_outcome_detail',
                    ('event_outcome_detail_note', outcome_detail_note)
                )
            )
        ]
        event = tuple(utils.add_agents_to_event_as_list(event, agents))
        if inst:
            return metsrw.PREMISEvent(data=event)
        return event

    def get_replication_validation_event(
            self, checksum_report, master_aip_uuid, fixity_report=None,
            agents=None, inst=True):
        """Return a PREMIS:EVENT (as a tuple) for validation of AIP
        replication.
        """
        success = checksum_report['success']
        if fixity_report:
            success = fixity_report['success'] and success
        outcome = success and 'success' or 'failure'
        detail = (
            'Validated the replication of Archival Information Package (AIP)'
            ' {master_aip_uuid} to replica AIP {replica_aip_uuid}'.format(
                master_aip_uuid=master_aip_uuid,
                replica_aip_uuid=self.uuid))
        if fixity_report:
            detail += (' by performing a BagIt fixity check and by comparing'
                       ' checksums')
            outcome_detail_note = '{}\n{}'.format(
                fixity_report['message'], checksum_report['message'])
        else:
            detail += ' by comparing checksums'
            outcome_detail_note = checksum_report['message']
        if not agents:
            agents = utils.get_ss_premis_agents()
        event = [
            'event',
            metsrw.PREMIS_META,
            (
                'event_identifier',
                ('event_identifier_type', 'UUID'),
                ('event_identifier_value', str(uuid4())),
            ),
            ('event_type', 'validation'),
            ('event_date_time', utils.mets_file_now()),
            ('event_detail', detail),
            (
                'event_outcome_information',
                ('event_outcome', outcome),
                (
                    'event_outcome_detail',
                    ('event_outcome_detail_note', outcome_detail_note)
                )
            )
        ]
        event = tuple(utils.add_agents_to_event_as_list(event, agents))
        if inst:
            return metsrw.PREMISEvent(data=event)
        return event

    def create_pointer_file(self,
                            premis_object,
                            premis_events,
                            premis_agents=None,
                            package_subtype=None,
                            validate=True):
        """Create and return a pointer file for this package.
        A pointer file is a METS XML file that describes an AIP as a black box.
        It does not describe the contents of the AIP but rather the nature of
        the AIP and the types of operations that must be performed on it in
        order to arrive at a canonical representation, e.g., decompression,
        decryption, and/or reassembly.
        :param tuple/metsrw.premisrw.PREMISObject premis_object: the
            PREMIS:OBJECT for the AIP itself.
        :param list premis_events: a list of PREMIS:EVENTs (tuples or
            metsrw.premisrw.PREMISEvent instances) representing events
            involving the AIP. In order for a pointer file to be created, this
            must contain a compression event performed by AM.
        :param list premis_agents: a list of PREMIS:AGENTs (tuples of
            metsrw.premisrw.PREMISAgent instances) representing premis_agents
            of the events in ``premis_events``.
        :param str package_subtype: representation of the AIP's package type.
            Default 'Archival Information Package' may be overridden by, for
            example, a Dublin Core type from user-specified metadata.
        :returns: the pointer file as a class:`metsrw.MetsDocument` instance.

        Events and agents must be expressed using tuples (or lists), using a
        structure that closely resembles XML. The first item of the tuple is
        the XML element's tag name, and subsequent elements can be
        strings---which become XML text---, tuples---which become XML
        sub-elements---, or dicts---which become XML attributes. See, for
        example, Archivematica's clientScripts/storeAIP.py::get_events_from_db.

        TODOs:
        - Retrieve AIP checksum from the model itself if it has already been
          generated (instead of generating it here.)
        - modify eventDetail from ``finish_reingest`` to encode compression
          algorithm.
        - test with pbzip2 compression

        Notes and Warnings:
        - the CREATEDATE attr of <mets:metsHdr> will be auto-generated by metsrw
          and will probably not be identical to
          <premis:dateCreatedByApplication>. Is this ok?
        """
        # Convert any PREMIS-entities-as-tuples/lists to
        # metsrw.premisrw.PREMISElement subclass instances. Note that
        # instantiating a PREMISElement by passing in an existing instance via
        # the ``data`` kwarg will construct an equivalent instance.
        premis_object = metsrw.PREMISObject(data=premis_object)
        premis_events = [metsrw.PREMISEvent(data=event) for event in premis_events]
        premis_agents = premis_agents or []
        premis_agents = [metsrw.PREMISAgent(data=agent) for agent in premis_agents]

        compression_event = _find_compression_event(premis_events)
        if not compression_event:  # no pointer files for uncompressed AIPs
            return
        transform_files = []
        encryption_event = _find_encryption_event(premis_events)
        if encryption_event:
            transform_files.append(
                encryption_event.get_decryption_transform_file())
        compression_transform_files = (
            compression_event.get_decompression_transform_files(
                offset=len(transform_files)))
        for tf in compression_transform_files:
            transform_files.append(tf)
        # Construct the METS pointer file
        pointer_file = metsrw.METSWithPREMISDocument()
        AIP_PACKAGE_TYPE = 'Archival Information Package'
        package_subtype = package_subtype or AIP_PACKAGE_TYPE
        mets_fs_entry = metsrw.FSEntry(
            path=self.full_path, file_uuid=str(self.uuid), use=AIP_PACKAGE_TYPE,
            type=AIP_PACKAGE_TYPE, transform_files=transform_files,
            mets_div_type=package_subtype)
        mets_fs_entry.add_premis_object(premis_object.serialize())
        for event in premis_events:
            mets_fs_entry.add_premis_event(event.serialize())
        for agent in premis_agents:
            mets_fs_entry.add_premis_agent(agent.serialize())
        pointer_file.append_file(mets_fs_entry)
        # 3. Validate the pointer file
        if validate:
            is_valid, report = metsrw.validate(
                pointer_file.serialize(), schematron=metsrw.AM_PNTR_SCT_PATH)
            if is_valid:
                LOGGER.info('Pointer file constructed for %s is valid.', self.uuid)
            else:
                LOGGER.warning('Pointer file constructed for %s is not valid.\n%s',
                            self.uuid, metsrw.report_string(report))
        return pointer_file

    def _create_aip_premis_object(self,
                                  message_digest_algorithm,
                                  message_digest,
                                  archive_tool,
                                  compression_program_version,
                                  premis_relationships=None):
        """Return a <premis:object> element for this package's (AIP's) pointer
        file.
        :param str message_digest_algorithm: name of the algorithm used to generate
            ``message_digest``.
        :param str message_digest: hex string checksum for the
            packaged/compressed AIP.
        :param str archive_tool: name of the tool (program) used to compress
            the AIP, e.g., '7-Zip'.
        :param str compression_program_version: version of ``archive_tool``
            used.
        :returns: <premis:object> as a tuple.
        """
        # PRONOM ID and PRONOM name for each file extension
        pronom_conversion = {
            '.7z': {'puid': 'fmt/484', 'name': '7Zip format'},
            '.bz2': {'puid': 'x-fmt/268', 'name': 'BZIP2 Compressed Archive'},
        }
        __, extension = os.path.splitext(self.current_path)
        now = timezone.now().strftime("%Y-%m-%dT%H:%M:%S")  # YYYY-MM-DDTHH:MM:SS
        premis_relationships = premis_relationships or []
        return metsrw.PREMISObject(
            xsi_type='premis:file',
            identifier_value=self.uuid,
            message_digest_algorithm=message_digest_algorithm,
            message_digest=message_digest,
            size=str(self.size),
            format_name=pronom_conversion[extension]['name'],
            format_registry_key=pronom_conversion[extension]['puid'],
            creating_application_name=archive_tool,
            creating_application_version=compression_program_version,
            date_created_by_application=now,
            relationships=premis_relationships)

    def create_replicas(self):
        """Create replicas of this AIP in any replicator locations.

        Note: in a future iteration, this should be done asynchronously by put
        requests to replicate this package on the "Package Replication Queue";
        workers will read from this queue and replicate the package to
        different locations asynchronously, e.g.,::

            >>> job = {'package': self.uuid, 'location': replicator_loc.uuid}
            >>> RMQ_CHANNEL.basic_publish(
                exchange='',
                routing_key=PACKAGE_REPLICATION_QUEUE,
                body=json.dumps(job).encode('utf8'),
                properties=pika.BasicProperties(
                    delivery_mode = 2,  # make message persistent
                )
            )
        """
        replicator_locs = self.current_location.replicators.all()
        for replicator_loc in replicator_locs:
            self.replicate(replicator_loc.uuid)

    def extract_file(self, relative_path='', extract_path=None):
        """Attempts to extract this package.

        If `relative_path` is provided, will extract only that file.  Otherwise,
        will extract entire package.
        If `extract_path` is provided, will extract there, otherwise to a temp
        directory in the SS internal location.
        If extracting the whole package, will set local_path to the extracted path.
        Fetches the file from remote storage before extracting, if necessary.

        Returns path to the extracted file and a temp dir that needs to be
        deleted.
        """
        ss_internal = Location.active.get(purpose=Location.STORAGE_SERVICE_INTERNAL)
        full_path = self.fetch_local_path()

        if extract_path is None:
            extract_path = tempfile.mkdtemp(dir=ss_internal.full_path)

        # The basename is the base directory containing a package
        # like an AIP inside the compressed file.
        try:
            basename = self.get_base_directory()
        except subprocess.CalledProcessError:
            raise StorageException(_('Error determining basename during extraction'))

        if relative_path:
            output_path = os.path.join(extract_path, relative_path)
        else:
            output_path = os.path.join(extract_path, basename)

        if self.is_compressed:
            # The command used to extract the compressed file at
            # full_path was, previously, universally::
            #
            #     $ unar -force-overwrite -o extract_path full_path
            #
            # The problem with this command is that unar treats __MACOSX .rsrc
            # ("resource fork") files differently than 7z and tar do. 7z and
            # tar convert these .rsrc files to ._-prefixed files. Similar
            # behaviour with unar can be achieved by passing `-k hidden`.
            # However, while a command like::
            #
            #     $ unar -force-overwrite -k hidden -o extract_path full_path
            #
            # preserves the .rsrc MACOSX files as ._-prefixed files, it does so
            # differently than 7z/tar do: the resulting .-prefixed files have
            # different sizes than those created via unar. This makes
            # ``bag.validate`` choke.
            if self.full_pointer_file_path:
                compression = utils.get_compression(self.full_pointer_file_path)
            else:
                compression = None  # no pointer file :. command will be unar
            command = _get_decompr_cmd(compression, extract_path, full_path)
            if relative_path:
                command.append(relative_path)
            LOGGER.info('Extracting file with: %s to %s', command, output_path)
            rc = subprocess.check_output(command)
            if 'No files extracted' in rc:
                raise StorageException(_('Extraction error'))
        else:
            if relative_path:
                # copy only one file out of aip
                head, tail = os.path.split(full_path)
                src = os.path.join(head, relative_path)
                os.mkdir(os.path.join(extract_path, basename))
                shutil.copy(src, output_path)
            else:
                src = full_path
                shutil.copytree(full_path, output_path)

            LOGGER.info('Copying from: %s to %s', src, output_path)

        if not relative_path:
            self.local_path_location = ss_internal
            self.local_path = output_path
        return (output_path, extract_path)

    def compress_package(self, algorithm, extract_path=None):
        """
        Produces a compressed copy of the package.

        :param algorithm: Compression algorithm to use. Should be one of
            :const:`utils.COMPRESSION_ALGORITHMS`
        :param str extract_path: Path to compress to. If not provided, will
            compress to a temp directory in the SS internal location.
        :return: Tuple with (path to the compressed file, parent directory of
            compressed file)  Given that compressed packages are likely to
            be large, this should generally be deleted after use if a temporary
            directory was used.
        """
        LOGGER.debug('in package.py::compress_package')

        if extract_path is None:
            ss_internal = Location.active.get(purpose=Location.STORAGE_SERVICE_INTERNAL)
            extract_path = tempfile.mkdtemp(dir=ss_internal.full_path)
        if algorithm not in utils.COMPRESSION_ALGORITHMS:
            raise ValueError(_('Algorithm %(algorithm)s not in %(algorithms)s') % {'algorithm': algorithm, 'algorithms': utils.COMPRESSION_ALGORITHMS})

        full_path = self.fetch_local_path()

        if os.path.isfile(full_path):
            basename = os.path.splitext(os.path.basename(full_path))[0]
        else:
            basename = os.path.basename(full_path)

        if algorithm in (utils.COMPRESSION_TAR, utils.COMPRESSION_TAR_BZIP2):
            compressed_filename = os.path.join(extract_path, basename + '.tar')
            relative_path = os.path.dirname(full_path)
            algo = ''
            if algorithm == utils.COMPRESSION_TAR_BZIP2:
                algo = '-j'  # Compress with bzip2
                compressed_filename += '.bz2'
            command = [
                'tar', 'c',  # Create tar
                algo,  # Optional compression flag
                '-C', relative_path,  # Work in this directory
                '-f', compressed_filename,  # Output file
                os.path.basename(full_path),   # Relative path to source files
            ]
        elif algorithm in (utils.COMPRESSION_7Z_BZIP, utils.COMPRESSION_7Z_LZMA):
            compressed_filename = os.path.join(extract_path, basename + '.7z')
            if algorithm == utils.COMPRESSION_7Z_BZIP:
                algo = 'bzip2'
            elif algorithm == utils.COMPRESSION_7Z_LZMA:
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
            raise NotImplementedError(_('Algorithm %(algorithm)s not implemented') % {'algorithm': algorithm})

        LOGGER.info('Compressing package with: %s to %s', command, compressed_filename)
        rc = subprocess.call(command)
        LOGGER.debug('Compress package RC: %s', rc)

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
            raise StorageException(_('No METS found at location: %(path)s') % {'path': mets_path})

        doc = etree.parse(mets_path)

        namespaces = {'m': utils.NSMAP['mets'],
                      'p': utils.NSMAP['premis']}
        mets = doc.xpath('/m:mets', namespaces=namespaces)
        if not mets:
            raise StorageException(_("<mets> element not found in METS file!"))
        else:
            mets = mets[0]

        try:
            transfer_uuid = mets.attrib['OBJID']
        except KeyError:
            raise StorageException(_("<mets> element did not have an OBJID attribute!"))

        header = doc.find('m:metsHdr', namespaces=namespaces)
        if header is None:
            raise StorageException(_("<metsHdr> element not found in METS file!"))

        try:
            creation_date = header.attrib['CREATEDATE']
        except KeyError:
            raise StorageException(_("<metsHdr> element did not have a CREATEDATE attribute!"))

        accession_id = header.findtext('./m:altRecordID[@TYPE="Accession number"]', namespaces=namespaces) or ''

        agent = header.xpath('./m:agent[@ROLE="CREATOR"][@TYPE="OTHER"][@OTHERTYPE="SOFTWARE"]/m:note[.="Archivematica dashboard UUID"]/../m:name',
                             namespaces=namespaces)
        if not agent:
            raise StorageException(_("No <agent> element found!"))
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
            File.objects.update_or_create(source_id=f['file_uuid'],
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
            package=self,
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
            return (None, [], _("Unable to scan; package is not a bag (AIP or AIC)"), None)

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
                return (None, [], _('Error extracting file'), None)
        else:
            path = self.fetch_local_path()
            temp_dir = None

        bag = bagit.Bag(path)
        try:
            success = bag.validate(processes=settings.BAG_VALIDATION_NO_PROCESSES)
            failures = []
            message = ""
        except bagit.BagValidationError as failure:
            LOGGER.error('bagit.BagValidationError on %s:\n%s', path, failure.message)
            try:
                LOGGER.debug(subprocess.check_output(
                    ['tree', '-a', '--du', path]))
            except (OSError, ValueError, subprocess.CalledProcessError):
                pass
            success = False
            failures = failure.details
            message = failure.message

        if temp_dir and delete_after and (self.local_path_location != self.current_location or self.local_path != self.full_path):
            shutil.rmtree(temp_dir)

        return (success, failures, message, None)

    def get_fixity_check_report_send_signals(self, force_local=False,
                                             delete_after=True):
        """Perform a fixity check on this package by calling ``check_fixity``,
        then also send Django signals so the check is recorded in the database,
        and return a JSON report of the fixity check attempt.
        """

        # Do the fixity check
        success, failures, message, timestamp = self.check_fixity(
            force_local=force_local)

        # Build the response (to be a JSON object)
        response = {
            "success": success,
            "message": message,
            "failures": {
                "files": {
                    "missing": [],
                    "changed": [],
                    "untracked": [],
                }
            },
            "timestamp": timestamp,
        }
        for failure in failures:
            if isinstance(failure, bagit.FileMissing):
                info = {
                    "path": failure.path,
                    "message": str(failure)
                }
                response["failures"]["files"]["missing"].append(info)
            if isinstance(failure, bagit.ChecksumMismatch):
                info = {
                    "path": failure.path,
                    "expected": failure.expected,
                    "actual": failure.found,
                    "hash_type": failure.algorithm,
                    "message": str(failure),
                }
                response["failures"]["files"]["changed"].append(info)
            if isinstance(failure, bagit.UnexpectedFile):
                info = {
                    "path": failure.path,
                    "message": str(failure)
                }
                response["failures"]["files"]["untracked"].append(info)
        report = json.dumps(response)

        # Trigger the signals (so ``FixityLog`` instances are created)
        if success is False:
            signals.failed_fixity_check.send(sender=self,
                uuid=self.uuid, location=self.full_path,
                report=report)
        elif success is None:
            signals.fixity_check_not_run.send(sender=self,
                uuid=self.uuid, location=self.full_path,
                report=report)
        elif success is True:
            signals.successful_fixity_check.send(sender=self,
                uuid=self.uuid, location=self.full_path,
                report=report)
        return report, response

    def delete_from_storage(self):
        """ Deletes the package from filesystem and updates metadata.
        Returns (True, None) on success, and (False, error_msg) on failure.
        """
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
                LOGGER.info("Error deleting pointer file %s for package %s",
                            pointer_path, self.uuid, exc_info=True)
            utils.removedirs(os.path.dirname(self.pointer_file_path),
                             base=self.pointer_file_location.full_path)

        self.status = self.DELETED
        self.save()
        return True, error

    # REINGEST

    def start_reingest(self, pipeline, reingest_type, processing_config='default'):
        """
        Copies this package to `pipeline` for reingest.

        Fetches the AIP from storage, extracts and runs fixity on it to verify integrity.
        If reingest_type is METADATA_ONLY, sends the METS and all files in the metadata directory.
        If reingest_type is OBJECTS, sends METS, all files in metadata directory and all objects, preservation and original.
        If reingest_type is FULL, we do like in OBJECTS but sending the package to the transfer source location.
        Calls Archivematica endpoint /api/ingest/reingest/ to start reingest.

        :param pipeline: Pipeline object to send reingested AIP to.
        :param reingest_type: Type of reingest to start, one of REINGEST_CHOICES.
        :return: Dict with keys 'error', 'status_code' and 'message'
        """
        if self.package_type not in Package.PACKAGE_TYPE_CAN_REINGEST:
            return {'error': True, 'status_code': 405, 'message': 'Package with type {} cannot be re-ingested.'.format(self.get_package_type_display())}

        # Check and set reingest pipeline
        if self.misc_attributes.get('reingest_pipeline', None):
            return {
                'error': True,
                'status_code': 409,
                'message': _('This AIP is already being reingested on {pipeline}') % {'pipeline': self.misc_attributes['reingest_pipeline']},
            }
        self.misc_attributes.update({'reingest_pipeline': pipeline.uuid})

        # Fetch and extract if needed
        if self.is_compressed:
            local_path, temp_dir = self.extract_file()
            LOGGER.debug('Reingest: extracted to %s', local_path)
        else:
            # Append / to uncompressed AIPS so we send the contents of the dir
            # not the dir itself inside a dir of the same name
            local_path = os.path.join(self.fetch_local_path(), '')
            temp_dir = ''
            LOGGER.debug('Reingest: uncompressed at %s', local_path)

        # Run fixity
        # Fixity will fetch & extract package if needed
        success, ___, error_msg, ___ = self.check_fixity(delete_after=False)
        LOGGER.debug('Reingest: Fixity response: %s, %s', success, error_msg)
        if not success:
            return {'error': True, 'status_code': 500, 'message': error_msg}

        # Make list of folders to move
        current_location = self.local_path_location or self.current_location
        relative_path = local_path.replace(current_location.full_path, '', 1).lstrip('/')
        reingest_files = [
            os.path.join(relative_path, 'data', 'METS.' + self.uuid + '.xml')
        ]
        if reingest_type == self.FULL:
            # All the things!
            reingest_files = [relative_path]
        elif reingest_type == self.OBJECTS:
            # All in objects except submissionDocumentation dir
            for f in os.listdir(os.path.join(local_path, 'data', 'objects')):
                if f in ('submissionDocumentation',):
                    continue
                abs_path = os.path.join(local_path, 'data', 'objects', f)
                if os.path.isfile(abs_path):
                    reingest_files.append(os.path.join(relative_path, 'data', 'objects', f))
                elif os.path.isdir(abs_path):
                    # Dirs must be / terminated to make the move functions happy
                    reingest_files.append(os.path.join(relative_path, 'data', 'objects', f, ''))
        elif reingest_type == self.METADATA_ONLY:
            reingest_files.append(os.path.join(relative_path, 'data', 'objects', 'metadata', ''))

        # Fetch processing configuration, put it in the root of the package and
        # include the file in reingest_files.
        if reingest_type == self.FULL and processing_config != 'default':
            try:
                config = pipeline.get_processing_config(processing_config)
            except requests.exceptions.RequestException:
                LOGGER.error('Reingest: processing configuration %s could not be loaded', processing_config)
            else:
                config_path = os.path.join(local_path, 'processingMCP.xml')
                try:
                    # It's not expected to find an existing processingMCP.xml
                    # file in the original AIP, but we are using the w+ mode
                    # just in case.
                    with open(config_path, 'w+') as f:
                        f.write(config)
                    LOGGER.debug('Reingest: processing configuration %s written, location: %s', processing_config, config_path)
                except IOError:
                    LOGGER.exception('Reingest: processing configuration %s could not be written', processing_config)
                    raise

        LOGGER.info('Reingest: files: %s', reingest_files)

        # Copy to pipeline
        try:
            currently_processing = Location.active.filter(pipeline=pipeline).get(purpose=Location.CURRENTLY_PROCESSING)
        except (Location.DoesNotExist, Location.MultipleObjectsReturned):
            return {
                'error': True,
                'status_code': 412,
                'message': _('No currently processing Location is associated with pipeline %(uuid)s') % {'pipeline': pipeline.uuid},
            }
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
                package=self,
            )

        # Delete local copy of extraction
        if self.local_path != self.full_path:
            try:
                shutil.rmtree(local_path)
            except OSError:  # May have been moved not copied
                pass
        if temp_dir:
            shutil.rmtree(temp_dir)

        # Call reingest API
        reingest_target = 'transfer' if reingest_type == self.FULL else 'ingest'
        reingest_uuid = self.uuid
        try:
            resp = pipeline.reingest(relative_path, self.uuid, reingest_target)
        except requests.exceptions.RequestException as e:
            message = _('Error in approve reingest API. %(error)s') % {'error': e}
            LOGGER.exception('Error approving reingest in pipeline for package %s', self.uuid)
            return {'error': True, 'status_code': 502, 'message': message}
        else:
            reingest_uuid = resp.get('reingest_uuid')
        LOGGER.debug('Reingest UUID: %s', reingest_uuid)
        self.save()

        return {
            'error': False,
            'status_code': 202,
            'message': _('Package %(uuid)s sent to pipeline %(pipeline)s for re-ingest') % {'uuid': self.uuid, 'pipeline': pipeline},
            'reingest_uuid': reingest_uuid,
        }

    def finish_reingest(self,
                        origin_location, origin_path,
                        reingest_location, reingest_path):
        """Finish the re-ingest of this package by updating it in accordance
        with the reingested version at ``origin_location/path`` and place the
        final reingested package at ``reingest_location/path``. Steps:

        NOTE: it is important to understand that the directory at
        ``old_aip_internal_path`` is the representation of the AIP that will
        constitute the final, reingested AIP. This is the original AIP
        directory which is progressively modified in the course of this method
        call by making it more like the re-ingested AIP at
        ``reingest_location/path``.

        1. Fetch the reingested AIP from the origin_location.
        2. Replace this AIP's METS file with the reingested AIP's mets file.
        3. Copy the new (reingested) metadata directory over the old
           (current) one.
        4. Copies preservation derivatives from reingested AIP to current AIP.
           New files will be added, updated files will be overwritten.
        5. Recreate the bagit manifest.
        6. Compress the AIP according to what was selected during reingest in
           Archivematica.
        7. Store the AIP in the reingest_location.
        8. Update the pointer file.

        :param Location origin_location: Location the newly re-ingested AIP was
            procesed on.
        :param str origin_path: Path to newly re-ingested AIP in
            origin_location.
        :param Location reingest_location: Location to store the updated AIP in.
        :param str reingest_path: Path to store the updated AIP at.

        We are dealing with 3 Space/Location sets:
        1. origin_space/location:   where the reingested AIP is at the start
        2. reingest_space/location: where we want the reingested AIP to end up
        3. internal_space/location: location for processing copies of this
                                    package and the reingested one
        """
        self._validate_pipelines_for_reingest()
        origin_space = origin_location.space
        reingest_space = reingest_location.space
        internal_location = Location.objects.get(
            purpose=Location.STORAGE_SERVICE_INTERNAL)
        internal_space = internal_location.space
        # Take note of whether the (soon-to-be) old (i.e., current) version of
        # this AIP was compressed.
        was_compressed = self.is_compressed
        # Copy the current AIP to the Storage Service's internal location,
        # extracting it if needed. We keep track of ``extract_path_to_delete``
        # so we can delete it later. Note: ``old_aip_internal_path`` points to
        # a copy of this package in a SS-internal location.
        old_aip_internal_path, extract_path_to_delete = self.extract_file()

        # 1. Fetch (and extract) the reingested AIP (and its pointer file) from
        #    the origin_location and put them in the internal processing
        #    location. Move the newly re-ingested version of the AIP from the
        #    original location to the internal location for processing.
        rein_aip_internal_path = (
            self._move_reingested_aip_from_origin_to_internal(
                origin_space, origin_location, origin_path,
                internal_space, internal_location, reingest_path))
        # Take note of whether the new version of the AIP should be compressed.
        to_be_compressed = rein_aip_is_compressed = os.path.isfile(
            rein_aip_internal_path)
        # Extract reingested AIP, if needed
        if rein_aip_is_compressed:
            rein_aip_internal_path = _extract_rein_aip(
                internal_location, rein_aip_internal_path)
        # Copy the pointer file of the newly re-ingested package (AIP) to the
        # internal location. ``rein_pointer_path`` is the full path to the
        # pointer file in the internal location.
        rein_pointer_path = self._copy_rein_pointer_from_origin_to_internal(
            to_be_compressed, was_compressed,
            origin_space, origin_location, origin_path,
            internal_space, internal_location)

        # 2. Replace the old AIP's METS file with the reingested AIP's mets
        #    file.
        self._overwrite_old_mets_with_rein_mets(rein_aip_internal_path,
                                                old_aip_internal_path)

        # 3. Copy the reingested AIP's metadata/ directory over the old AIP's
        #    metadata' directory.
        _replace_old_metdata_with_reingested(rein_aip_internal_path,
                                             old_aip_internal_path)

        # 4. Copy preservation derivatives from the reingested AIP to the old
        #    AIP. Outdated preservation derivatives are deleted.
        #    ``removed_pres_der_paths`` is a list of paths (in the old AIP) of
        #    preservation derivatives that were deleted because they were made
        #    out-of-date by new derivatives in the newly re-ingested AIP.
        removed_pres_der_paths = (
            _replace_old_pres_ders_with_reingested(
                rein_aip_internal_path, old_aip_internal_path))

        # 5. Create a new bag from the AIP at ``old_aip_internal_path`` and
        #    validate it.
        _update_bag_payload_and_verify(old_aip_internal_path)

        # 6. Compress the re-ingested AIP (if necessary) and get the local path
        #    to it and to its parent directory. At this point ``updated_aip``
        #    points to the same location as ``old_aip`` but the new var name
        #    indicates the update via reingest.
        updated_aip_path, updated_aip_parent_path, compression = (
            self._compress_and_clean_for_reingest(
                to_be_compressed, was_compressed,
                rein_pointer_path, rein_aip_internal_path,
                extract_path_to_delete))
        self.size = _recalculate_size(updated_aip_path)

        # 7. Store the AIP in the reingest_location.
        self._move_rein_updated_to_final_dest(
            to_be_compressed, removed_pres_der_paths,
            internal_space, internal_location,
            updated_aip_parent_path, updated_aip_path,
            reingest_space, reingest_location, old_aip_internal_path)

        # 8. Update the pointer file.
        self._process_pointer_file_for_reingest(
            to_be_compressed, was_compressed, compression, updated_aip_path)
        self.save()
        shutil.rmtree(updated_aip_parent_path)  # Delete working files

    # ==========================================================================
    # Private methods for ``finish_reingest``
    # ==========================================================================

    def _validate_pipelines_for_reingest(self):
        """Confirm that this package's origin_pipeline matches the
        reingest_pipeline set during ``start_reingest``.
        """
        if self.origin_pipeline.uuid != self.misc_attributes.get(
                'reingest_pipeline'):
            LOGGER.info('Reingest: Received pipeline %s did not match expected'
                        ' pipeline %s', self.origin_pipeline.uuid,
                        self.misc_attributes.get('reingest_pipeline'))
            raise Exception(
                _('%(uuid)s did not match the pipeline this AIP was reingested'
                  ' on.') % {'uuid': self.origin_pipeline.uuid})
        self.misc_attributes.update({'reingest_pipeline': None})
        self.save()

    def _move_reingested_aip_from_origin_to_internal(
            self, origin_space, origin_location, origin_path, internal_space,
            internal_location, reingest_path):
        """Move the reingested AIP from its origin space/location to the
        Storage Service internal one for processing during the final stage of
        AIP reingest.
        """
        origin_space.move_to_storage_service(
            source_path=os.path.join(
                origin_location.relative_path,
                origin_path),
            destination_path=reingest_path,  # This should include Location.path
            destination_space=internal_space)
        internal_space.move_from_storage_service(
            source_path=reingest_path,  # This should include Location.path
            destination_path=os.path.join(
                internal_location.relative_path,
                reingest_path),
            package=self,
        )
        return os.path.join(internal_location.full_path, reingest_path)

    def _copy_rein_pointer_from_origin_to_internal(
            self, to_be_compressed, was_compressed, origin_space,
            origin_location, origin_path, internal_space, internal_location):
        """Copy the pointer file (if it exists) from the origin location (e.g.,
        currently processing) to the internal location and return the full path
        within the internal location to that pointer file.
        TODO: what do if LOCKSS?
        """
        rein_pointer_path = None
        if self.package_type in (Package.AIP, Package.AIC) and to_be_compressed:
            reingest_pointer_src = os.path.join(
                origin_location.relative_path,
                os.path.dirname(origin_path),
                'pointer.xml')
            # If reingesting a previously compressed AIP, make a temporary
            # "reingest" pointer (otherwise make a normal one)
            if was_compressed:
                reingest_pointer_name = 'pointer.{}.reingest.xml'.format(
                    self.uuid)
                reingest_pointer_dst = os.path.join(
                    internal_location.relative_path,
                    reingest_pointer_name)
                rein_pointer_path = os.path.join(
                    internal_location.full_path,
                    reingest_pointer_name)
            else:
                reingest_pointer_name = 'pointer.{}.xml'.format(self.uuid)
                uuid_path = utils.uuid_to_path(self.uuid)
                reingest_pointer_dst = os.path.join(
                    internal_location.relative_path,
                    uuid_path,
                    reingest_pointer_name)
                self.pointer_file_location = Location.active.get(
                    purpose=Location.STORAGE_SERVICE_INTERNAL)
                self.pointer_file_path = os.path.join(
                    uuid_path,
                    reingest_pointer_name)
                rein_pointer_path = os.path.join(
                    internal_location.full_path,
                    uuid_path,
                    reingest_pointer_name)
            origin_space.move_to_storage_service(
                reingest_pointer_src, reingest_pointer_name, internal_space)
            internal_space.move_from_storage_service(
                reingest_pointer_name, reingest_pointer_dst, package=None)
        return rein_pointer_path

    def _overwrite_old_mets_with_rein_mets(self,
                                           rein_aip_internal_path,
                                           old_aip_internal_path):
        """Overwrite this package's METS file with that of the reingested
        package.
        """
        mets_name = 'METS.{}.xml'.format(self.uuid)
        rein_aip_mets_path = os.path.join(
            rein_aip_internal_path, 'data', mets_name)
        old_aip_mets_path = os.path.join(
            old_aip_internal_path, 'data', mets_name)
        LOGGER.info('Replacing old AIP METS %s with reingested METS %s',
                    old_aip_mets_path, rein_aip_mets_path)
        os.rename(rein_aip_mets_path, old_aip_mets_path)

    def _compress_and_clean_for_reingest(
            self, to_be_compressed, was_compressed, rein_pointer_path,
            rein_aip_internal_path, extract_path_to_delete):
        """If this package (AIP) needs to be compressed, compress it. In either
        case, return the local path to this package and the path to its parent
        directory. And clean up some unused directories.
        """
        compression = None
        # Compress if necessary
        if to_be_compressed:
            compression = utils.get_compression(rein_pointer_path)
            # If updating, rather than creating a new pointer file, delete this
            # pointer file.
            # TODO: this is maybe not a good idea and might be what is messing
            # with encrypted re-ingest
            if was_compressed:
                os.remove(rein_pointer_path)
            LOGGER.info('Reingest: compressing with %s', compression)
            # FIXME Do we need compression output for event?
            updated_aip_path, updated_aip_parent_path = (
                self.compress_package(compression))
            # Delete working files
            shutil.rmtree(rein_aip_internal_path)
            shutil.rmtree(extract_path_to_delete)
        else:
            updated_aip_path = self.fetch_local_path()
            updated_aip_parent_path = os.path.dirname(updated_aip_path)
        return updated_aip_path, updated_aip_parent_path, compression

    def _move_rein_updated_to_final_dest(
            self, to_be_compressed, removed_pres_der_paths,
            internal_space, internal_location,
            updated_aip_parent_path, updated_aip_path,
            reingest_space, reingest_location, old_aip_internal_path):
        """Move the AIP updated via re-ingest from the internal space (where it
        has been processed) to its final destination, i.e., the reingest space.
        """
        updated_aip_src_path = updated_aip_path.replace(
            internal_location.space.path, '', 1).lstrip('/')
        uuid_path = utils.uuid_to_path(self.uuid)
        dest_path = updated_aip_path.replace(
            updated_aip_parent_path, '', 1).lstrip('/')
        dest_path = os.path.join(uuid_path, dest_path)
        if not to_be_compressed:
            # This allows uncompressed AIP to be rsynced properly
            updated_aip_src_path = updated_aip_src_path + '/'
            # TODO: I don't understand why the following is needed; why are
            # there any preservation derivatives in the reingest location at
            # all?
            # Delete superseded preservation derivatives from final storage
            # Otherwise, when the uncompressed AIP is stored, the old
            # preservations derivatives still exist.
            # This doesn't happen with packaged AIPs because they're a single file
            for del_path in removed_pres_der_paths:
                # FIXME This may have problems in Spaces where
                # location.full_path isn't what we want
                del_path = del_path.replace(
                    old_aip_internal_path,
                    os.path.join(reingest_location.full_path, dest_path))
                LOGGER.info('Deleting %s', del_path)
                reingest_space.delete_path(del_path)
        internal_space.move_to_storage_service(
            source_path=updated_aip_src_path,
            destination_path=dest_path,  # This should include Location.path
            destination_space=reingest_space)
        reingest_space.move_from_storage_service(
            source_path=dest_path,  # This should include Location.path
            destination_path=os.path.join(reingest_location.relative_path,
                                          dest_path),
            package=self)
        # Delete old copy of AIP if different
        if (self.current_path != dest_path or
                self.current_location != reingest_location):
            LOGGER.info('Old copy of reingested AIP is at a different location.'
                        ' Deleting %s', self.full_path)
            self.current_location.space.delete_path(self.full_path)
        self.current_location = reingest_location
        self.current_path = dest_path

    def _process_pointer_file_for_reingest(
            self, to_be_compressed, was_compressed, compression,
            updated_aip_path):
        """Process the pointer file at the end of a package (AIP) reingest:
        Update the pointer file if one is needed, otherwise remove any
        no-longer-needed pointer file.
        """
        if to_be_compressed:
            # Update pointer file
            root = etree.parse(self.full_pointer_file_path)
            # Add compression event (if compressed)
            amdsec = root.find('mets:amdSec', namespaces=utils.NSMAP)
            if compression in (utils.COMPRESSION_7Z_BZIP,
                               utils.COMPRESSION_7Z_LZMA):
                try:
                    version = [x for x in
                               subprocess.check_output('7z').splitlines() if
                               'Version' in x][0]
                    event_detail = 'program="7z"; version="{}"'.format(version)
                except (subprocess.CalledProcessError, Exception):
                    event_detail = 'program="7z"'
            elif compression in (utils.COMPRESSION_TAR_BZIP2,
                                 utils.COMPRESSION_TAR):
                try:
                    version = subprocess.check_output(
                        ['tar', '--version']).splitlines()[0]
                    event_detail = 'program="tar"; version="{}"'.format(version)
                except (subprocess.CalledProcessError, Exception):
                    event_detail = 'program="tar"'
            else:
                LOGGER.warning('Unknown compression algorithm, cannot correctly'
                               ' update pointer file')
                event_detail = _('Unknown compression')
            utils.mets_add_event(
                amdsec,
                'compression',
                event_detail=event_detail,
                event_outcome_detail_note='',
            )
            self._update_pointer_file(
                compression, root=root, path=updated_aip_path)
        elif was_compressed:
            # AIP used to be compressed, but is no longer so delete pointer file
            os.remove(self.full_pointer_file_path)
            self.pointer_file_location = None
            self.pointer_file_path = None

    # ==========================================================================
    # END Private methods for ``finish_reingest``
    # ==========================================================================

    def _update_pointer_file(self, compression, root=None, path=None):
        """Update the AIP's pointer file at the end of re-ingest."""
        LOGGER.debug('Updating pointer file at %s', self.full_pointer_file_path)
        if not root:
            root = etree.parse(self.full_pointer_file_path)
        if not path:
            path = self.fetch_local_path()

        # Update FLocat to full path
        file_ = root.find(
            './/mets:fileGrp[@USE="Archival Information Package"]/mets:file',
            namespaces=utils.NSMAP)
        flocat = file_.find(
            'mets:FLocat[@OTHERLOCTYPE="SYSTEM"][@LOCTYPE="OTHER"]',
            namespaces=utils.NSMAP)
        flocat.set(utils.PREFIX_NS['xlink'] + 'href', self.full_path)

        # Update fixity checksum
        fixity_elem = root.find('.//premis:fixity', namespaces=utils.NSMAP)
        algorithm = fixity_elem.findtext('premis:messageDigestAlgorithm',
                                         namespaces=utils.NSMAP)
        try:
            checksum = utils.generate_checksum(path, algorithm)
        except ValueError:
            # If incorrectly parsed algorithm, default to sha512, since that is
            # what AM uses
            checksum = utils.generate_checksum(path, 'sha512')
        fixity_elem.find('premis:messageDigest',
                         namespaces=utils.NSMAP).text = checksum.hexdigest()

        # Update size
        root.find('.//premis:size', namespaces=utils.NSMAP).text = str(
            os.path.getsize(path))

        # Set compression-related data
        transform_order = 1
        decr_transform_file = file_.find(
            './/mets:transformFile[@TRANSFORMTYPE="decryption"]',
            namespaces=utils.NSMAP)
        if decr_transform_file is not None:
            transform_order = 2  # encryption is a prior transformation

        transform_file = []
        if compression in (utils.COMPRESSION_7Z_BZIP,
                           utils.COMPRESSION_7Z_LZMA):
            if compression == utils.COMPRESSION_7Z_BZIP:
                algo = 'bzip2'
            elif compression == utils.COMPRESSION_7Z_LZMA:
                algo = 'lzma'
            transform_file.append(
                etree.Element(utils.PREFIX_NS['mets'] + "transformFile",
                              TRANSFORMORDER=str(transform_order),
                              TRANSFORMTYPE='decompression',
                              TRANSFORMALGORITHM=algo)
            )
            version = [x for x in subprocess.check_output('7z').splitlines() if
                       'Version' in x][0]
            format_info = {
                'name': '7Zip format',
                'registry_name': 'PRONOM',
                'registry_key': 'fmt/484',
                'program_name': '7-Zip',
                'program_version': version
            }

        elif compression in (utils.COMPRESSION_TAR_BZIP2,
                             utils.COMPRESSION_TAR):
            if compression == utils.COMPRESSION_TAR_BZIP2:
                transform_file.append(
                    etree.Element(utils.PREFIX_NS['mets'] + "transformFile",
                                  TRANSFORMORDER=str(transform_order),
                                  TRANSFORMTYPE='decompression',
                                  TRANSFORMALGORITHM='bzip2')
                )
                transform_order += 1

            transform_file.append(
                etree.Element(utils.PREFIX_NS['mets'] + "transformFile",
                              TRANSFORMORDER=str(transform_order),
                              TRANSFORMTYPE='decompression',
                              TRANSFORMALGORITHM='tar')
            )
            version = subprocess.check_output(
                ['tar', '--version']).splitlines()[0]
            format_info = {
                'name': 'BZIP2 Compressed Archive',
                'registry_name': 'PRONOM',
                'registry_key': 'x-fmt/268',
                'program_name': 'tar',
                'program_version': version,
            }

        # Set new format info
        fmt = root.find('.//premis:format', namespaces=utils.NSMAP)
        fmt.clear()
        fd = etree.SubElement(
            fmt, utils.PREFIX_NS['premis'] + 'formatDesignation')
        etree.SubElement(
            fd, utils.PREFIX_NS['premis'] + 'formatName').text = (
                format_info.get('name'))
        etree.SubElement(
            fd, utils.PREFIX_NS['premis'] + 'formatVersion').text = (
                format_info.get('version'))
        fr = etree.SubElement(fmt, utils.PREFIX_NS['premis'] + 'formatRegistry')
        etree.SubElement(
            fr, utils.PREFIX_NS['premis'] + 'formatRegistryName').text = (
                format_info.get('registry_name'))
        etree.SubElement(
            fr, utils.PREFIX_NS['premis'] + 'formatRegistryKey').text = (
                format_info.get('registry_key'))

        # Creating application info
        now = utils.mets_file_now()
        app = root.find('.//premis:creatingApplication', namespaces=utils.NSMAP)
        app.clear()
        etree.SubElement(
            app, utils.PREFIX_NS['premis'] + 'creatingApplicationName').text = (
                format_info.get('program_name'))
        etree.SubElement(
            app,
            utils.PREFIX_NS['premis'] + 'creatingApplicationVersion').text = (
                format_info.get('program_version'))
        etree.SubElement(
            app,
            utils.PREFIX_NS['premis'] + 'dateCreatedByApplication').text = str(
                now)

        # Remove existing decompression transformFiles
        to_delete = file_.findall(
            './/mets:transformFile[@TRANSFORMTYPE="decompression"]',
            namespaces=utils.NSMAP)
        for elem in to_delete:
            file_.remove(elem)
        # Add new ones
        for elem in transform_file:
            file_.append(elem)

        # Update compositionLevel
        root.find(
            './/premis:compositionLevel', namespaces=utils.NSMAP).text = str(
                len(file_.findall('mets:transformFile', namespaces=utils.NSMAP)))

        # Write out pointer file again
        with open(self.full_pointer_file_path, 'w') as f:
            f.write(etree.tostring(root,
                                   pretty_print=True,
                                   xml_declaration=True,
                                   encoding='utf-8'))

    # SWORD-related methods
    def has_been_submitted_for_processing(self):
        return 'deposit_completion_time' in self.misc_attributes


def _get_decompr_cmd(compression, extract_path, full_path):
    """Returns a decompression command (as a list), given ``compression``
    (one of ``COMPRESSION_ALGORITHMS``), the destination path
    ``extract_path`` and the path of the archive ``full_path``.
    """
    if compression in (utils.COMPRESSION_7Z_BZIP, utils.COMPRESSION_7Z_LZMA):
        return ['7z', 'x', '-bd', '-y', '-o{0}'.format(extract_path),
                full_path]
    elif compression == utils.COMPRESSION_TAR_BZIP2:
        return ['/bin/tar', 'xvjf', full_path, '-C', extract_path]
    return ['unar', '-force-overwrite', '-o', extract_path, full_path]


def _extract_rein_aip(internal_location, rein_aip_internal_path):
    """Extract the reingested AIP (package) at ``rein_aip_internal_path`` and
    return the path to the resulting directory.
    """
    if os.path.isfile(rein_aip_internal_path):
        # TODO modify extract_file and get_base_directory to handle
        # reingest paths?  Update self.local_path sooner?
        # Extract
        command = [
            'unar',
            '-force-overwrite',
            '-o',
            internal_location.full_path,
            rein_aip_internal_path
        ]
        LOGGER.info('Extracting reingested AIP with: %s', command)
        rc = subprocess.call(command)
        LOGGER.debug('Extract file RC: %s', rc)
        # Get output path
        command = ['lsar', '-ja', rein_aip_internal_path]
        try:
            output = subprocess.check_output(command)
            j = json.loads(output)
            bname = sorted([d['XADFileName'] for d in j['lsarContents'] if
                            d.get('XADIsDirectory', False)], key=len)[0]
        except (subprocess.CalledProcessError, ValueError):
            bname = os.path.splitext(
                os.path.basename(rein_aip_internal_path))[0]
            LOGGER.warning('Unable to parse base directory from package,'
                           ' using basename %s', bname)
        else:
            LOGGER.debug('Reingested AIP extracted, removing original package %s',
                         rein_aip_internal_path)
            os.remove(rein_aip_internal_path)
            rein_aip_internal_path = os.path.join(internal_location.full_path, bname)
    LOGGER.debug('Reingested AIP full path: %s', rein_aip_internal_path)
    return rein_aip_internal_path


def _replace_old_pres_ders_with_reingested(rein_aip_internal_path,
                                           old_aip_internal_path):
    """Replace preservation derivatives in this package (at
    ``old_aip_internal_path``) with those from the reingested AIP at internal
    path ``internal_path``. Return a list of paths (in the old AIP, in the
    internal processing space) of the old preservation derivatives that were
    deleted (i.e., replaced) from this AIP.
    """
    rein_aip_objects_dir = os.path.join(
        rein_aip_internal_path, 'data', 'objects')
    old_aip_objects_dir = os.path.join(
        old_aip_internal_path, 'data', 'objects')
    preservation_regex = r'(.+)-\w{8}-\w{4}-\w{4}-\w{4}-\w{12}(.*)'
    removed_pres_der_paths = []  # a return value
    # Walk through all files in the internally stored reingested AIP
    for rein_aip_dirpath, ___, rein_aip_filenames in os.walk(
            rein_aip_objects_dir):
        for rein_aip_filename in rein_aip_filenames:
            match = re.match(preservation_regex, rein_aip_filename)
            # This file is a preservation derivative, so copy it
            # to this package's objects/ directory and delete any
            # same-named preservation derivative in this package's objects/
            # directory.
            if match:
                rein_aip_pres_der_path = os.path.join(
                    rein_aip_dirpath, rein_aip_filename)
                old_aip_pres_der_path = (
                    rein_aip_pres_der_path.replace(
                        rein_aip_objects_dir,
                        old_aip_objects_dir))
                # Check for another preservation derivative and delete
                old_aip_pres_der_dir_path = os.path.dirname(
                    old_aip_pres_der_path)
                dupe_preservation_regex = (
                    match.group(1) +
                    r'-\w{8}-\w{4}-\w{4}-\w{4}-\w{12}' +
                    match.group(2))
                for old_aip_filename in os.listdir(old_aip_pres_der_dir_path):
                    # Don't delete if the 'duplicate' is the original
                    if rein_aip_filename == old_aip_filename:
                        continue
                    if re.match(dupe_preservation_regex, old_aip_filename):
                        del_path = os.path.join(old_aip_pres_der_dir_path,
                                                old_aip_filename)
                        LOGGER.info('Deleting %s', del_path)
                        os.remove(del_path)
                        # Save these paths to delete from uncompressed AIP later
                        removed_pres_der_paths.append(del_path)
                # Copy new preservation derivative
                LOGGER.info('Moving %s to %s', rein_aip_pres_der_path,
                            old_aip_pres_der_path)
                shutil.copy2(rein_aip_pres_der_path, old_aip_pres_der_path)
    return removed_pres_der_paths


def _update_bag_payload_and_verify(old_aip_internal_path):
    """Create a new bag from the AIP at ``old_aip_internal_path`` and validate it."""
    bag = bagit.Bag(old_aip_internal_path)
    bag.save(manifests=True)
    # Workaround for bug
    # https://github.com/LibraryOfCongress/bagit-python/pull/63
    bag = bagit.Bag(old_aip_internal_path)
    # Raises exception in case of problem
    bag.validate(processes=settings.BAG_VALIDATION_NO_PROCESSES)


def _replace_old_metdata_with_reingested(rein_aip_internal_path,
                                         old_aip_internal_path):
    """Replace this package's data/objects/metadata/ dir with that of the
    reingested package.
    """
    internal_metadata_dir = os.path.join(
        rein_aip_internal_path, 'data', 'objects', 'metadata')
    this_metadata_dir = os.path.join(
        old_aip_internal_path, 'data', 'objects', 'metadata')
    LOGGER.info(
        'Replacing original metadata directory %s with reingested metadata'
        ' directory %s', this_metadata_dir, internal_metadata_dir)
    if os.path.isdir(internal_metadata_dir):
        distutils.dir_util.copy_tree(
            internal_metadata_dir,
            this_metadata_dir)


def _recalculate_size(rein_aip_internal_path):
    """Recalculate size: it may have changed because of changed preservation
    derivatives or because of a metadata-only reingest. If the AIP is a
    directory, then calculate the size recursively.
    """
    if os.path.isdir(rein_aip_internal_path):
        size = 0
        for dirpath, ___, filenames in os.walk(rein_aip_internal_path):
            for filename in filenames:
                file_path = os.path.join(dirpath, filename)
                size += os.path.getsize(file_path)
    else:
        size = os.path.getsize(rein_aip_internal_path)
    return size


def _find_compression_event(events):
    return _find_event(events, 'compression')


def _find_encryption_event(events):
    return _find_event(events, 'encryption')


def _find_event(events, event_type):
    try:
        return [evt for evt in events if evt.event_type == event_type][0]
    except IndexError:
        return None


def _replicate_package_mdl_inst(package_mdl):
    """Create a new Django ``Package`` instance that is exactly like
    ``package_mdl`` but which has a new primary key and UUID, and references
    ``package_mdl`` as its ``replicated_package``.
    """
    package_uuid = package_mdl.uuid
    replica_package = package_mdl
    # After setting ``pk`` to ``None``, ``save()`` will create a new instance/db row
    replica_package.pk = None
    replica_package.uuid = None  # will trigger new UUID generation
    replica_package.replicated_package_id = package_uuid
    replica_package.save()
    return replica_package


def _get_checksum_report(master_checksum, master_uuid, replica_checksum,
                         replica_uuid, algorithm):
    success = replica_checksum == master_checksum
    if success:
        message = ('Master AIP {m_uuid} and replica AIP {r_uuid} both'
                   ' have checksum {checksum} when using algorithm'
                   ' {algorithm}.'.format(
                       m_uuid=master_uuid, r_uuid=replica_uuid,
                       checksum=master_checksum, algorithm=algorithm))
    else:
        message = ('Using algorithm {algorithm}, master AIP {m_uuid}'
                   ' has checksum {m_checksum} while replica AIP'
                   ' {r_uuid} has checksum {r_checksum}.'.format(
                       m_uuid=master_uuid, r_uuid=replica_uuid,
                       m_checksum=master_checksum,
                       r_checksum=replica_checksum, algorithm=algorithm))
    return {'success': success, 'message': message}


def _get_replication_derivation_relationship(related_aip_uuid,
                                             replication_event_uuid,
                                             premis_version=None):
    """Return a PREMIS relationship of type derivation relating an implicit
    PREMIS object (an AIP) to some to related AIP (with UUID
    ``related_aip_uuid``) via a replication event with UUID
    ``replication_event_uuid``. Note the complication wherein PREMIS v. 2.2
    uses 'Identification' where PREMIS v. 3.0 uses 'Identifier'.
    """
    if not premis_version:
        premis_version = metsrw.PREMIS_META['version']
    related_object_identifier = {'2.2': 'related_object_identification'}.get(
        premis_version, 'related_object_identifier')
    related_event_identifier = {'2.2': 'related_event_identification'}.get(
        premis_version, 'related_event_identifier')
    return (
        'relationship',
        ('relationship_type', 'derivation'),
        ('relationship_sub_type', ''),
        (related_object_identifier,
            ('related_object_identifier_type', 'UUID'),
            ('related_object_identifier_value', related_aip_uuid)),
        (related_event_identifier,
            ('related_event_identifier_type', 'UUID'),
            ('related_event_identifier_value', replication_event_uuid)))


def write_pointer_file(pointer_file, pointer_file_path):
    """Write the pointer file to disk. creating intermediate directories as
    necessary.
    :param metsrw.METSDocument pointer_file:
    :param str pointer_file_path:
    """
    pointer_dir_path = os.path.dirname(pointer_file_path)
    if not os.path.isdir(pointer_dir_path):
        os.makedirs(pointer_dir_path)
    pointer_file.write(pointer_file_path, pretty_print=True)
