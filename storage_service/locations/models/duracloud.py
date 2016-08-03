from __future__ import absolute_import
# stdlib, alphabetical
import logging
from lxml import etree
import os
import re
import shutil
import urllib

# Core Django, alphabetical
from django.db import models

# Third party dependencies, alphabetical
import requests

# This project, alphabetical
from common import utils

# This module, alphabetical
from . import StorageException
from .location import Location

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
    CHUNK_SIZE = 1 * 1024 * 1024 * 1024  # 1 GB

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
        LOGGER.debug('URL: %s', url)
        response = self.session.delete(url)
        LOGGER.debug('Response: %s', response)
        if response.status_code == 404:
            # Check if this is a chunked file
            manifest_url = url + self.MANIFEST_SUFFIX
            LOGGER.debug('Manifest URL: %s', manifest_url)
            response = self.session.get(manifest_url)
            LOGGER.debug('Response: %s', response)
            if response.ok:
                # Get list of file chunks
                root = etree.fromstring(response.content)
                to_delete = [e.attrib['chunkId'] for e in root.findall('chunks/chunk')]
                to_delete.append(delete_path + self.MANIFEST_SUFFIX)
                LOGGER.debug('Chunks to delete: %s', to_delete)
            else:
                # File cannot be found - this may be a folder
                to_delete = self._get_files_list(delete_path, show_split_files=True)
            # Do not support globbing for delete - do not want to accidentally
            # delete something
            for d in to_delete:
                url = self.duraspace_url + urllib.quote(d)
                response = self.session.delete(url)

    def _download_file(self, url, download_path, expected_size=0, checksum=None):
        """
        Helper to download files from DuraCloud.

        :param url: URL to fetch the file from.
        :param download_path: Absolute path to store the downloaded file at.
        :return: True on success, False if file not found
        :raises: StorageException if response code not 200 or 404
        """
        LOGGER.debug('URL: %s', url)
        response = self.session.get(url)
        LOGGER.debug('Response: %s', response)
        if response.status_code == 404:
            # Check if chunked by looking for a .dura-manifest
            manifest_url = url + self.MANIFEST_SUFFIX
            LOGGER.debug('Manifest URL: %s', manifest_url)
            response = self.session.get(manifest_url)
            LOGGER.debug('Response: %s', response)
            # No manifest - this file does not exist
            if not response.ok:
                return False

            # Get chunks, expected size, checksum
            root = etree.fromstring(response.content)
            expected_size = int(root.findtext('header/sourceContent/byteSize'))
            checksum = root.findtext('header/sourceContent/md5')
            chunk_elements = [e for e in root.findall('chunks/chunk')]
            # Download each chunk and append to original file
            self.space.create_local_directory(download_path)
            LOGGER.debug('Writing to %s', download_path)
            with open(download_path, 'wb') as output_f:
                for e in chunk_elements:
                    # Parse chunk element
                    chunk = e.attrib['chunkId']
                    size = int(e.findtext('byteSize'))
                    md5 = e.findtext('md5')
                    # Download
                    chunk_url = self.duraspace_url + urllib.quote(chunk)
                    LOGGER.debug('Chunk URL: %s', chunk_url)
                    chunk_path = chunk_url.replace(url, download_path)
                    LOGGER.debug('Chunk path: %s', chunk_path)
                    self._download_file(chunk_url, chunk_path, size, md5)
                    # Append to output
                    with open(chunk_path, 'rb') as chunk_f:
                        shutil.copyfileobj(chunk_f, output_f)
                    # Delete chunk_path
                    os.remove(chunk_path)
        elif response.status_code != 200:
            LOGGER.warning('Response: %s when fetching %s', response, url)
            LOGGER.warning('Response text: %s', response.text)
            raise StorageException('Unable to fetch %s' % url)
        else:  # Status code 200 - file exists
            self.space.create_local_directory(download_path)
            LOGGER.debug('Writing to %s', download_path)
            with open(download_path, 'wb') as f:
                f.write(response.content)

        # Verify file, if size or checksum is known
        if expected_size and os.path.getsize(download_path) != expected_size:
            raise StorageException('File %s does not match expected size of %s bytes, but was actually %s bytes', download_path, expected_size, os.path.getsize(download_path))
        calculated_checksum = utils.generate_checksum(download_path, 'md5')
        if checksum and checksum != calculated_checksum.hexdigest():
            raise StorageException('File %s does not match expected checksum of %s, but was actually %s', download_path, checksum, calculated_checksum.hexdigest())

        return True

    def move_to_storage_service(self, src_path, dest_path, dest_space):
        """ Moves src_path to dest_space.staging_path/dest_path. """
        # Convert unicode strings to byte strings
        #  .replace() doesn't handle mixed unicode/str well, and it's easiest to put it all in strs
        src_path = utils.coerce_str(src_path)
        dest_path = utils.coerce_str(dest_path)
        # Try to fetch if it's a file
        url = self.duraspace_url + urllib.quote(src_path)
        success = self._download_file(url, dest_path)
        if not success:
            LOGGER.debug('%s not found, trying as folder', src_path)
            # File cannot be found - this may be a folder
            # Remove /. and /* at the end of the string. These glob-match on a
            # filesystem, but do not character-match in Duracloud.
            # Normalize dest_path as well so replace continues to work
            find_regex = r'/[\.\*]$'
            src_path = re.sub(find_regex, '/', src_path)
            dest_path = re.sub(find_regex, '/', dest_path)
            LOGGER.debug('Modified paths: src: %s dest: %s', src_path, dest_path)
            to_get = self._get_files_list(src_path, show_split_files=False)
            for entry in to_get:
                url = self.duraspace_url + urllib.quote(entry)
                dest = entry.replace(src_path, dest_path, 1)
                self._download_file(url, dest)

    def _process_chunk(self, f, chunk_path):
        bytes_read = 0
        bytes_to_read = 1024 * 1024  # 1MB

        with open(chunk_path, 'w') as fchunk:
            while bytes_read < self.CHUNK_SIZE:
                data = f.read(bytes_to_read)
                fchunk.write(data)

                length = len(data)

                if length < bytes_to_read:
                    raise StopIteration("End of file reached")
                else:
                    bytes_read += length

    def _upload_file(self, url, upload_file, resume=False):
        """
        Upload a file of any size to Duracloud.

        If the file is larger that self.CHUNK_SIZE, will chunk it and upload chunks and manifest.

        :param url: URL to upload the file to.
        :param upload_file: Absolute path to the file to upload.
        :returns: None
        :raises: StorageException if error storing file
        """
        LOGGER.debug('Upload %s to %s', upload_file, url)
        filesize = os.path.getsize(upload_file)
        if filesize > self.CHUNK_SIZE:
            LOGGER.debug('%s size (%s) larger than %s', upload_file, filesize, self.CHUNK_SIZE)
            # Create manifest info for complete file.  Eg:
            # <header schemaVersion="0.2">
            #   <sourceContent contentId="chunked/chunked_image.jpg">
            #     <mimetype>application/octet-stream</mimetype>
            #     <byteSize>2222135</byteSize>
            #     <md5>9497f70a1a17943ddfcbed567538900d</md5>
            #   </sourceContent>
            # </header>
            relative_path = urllib.unquote(url.replace(self.duraspace_url, '', 1))
            LOGGER.debug('File name: %s', relative_path)
            checksum = utils.generate_checksum(upload_file, 'md5')
            LOGGER.debug('Checksum for %s: %s', upload_file, checksum.hexdigest())
            root = etree.Element('{duracloud.org}chunksManifest', nsmap={'dur': 'duracloud.org'})
            header = etree.SubElement(root, 'header', schemaVersion="0.2")
            content = etree.SubElement(header, 'sourceContent', contentId=relative_path)
            etree.SubElement(content, 'mimetype').text = 'application/octet-stream'
            etree.SubElement(content, 'byteSize').text = str(filesize)
            etree.SubElement(content, 'md5').text = checksum.hexdigest()
            chunks = etree.SubElement(root, 'chunks')
            # Split file into chunks
            with open(upload_file, 'rb') as f:
                # If resume, check if chunks already exists
                if resume:
                    chunklist = set(self._get_files_list(relative_path))
                    LOGGER.debug('Chunklist %s', chunklist)
                file_complete = False
                i = 0
                while not file_complete:
                    # Setup chunk info
                    chunk_suffix = '.dura-chunk-' + str(i).zfill(4)
                    chunk_path = upload_file + chunk_suffix
                    LOGGER.debug('Chunk path: %s', chunk_path)
                    chunk_url = url + chunk_suffix
                    LOGGER.debug('Chunk URL: %s', chunk_url)
                    chunkid = relative_path + chunk_suffix
                    LOGGER.debug('Chunk ID: %s', chunkid)
                    try:
                        self._process_chunk(f, chunk_path)
                    except StopIteration:
                        file_complete = True
                    # Make chunk element
                    # <chunk chunkId="chunked/chunked_image.jpg.dura-chunk-0000" index="0">
                    #   <byteSize>2097152</byteSize>
                    #   <md5>ddbb227beaac5a9dc34eb49608997abf</md5>
                    # </chunk>
                    checksum = utils.generate_checksum(chunk_path)
                    chunk_e = etree.SubElement(chunks, 'chunk', chunkId=chunkid)
                    etree.SubElement(chunk_e, 'byteSize').text = str(os.path.getsize(chunk_path))
                    etree.SubElement(chunk_e, 'md5').text = checksum.hexdigest()
                    # Upload chunk
                    # Check if chunk exists already
                    if resume and chunkid in chunklist:
                        LOGGER.info('%s already in Duracloud, skipping upload', chunk_path)
                    else:
                        self._upload_chunk(chunk_url, chunk_path)
                    # Delete chunk
                    os.remove(chunk_path)
                    i += 1
            # Write .dura-manifest
            manifest_path = upload_file + self.MANIFEST_SUFFIX
            manifest_url = url + self.MANIFEST_SUFFIX
            with open(manifest_path, 'w') as f:
                f.write(etree.tostring(root, pretty_print=True, xml_declaration=True, encoding='UTF-8'))
            # Upload .dura-manifest
            self._upload_chunk(manifest_url, manifest_path)
            os.remove(manifest_path)
            # TODO what if .dura-manifest over chunksize?
        else:
            # Example URL: https://trial.duracloud.org/durastore/trial261//ts/test.txt
            self._upload_chunk(url, upload_file)

    def _upload_chunk(self, url, upload_file, retry_attempts=3):
        """
        Upload a single file to Duracloud.

        The file size must be less than self.CHUNK_SIZE.
        Call _upload_file_check_chunking if the file might be larger.

        :param url: URL to upload the file to.
        :param upload_file: Absolute path to the file to upload.
        :param int retry_attempts: Number of retry attempts left.
        :returns: None
        :raises: StorageException if error storing file
        """
        try:
            LOGGER.debug('PUT URL: %s', url)
            with open(upload_file, 'rb') as f:
                response = self.session.put(url, data=f)
            LOGGER.debug('Response: %s', response)
        except Exception:
            LOGGER.exception('Error in PUT to %s', url)
            if retry_attempts > 0:
                LOGGER.info('Retrying %s', upload_file)
                self._upload_chunk(url, upload_file, retry_attempts - 1)
            else:
                raise
        else:
            if response.status_code != 201:
                LOGGER.warning('%s: Response: %s', response, response.text)
                if retry_attempts > 0:
                    LOGGER.info('Retrying %s', upload_file)
                    self._upload_chunk(url, upload_file, retry_attempts - 1)
                else:
                    raise StorageException('Unable to store %s' % upload_file)

    def move_from_storage_service(self, source_path, destination_path, resume=False):
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
                    self._upload_file(url, entry, resume=resume)
        elif os.path.isfile(source_path):
            url = self.duraspace_url + urllib.quote(destination_path)
            self._upload_file(url, source_path, resume=resume)
        elif not os.path.exists(source_path):
            raise StorageException('%s does not exist.' % source_path)
        else:
            raise StorageException('%s is not a file or directory.' % source_path)
