# stdlib, alphabetical
import json
import logging
import os
import requests

# Core Django, alphabetical
from django.conf import settings
from django.db import models

# Third party dependencies, alphabetical

# This project, alphabetical
from common import utils

# This module, alphabetical
from . import StorageException
from location import Location

LOGGER = logging.getLogger(__name__)

if settings.DEBUG:
    VERIFY = False
else:
    VERIFY = True


class Arkivum(models.Model):
    space = models.OneToOneField('Space', to_field='uuid')

    host = models.CharField(max_length=256,
        help_text='Hostname of the Arkivum web instance. Eg. arkivum.example.com:8443')
    # Optionally be able to rsync
    remote_user = models.CharField(max_length=64, null=True, blank=True,
        help_text="Optional: Username on the remote machine accessible via passwordless ssh.")
    remote_name = models.CharField(max_length=256, null=True, blank=True,
        help_text="Optional: Name or IP of the remote machine.")

    class Meta:
        verbose_name = "Arkivum"
        app_label = 'locations'

    ALLOWED_LOCATION_PURPOSE = [
        Location.AIP_STORAGE,
    ]

    def browse(self, path):
        # This is AIP storage only - do not support browse
        logging.warning('Arkivum does not support browsing')
        return {'directories': [], 'entries': []}

    def delete_path(self, delete_path):
        pass

    def move_to_storage_service(self, src_path, dest_path, dest_space):
        """ Moves src_path to dest_space.staging_path/dest_path. """
        pass

    def move_from_storage_service(self, source_path, destination_path):
        """ Moves self.staging_path/src_path to dest_path. """
        # Rsync to Arkivum watched directory
        if self.remote_user and self.remote_name:
            self.space._create_rsync_directory(destination_path, self.remote_user, self.remote_name)
            rsync_dest = "{}@{}:{}".format(self.remote_user, self.remote_name, utils.coerce_str(destination_path))
        else:
            rsync_dest = destination_path
            self.space._create_local_directory(destination_path)
        self.space._move_rsync(source_path, rsync_dest)

    def post_move_from_storage_service(self, staging_path, destination_path, package):
        """ POST to Arkivum with information about the newly stored Package. """
        if package is None:
            return

        # Get size, checksum, checksum algorithm (md5sum), compression algorithm
        checksum = utils.generate_checksum(staging_path, 'md5')
        payload = {
            'size': str(os.path.getsize(staging_path)),
            'checksum': checksum.hexdigest(),
            'checksumAlgorithm': 'md5',
            'compressionAlgorithm': os.path.splitext(package.current_path)[1],
        }
        payload = json.dumps(payload)

        # POST to Arkivum host/api/2/files/release/relative_path
        relative_path = os.path.relpath(destination_path, self.space.path)
        url = 'https://' + self.host + '/api/2/files/release/' + relative_path
        LOGGER.info('URL: %s, Payload: %s', url, payload)

        try:
            response = requests.post(url, headers={'Content-Type': 'application/json'}, data=payload, verify=VERIFY)
        except requests.exceptions.ConnectionError:
            LOGGER.exception('Error in connection for POST to %s', url)
            raise StorageException('Error in connection for POST to %s', url)

        LOGGER.info('Response: %s, Response text: %s', response.status_code, response.text)
        if response.status_code not in (requests.codes.ok, requests.codes.accepted):
            LOGGER.warning('Arkivum responded with %s: %s', response.status_code, response.text)
            raise StorageException('Unable to notify Arkivum of %s', package)
        # Response has request ID for polling status
        try:
            response_json = response.json()
        except json.JSONDecodeError:
            raise StorageException("Could not get request ID from Arkivum's response %s", response.text)
        request_id = response_json['id']

        # Store request ID in misc_attributes
        package.misc_attributes.update({'request_id': request_id})
        package.save()

        # TODO Uncompressed: Post info about bag (really only support AIPs)

    def update_package_status(self, package):
        pass
