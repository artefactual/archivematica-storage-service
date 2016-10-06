#
# -*- coding: utf-8 -*-

# Copyright (c) 2016 Ymagis SA, http://www.ymagis.com/
#
# This file is part of archivematica-storage-service.

# archivematica-storage-service is free software: you can redistribute it 
# and/or modify it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the License,
# or (at your option) any later version.
#
# archivematica-storage-service is distributed in the hope that it will be
# useful, but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with archivematica-storage-service.  If not, 
# see <http://www.gnu.org/licenses/>.
#
# @author Thomas Capricelli <capricelli@sylphide-consulting.com>
#


# Standard
import logging
import os
from base64 import b64encode
import requests

# Core Django, alphabetical
from django.db import models

# Third party dependencies, alphabetical
import bagit
from irods.exception import DataObjectDoesNotExist, CollectionDoesNotExist
from irods.session import iRODSSession

# This project, alphabetical
from common.utils import generate_checksum, dirsize

# This module, alphabetical
from . import StorageException
from location import Location

LOGGER = logging.getLogger(__name__)


class iRODS(models.Model):
    space = models.OneToOneField('Space', to_field='uuid')

    host = models.CharField(max_length=256, help_text=u"iRODS API server name or IP")
    port = models.PositiveIntegerField(help_text=u"port, default is 1247", default=1247)
    user = models.CharField(max_length=256, help_text=u"iRODS user")
    password = models.CharField(max_length=256, help_text=u"Corresponding password")
    zone = models.CharField(max_length=256, help_text=u"iRODS zone (e.g. tempZone)", default="tempZone")
    resource = models.CharField(max_length=256, help_text="iRODS resource used for storing objects")
    callback = models.CharField(u"Non-mandatory callback URL", max_length=512, help_text="If present a call will be made to this URL after a successful/finished move_from_storage_service() (data stored on the iRODS backend) with the destination name as argument.", blank=True)

    class Meta:
        verbose_name = "iRODS"
        app_label = 'locations'

    ALLOWED_LOCATION_PURPOSE = [
        Location.AIP_STORAGE,
        Location.DIP_STORAGE,
        Location.TRANSFER_SOURCE,
        Location.BACKLOG,
    ]
    CHUNK_SIZE = 1024*1024 # 1MB

    # map non-standard irods checksum names to standard ones (such as those used by hashlib.new)
    map_irods_checksum_type = {
        "sha2": "sha256"
    }

    def __init__(self, *args, **kwargs):
        super(iRODS, self).__init__(*args, **kwargs)
        self._session = None

    @property
    def session(self):
        if self._session is None:
            self._session = iRODSSession(
                host = str(self.host),
                port = str(self.port),
                user = str(self.user),
                password = str(self.password),
                zone = str(self.zone),
            )
        return self._session

    def irodspath(self, path):
        "Clean / normalize a path, taking zone into consideration"
	return str(os.path.normpath('/%s/%s'% ( self.zone, path)))

    def browse(self, path):
        """
        Returns information about files and folders (called "collections" in iRODS)

        See Space.browse for full documentation.

        Properties provided:
        'size': Size of the object
        'timestamp': Last modified timestamp of the object or directory
        """
        properties = {}
        coll = self.session.collections.get(self.irodspath(path))

        # List folders
        directories = [collection.name for collection in coll.subcollections]

        # List files
        objects = [obj.name for obj in coll.data_objects]
        entries = objects + directories

        # Metadata
        # TODO: if we add a field "object count", archivematica frontend will make use of it. See the "FS" plugin for an example.
        for obj in coll.data_objects:
            properties[obj.name] = {
                'size': obj.size,
                'timestamp': obj.modify_time.isoformat(),
            }
        return {
            'directories': sorted(directories, key=lambda s: s.lower()),
            'entries': sorted(entries, key=lambda s: s.lower()),
            'properties': properties,
        }

    def delete_path(self, path):
        fullpath = self.irodspath(path)
        try:
            # Object ?
            obj = self.session.data_objects.get(fullpath)
            obj.unlink(force=True)
        except DataObjectDoesNotExist:
            # Collection ??
            collection  = self.session.collections.get(fullpath)
            collection.remove(force=True)

    def check_checksum(self, obj, local_path):
        if not obj.checksum: return # nothing to check
        LOGGER.info("Checking iRODS checksum against local file %s" % local_path)

        # iRODS provides a checksum: check it
        checksum_type, checksum_value = obj.checksum.split(":")
        checksum_type = self.map_irods_checksum_type.get(checksum_type, checksum_type)
        checksum = generate_checksum(local_path, checksum_type=checksum_type)
        # irods encodes the checksum whith base64
        if checksum_value != b64encode(checksum.digest()):
            raise StorageException("Error while checking the checksum provided by iRODS")

    def _iget(self, irods_path, local_path):
        """
        Get a file from iRODS and store it locally.

        :param str irods_path: path in iRODS.
        :param str local_path: local destination file path.
        """
        fullpath = self.irodspath(irods_path)
        LOGGER.info("_iget() %s -> %s" % (fullpath, local_path))
        obj = self.session.data_objects.get(fullpath)
        # Stream it
        with open(local_path, "wb") as localfile:
            with obj.open('r+') as irodsobject:
                while True:
                    chunk = irodsobject.read(iRODS.CHUNK_SIZE)
                    if not chunk: break
                    localfile.write(chunk)

        self.check_checksum(obj, local_path)

    def _iput(self, local_path, irods_path):
        """
        Send a local file to iRODS.

        :param str local_path: local source file path.
        :param str irods_path: path in iRODS.
        """
        LOGGER.info("_iput() %s -> %s" % (local_path, irods_path))
        fullpath = self.irodspath(irods_path)
        obj = self.session.data_objects.create(fullpath, resource=str(self.resource))
        # Stream it
        with open(local_path, "r+") as localfile:
            with obj.open('w') as irodsobject:
                while True:
                    chunk = localfile.read(iRODS.CHUNK_SIZE)
                    if not chunk: break
                    irodsobject.write(chunk)

        # Fetch again the iRODS object and check the checksum if available
        obj = self.session.data_objects.get(fullpath)
        self.check_checksum(obj, local_path)

    def move_to_storage_service(self, src_path, dest_path, dest_space):
        """ Moves src_path to dest_space.staging_path/dest_path. """
        try:
            # First try it as a collection
            self._move_to_storage_service_dir(src_path, dest_path)
        except CollectionDoesNotExist:
            # Not a collection, try as an object
            self._iget(src_path, dest_path)

    def _move_to_storage_service_dir(self, src_path, dest_path):
        """
        Get recursively an iRODS collection
        """
        coll = self.session.collections.get(self.irodspath(src_path))
        os.mkdir(dest_path)

        # Copy objects
        for obj in coll.data_objects:
            self._iget(
                os.path.join(src_path, obj.name),
                os.path.join(dest_path, obj.name),
            )
        # Copy directories
        for collection in coll.subcollections:
            self._move_to_storage_service_dir(
                os.path.join(src_path, collection.name),
                os.path.join(dest_path, collection.name),
            )

    def mkdir(self, name):
        LOGGER.info("Creating irods directory (zone:%s) %s", self.zone, name)
        self.session.collections.create(self.irodspath(name))

    def mkdir_if_needed(self, name):
        """
        Ensure a collection/directory exists (think "mkdir -p")
        * create new collection only if needed / doesn't exist
        * work at any depth
        """
        parentname = os.path.dirname(os.path.normpath(name))
        # Recursively check parents. This would be surprising to reach '/',
        # but we still want a robust stop criteria.
        if parentname not in [u'/', '/', '']:
            self.mkdir_if_needed(parentname) # recursion
        try:
            coll = self.session.collections.get(self.irodspath(name))
        except CollectionDoesNotExist:
            self.mkdir(name)

    def move_from_storage_service(self, source_path, destination_path):
        """
        Called by Space parent, which is responsible for adding
        * self.space.staging_path to source_path
        * self.space.path to destination_path

        So we don't need to do it
        """

        source_path = os.path.normpath(source_path)
        destination_path = os.path.normpath(destination_path)

        if os.path.isdir(source_path):
            self.mkdir_if_needed(destination_path)
            for path, directories, files in os.walk(source_path):
                for basename in files:
                    entry = os.path.join(path, basename)
                    dest = entry.replace(source_path, destination_path, 1)
                    self._iput(entry, dest)
                for directory in directories:
                    dirname = os.path.join(path, directory).replace(source_path, destination_path, 1)
                    self.mkdir(dirname)

        elif os.path.isfile(source_path):
            self._iput(source_path, destination_path)
        else:
            raise StorageException('%s is neither a file nor a directory, may not exist' % source_path)

        if os.path.isdir(source_path) and (
            os.path.exists(os.path.join(source_path, "bagit.txt")) or
            os.path.exists(os.path.join(source_path, "bag-info.txt"))
        ):
            # once all file are uploaded, check that local files haven't been
            # corrupted
            # We only handle the case of an uncompressed bagit
            LOGGER.info("Peforms bagitcheck after sending files to irods")
            bag = bagit.Bag(source_path)
            if not bag.is_valid():
                raise StorageException("Bagit check on the local directory failed after files were uploaded to irods")


        # Final step : on success, if present, call some callback
        if len(self.callback)<=0: return # nothing to do
        LOGGER.info("move_from_storage_service() done, calling callback")

        data = {
            "name": os.path.basename(os.path.normpath(destination_path)),
            "size_in_mb": dirsize(source_path)/(1024*1024),
        }

        # Checksum
        if os.path.isdir(source_path):
            # Files to consider, dictionnary mapping filename to checksum_type
            files_checksum = {
                "manifest-md5.txt": "md5",
                "manifest-sha256.txt": "sha256",
                "manifest-sha512.txt": "sha512",
            }
            for filename in files_checksum.keys():
                fullpath = os.path.join(source_path, filename)
                if not os.path.exists(fullpath): continue
                data['checksum_%s'%filename] = generate_checksum(fullpath, checksum_type=files_checksum[filename]).hexdigest(),
        response = requests.post(self.callback, data = data)
        if response.status_code != 200:
            LOGGER.warning("Error while calling the callback, error_code = %d" % response.status_code)
            #raise StorageException("Error while calling the callback, error_code = %d" % response.status_code)


