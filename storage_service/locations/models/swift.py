from __future__ import absolute_import
# stdlib, alphabetical
import logging
import os

# Core Django, alphabetical
from django.db import models

# Third party dependencies, alphabetical
import swiftclient

# This project, alphabetical
from common import utils

# This module, alphabetical
from . import StorageException
from .location import Location

LOGGER = logging.getLogger(__name__)


class Swift(models.Model):
    space = models.OneToOneField('Space', to_field='uuid')
    auth_url = models.CharField(max_length=256,
        help_text='URL to authenticate against')
    auth_version = models.CharField(max_length=8, default='2',
        help_text='OpenStack auth version')
    username = models.CharField(max_length=64,
        help_text='Username to authenticate as. E.g. http://example.com:5000/v2.0/')
    # HELP how do I store the password?  Has to be plaintext to send to Swift, but that seems like a bad idea
    password = models.CharField(max_length=256,
        help_text='Password to authenticate with')
    container = models.CharField(max_length=64)
    tenant = models.CharField(max_length=64, null=True, blank=True,
        help_text='The tenant/account name, required when connecting to an auth 2.0 system.')
    region = models.CharField(max_length=64, null=True, blank=True,
        help_text='Optional: Region in Swift')

    class Meta:
        verbose_name = "Swift"
        app_label = 'locations'

    ALLOWED_LOCATION_PURPOSE = [
        Location.AIP_STORAGE,
        Location.DIP_STORAGE,
        Location.TRANSFER_SOURCE,
        Location.BACKLOG,
    ]

    def __init__(self, *args, **kwargs):
        super(Swift, self).__init__(*args, **kwargs)
        self._connection = None

    @property
    def connection(self):
        if self._connection is None:
            self._connection = swiftclient.client.Connection(
                authurl=self.auth_url,
                user=self.username,
                key=self.password,
                tenant_name=self.tenant,
                auth_version=self.auth_version,
                os_options={'region_name': self.region}
            )
        return self._connection

    def browse(self, path):
        """
        Returns information about the files and simulated-folders in Duracloud.

        See Space.browse for full documentation.

        Properties provided:
        'size': Size of the object
        'timestamp': Last modified timestamp of the object or directory
        """
        # Can only browse directories. Add a trailing / to make Swift happy
        if not path.endswith('/'):
            path += '/'
        _, content = self.connection.get_container(self.container, delimiter='/', prefix=path)
        # Replace path, strip trailing /, sort
        entries = []
        directories = []
        properties = {}
        for entry in content:
            if 'subdir' in entry:  # Directories
                basename = os.path.basename(entry['subdir'].rstrip('/'))
                directories.append(basename)
            elif 'name' in entry:  # Files
                basename = os.path.basename(entry['name'])
                properties[basename] = {
                    'size': entry['bytes'],
                    'timestamp': entry['last_modified'],
                }
            else:
                # Error
                LOGGER.warning('%s is neither a file nor a directory.', entry)
                continue
            entries.append(basename)

        return {
            'directories': sorted(directories, key=lambda s: s.lower()),
            'entries': sorted(entries, key=lambda s: s.lower()),
            'properties': properties,
        }

    def delete_path(self, delete_path):
        # Try to delete object
        try:
            self.connection.delete_object(self.container, delete_path)
        except swiftclient.exceptions.ClientException:
            # Swift only stores objects and fakes having folders. If delete_path
            # doesn't exist, assume it is supposed to be a folder and fetch all
            # items with that prefix to delete.
            try:
                _, content = self.connection.get_container(self.container, prefix=delete_path)
            except swiftclient.exceptions.ClientException:
                LOGGER.warning('Neither file %s nor container %s exist; unable to delete any content.', delete_path, self.container)
                return
            to_delete = [x['name'] for x in content if x.get('name')]
            for d in to_delete:
                self.connection.delete_object(self.container, d)

    def _download_file(self, remote_path, download_path):
        """
        Download the file from download_path in this Space to remote_path.

        :param str remote_path: Full path in Swift
        :param str download_path: Full path to save the file to
        :raises: swiftclient.exceptions.ClientException may be raised and is not caught
        """
        # TODO find a way to stream content to dest_path, instead of having to put it in memory
        headers, content = self.connection.get_object(self.container, remote_path)
        self.space.create_local_directory(download_path)
        with open(download_path, 'wb') as f:
            f.write(content)
        # Check ETag matches checksum of this file
        if 'etag' in headers:
            checksum = utils.generate_checksum(download_path)
            if checksum.hexdigest() != headers['etag']:
                message = 'ETag {} for {} does not match {}'.format(remote_path, headers['etag'], checksum.hexdigest())
                logging.warning(message)
                raise StorageException(message)

    def move_to_storage_service(self, src_path, dest_path, dest_space):
        """ Moves src_path to dest_space.staging_path/dest_path. """
        try:
            self._download_file(src_path, dest_path)
        except swiftclient.exceptions.ClientException:
            # Swift only stores objects and fakes having folders. If src_path
            # doesn't exist, assume it is supposed to be a folder and fetch all
            # items with that prefix.
            _, content = self.connection.get_container(self.container, prefix=src_path)
            to_get = [x['name'] for x in content if x.get('name')]
            if not to_get:
                # If nothing found, try normalizing src_path to remove possible
                # extra characters like / /* /.  These glob-match on a
                # filesystem, but do not character-match in Swift.
                # Normalize dest_path as well, so replace continues to work
                src_path = os.path.normpath(src_path)
                dest_path = os.path.normpath(dest_path)
                _, content = self.connection.get_container(self.container, prefix=src_path)
                to_get = [x['name'] for x in content if x.get('name')]
            for entry in to_get:
                dest = entry.replace(src_path, dest_path, 1)
                self._download_file(entry, dest)

    def move_from_storage_service(self, source_path, destination_path):
        """ Moves self.staging_path/src_path to dest_path. """
        if os.path.isdir(source_path):
            # Both source and destination paths should end with /
            destination_path = os.path.join(destination_path, '')
            # Swift does not accept folders, so upload each file individually
            for path, _, files in os.walk(source_path):
                for basename in files:
                    entry = os.path.join(path, basename)
                    dest = entry.replace(source_path, destination_path, 1)
                    checksum = utils.generate_checksum(entry)
                    with open(entry, 'rb') as f:
                        self.connection.put_object(
                            self.container,
                            obj=dest,
                            contents=f,
                            etag=checksum.hexdigest(),
                            content_length=os.path.getsize(entry)
                        )
        elif os.path.isfile(source_path):
            checksum = utils.generate_checksum(source_path)
            with open(source_path, 'rb') as f:
                self.connection.put_object(
                    self.container,
                    obj=destination_path,
                    contents=f,
                    etag=checksum.hexdigest(),
                    content_length=os.path.getsize(source_path),
                )
        else:
            raise StorageException('%s is neither a file nor a directory, may not exist' % source_path)
