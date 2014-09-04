# stdlib, alphabetical
import logging
import os

# Core Django, alphabetical
from django.db import models

# Third party dependencies, alphabetical
import swiftclient

# This project, alphabetical

# This module, alphabetical
from location import Location

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
        pass

    def move_to_storage_service(self, src_path, dest_path, dest_space):
        """ Moves src_path to dest_space.staging_path/dest_path. """
        pass

    def move_from_storage_service(self, source_path, destination_path):
        """ Moves self.staging_path/src_path to dest_path. """
        pass
