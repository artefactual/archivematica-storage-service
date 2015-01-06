# stdlib, alphabetical
import logging
from lxml import etree
import os
import re
import urllib

# Core Django, alphabetical
from django.db import models

# Third party dependencies, alphabetical
import requests

# This project, alphabetical
from common import utils

# This module, alphabetical
from . import StorageException
from location import Location

LOGGER = logging.getLogger(__name__)


class Duracloud(models.Model):
    space = models.OneToOneField('Space', to_field='uuid')
    host = models.CharField(max_length=256,
        help_text='Hostname of the DuraCloud instance. Eg. trial.duracloud.org')
    user = models.CharField(max_length=64, help_text='Username to authenticate as')
    password = models.CharField(max_length=64, help_text='Password to authenticate with')
    duraspace = models.CharField(max_length=64, help_text='Name of the Space within DuraCloud')

    class Meta:
        verbose_name = "DuraCloud"
        app_label = 'locations'

    ALLOWED_LOCATION_PURPOSE = [
        Location.AIP_RECOVERY,
        Location.AIP_STORAGE,
        Location.DIP_STORAGE,
        Location.TRANSFER_SOURCE,
        Location.BACKLOG,
    ]

    MANIFEST_SUFFIX = '.dura-manifest'

    def __init__(self, *args, **kwargs):
        super(Duracloud, self).__init__(*args, **kwargs)
        self._session = None

    @property
    def session(self):
        if self._session is None:
            self._session = requests.Session()
            self._session.auth = (self.user, self.password)
        return self._session

    @property
    def duraspace_url(self):
        return 'https://' + self.host + '/durastore/' + self.duraspace + '/'

    def _get_files_list(self, prefix, show_split_files=True):
        """
        Generator function to return the full path of all files starting with prefix.

        :param prefix: All paths returned will start with prefix
        :param bool show_split_files: If True, will show files ending with .dura-chunk-#### and .dura-manifest. If False, will show the original file name (everything before .dura-manifest)
        :returns: Iterator of paths
        """
        params = {'prefix': prefix}
        LOGGER.debug('URL: %s, params: %s', self.duraspace_url, params)
        response = self.session.get(self.duraspace_url, params=params)
        LOGGER.debug('Response: %s', response)
        if response.status_code != 200:
            LOGGER.warning('%s: Response: %s', response, response.text)
            raise StorageException('Unable to get list of files in %s' % prefix)
        # Response is XML in the form:
        # <space id="self.durastore">
        #   <item>path</item>
        #   <item>path</item>
        # </space>
        root = etree.fromstring(response.content)
        paths = [p.text for p in root]
        LOGGER.debug('Paths first 10: %s', paths[:10])
        LOGGER.debug('Paths last 10: %s', paths[-10:])
        durachunk_regex = r'.dura-chunk-\d{4}$'
        duramanifest_len = len(self.MANIFEST_SUFFIX)
        while paths:
            for p in paths:
                if not show_split_files:
                    # There is exactly one .dura-manifest for chunked files
                    # Return the original filename when we find a manifest file
                    if p.endswith(self.MANIFEST_SUFFIX):
                        yield p[:-duramanifest_len]
                        continue
                    # File chunks skipped - manifest returns original filename
                    if re.search(durachunk_regex, p):
                        continue
                yield utils.coerce_str(p)
            params['marker'] = paths[-1]
            LOGGER.debug('URL: %s, params: %s', self.duraspace_url, params)
            response = self.session.get(self.duraspace_url, params=params)
            LOGGER.debug('Response: %s', response)
            if response.status_code != 200:
                LOGGER.warning('%s: Response: %s', response, response.text)
                raise StorageException('Unable to get list of files in %s' % prefix)
            root = etree.fromstring(response.content)
            paths = [p.text for p in root]
            LOGGER.debug('Paths first 10: %s', paths[:10])
            LOGGER.debug('Paths last 10: %s', paths[-10:])

    def browse(self, path):
        """
        Returns information about the files and simulated-folders in Duracloud.

        See Space.browse for full documentation.

        Properties provided:
        'object count': Number of objects in the directory, including children
        """
        if path and not path.endswith('/'):
            path += '/'
        entries = set()
        directories = set()
        properties = {}
        # Handle paths one at a time to deal with lots of files
        paths = self._get_files_list(path, show_split_files=False)
        for p in paths:
            path_parts = p.replace(path, '', 1).split('/')
            dirname = path_parts[0]
            if not dirname:
                continue
            entries.add(dirname)
            if len(path_parts) > 1:
                directories.add(dirname)
                properties[dirname] = properties.get(dirname, {})  # Default empty dict
                properties[dirname]['object count'] = properties[dirname].get('object count', 0) + 1  # Increment object count

        entries = sorted(entries, key=lambda s: s.lower())  # Also converts to list
        directories = sorted(directories, key=lambda s: s.lower())  # Also converts to list
        return {'directories': directories, 'entries': entries, 'properties': properties}

    def delete_path(self, delete_path):
        # BUG If delete_path is a folder but provided without a trailing /, will delete a file with the same name.
        # Files
        url = self.duraspace_url + urllib.quote(delete_path)
        response = self.session.delete(url)
        if response.status_code == 404:
            # File cannot be found - this may be a folder
            to_delete = self._get_files_list(delete_path)
            # Do not support globbing for delete - do not want to accidentally
            # delete something
            for d in to_delete:
                url = self.duraspace_url + urllib.quote(d)
                response = self.session.delete(url)

    def move_to_storage_service(self, src_path, dest_path, dest_space):
        """ Moves src_path to dest_space.staging_path/dest_path. """
        # Convert unicode strings to byte strings
        #  .replace() doesn't handle mixed unicode/str well, and it's easiest to put it all in strs
        src_path = utils.coerce_str(src_path)
        dest_path = utils.coerce_str(dest_path)
        # Try to fetch if it's a file
        url = self.duraspace_url + urllib.quote(src_path)
        response = self.session.get(url)
        if response.status_code == 404:
            LOGGER.debug('%s not found, trying as folder', src_path)
            # File cannot be found - this may be a folder
            # Remove /. and /* at the end of the string. These glob-match on a
            # filesystem, but do not character-match in Duracloud.
            # Normalize dest_path as well so replace continues to work
            find_regex = r'/[\.\*]$'
            src_path = re.sub(find_regex, '/', src_path)
            dest_path = re.sub(find_regex, '/', dest_path)
            LOGGER.debug('Modified paths: src: %s dest: %s', src_path, dest_path)
            to_get = self._get_files_list(src_path)
            for entry in to_get:
                dest = entry.replace(src_path, dest_path, 1)
                url = self.duraspace_url + urllib.quote(entry)
                LOGGER.debug('Getting %s', url)
                response = self.session.get(url)
                if response.status_code != 200:
                    LOGGER.warning('Response: %s when fetching %s', response, url)
                    LOGGER.warning('Response text: %s', response.text)
                    raise StorageException('Unable to fetch %s' % entry)
                self.space._create_local_directory(dest)
                LOGGER.debug('Writing %s to %s', entry, dest)
                with open(dest, 'wb') as f:
                    f.write(response.content)
        elif response.status_code != 200:
            raise StorageException('Unable to fetch %s' % src_path)
        else:  # status_code == 200
            self.space._create_local_directory(dest_path)
            LOGGER.debug('Writing to %s', dest_path)
            with open(dest_path, 'wb') as f:
                f.write(response.content)

    def _upload_file(self, url, upload_file):
        # Example URL: https://trial.duracloud.org/durastore/trial261//ts/test.txt
        with open(upload_file, 'rb') as f:
            response = self.session.put(url, data=f)
        LOGGER.info('Response from %s: %s', url, response)
        if response.status_code != 201:
            LOGGER.warning('Response text: %s', response.text)
            raise StorageException('Unable to store %s' % upload_file)

    def move_from_storage_service(self, source_path, destination_path):
        """ Moves self.staging_path/src_path to dest_path. """
        source_path = utils.coerce_str(source_path)
        destination_path = utils.coerce_str(destination_path)
        if os.path.isdir(source_path):
            # Both source and destination paths should end with /
            destination_path = os.path.join(destination_path, '')
            # Duracloud does not accept folders, so upload each file individually
            for path, _, files in os.walk(source_path):
                for basename in files:
                    entry = os.path.join(path, basename)
                    dest = entry.replace(source_path, destination_path, 1)
                    url = self.duraspace_url + urllib.quote(dest)
                    self._upload_file(url, entry)
        elif os.path.isfile(source_path):
            url = self.duraspace_url + urllib.quote(destination_path)
            self._upload_file(url, source_path)
        elif not os.path.exists(source_path):
            raise StorageException('%s does not exist.' % source_path)
        else:
            raise StorageException('%s is not a file or directory.' % source_path)
