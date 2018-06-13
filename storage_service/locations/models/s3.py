from __future__ import absolute_import
# stdlib, alphabetical
import logging
import os

# Core Django, alphabetical
from django.db import models
from django.utils.translation import ugettext as _, ugettext_lazy as _l

# Third party dependencies, alphabetical
import boto3
import re

# This project, alphabetical

# This module, alphabetical
from . import StorageException
from .location import Location

LOGGER = logging.getLogger(__name__)


class S3(models.Model):
    space = models.OneToOneField('Space', to_field='uuid')
    endpoint_url = models.CharField(max_length=2048,
        verbose_name=_l('S3 Endpoint URL'),
        help_text=_l('S3 Endpoint URL. Eg. https://s3.amazonaws.com'))
    access_key_id = models.CharField(max_length=64,
        verbose_name=_l('Access Key ID to authenticate'))
    secret_access_key = models.CharField(max_length=256,
        verbose_name=_l('Secret Access Key to authenticate with'))
    region = models.CharField(max_length=64,
        verbose_name=_l('Region'),
        help_text=_l('Region in S3. Eg. us-east-2'))

    class Meta:
        verbose_name = _l("S3")
        app_label = 'locations'

    ALLOWED_LOCATION_PURPOSE = [
        Location.AIP_STORAGE,
    ]

    def __init__(self, *args, **kwargs):
        super(S3, self).__init__(*args, **kwargs)
        self._client = None
        self._resource = None

    @property
    def client(self):
        if self._client is None:
            self._client = boto3.client(
                service_name='s3',
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.access_key_id,
                aws_secret_access_key=self.secret_access_key,
                region_name=self.region)
        return self._client

    @property
    def resource(self):
        if self._resource is None:
            self._resource = boto3.resource(
                service_name='s3',
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.access_key_id,
                aws_secret_access_key=self.secret_access_key,
                region_name=self.region)
        return self._resource

    def _ensure_bucket_exists(self):
        self.client.create_bucket(Bucket=self._bucket_name())

    def _bucket_name(self):
        return self.space_id

    def browse(self, path):
        # strip leading slash on path
        path = path.lstrip('/')

        # We need a trailing slash on non-empty prefixes because a path like:
        #
        #      /path/to/requirements
        #
        # will happily prefix match:
        #
        #      /path/to/requirements.txt
        #
        # which is not the intention!
        #
        if path != '':
            path = path.rstrip('/') + '/'

        objects = self.resource.Bucket(self._bucket_name()).objects.filter(Prefix=path)

        directories = set()
        entries = set()
        properties = {}

        for objectSummary in objects:
            relative_key = objectSummary.key.replace(path, '', 1).lstrip('/')

            if '/' in relative_key:
                directory_name = re.sub('/.*', '', relative_key)
                if directory_name:
                    directories.add(directory_name)
                    entries.add(directory_name)
            else:
                entries.add(relative_key)
                properties[relative_key] = {
                    'verbose name': objectSummary.key,
                    'size': objectSummary.size,
                    'timestamp': objectSummary.last_modified,
                    'e_tag': objectSummary.e_tag,
                }

        return {
            'directories': list(directories),
            'entries': list(entries),
            'properties': properties,
        }

    def delete_path(self, delete_path):
        objects = self.resource.Bucket(self._bucket_name()).objects.filter(Prefix=delete_path)

        for objectSummary in objects:
            objectSummary.delete()

    def move_to_storage_service(self, src_path, dest_path, dest_space):
        self._ensure_bucket_exists()
        bucket = self.resource.Bucket(self._bucket_name())

        # strip leading slash on src_path
        src_path = src_path.lstrip('/')

        objects = self.resource.Bucket(self._bucket_name()).objects.filter(Prefix=src_path)

        for objectSummary in objects:
            dest_file = objectSummary.key.replace(src_path, dest_path, 1)
            self.space.create_local_directory(dest_file)

            bucket.download_file(objectSummary.key, dest_file)

    def move_from_storage_service(self, src_path, dest_path, package=None):
        self._ensure_bucket_exists()
        bucket = self.resource.Bucket(self._bucket_name())

        if os.path.isdir(src_path):
            # ensure trailing slash on both paths
            src_path = os.path.join(src_path, '')
            dest_path = os.path.join(dest_path, '')

            # strip leading slash on dest_path
            dest_path = dest_path.lstrip('/')

            for path, dirs, files in os.walk(src_path):
                for basename in files:
                    entry = os.path.join(path, basename)
                    dest = entry.replace(src_path, dest_path, 1)

                    with open(entry, 'rb') as data:
                        bucket.upload_fileobj(data, dest)

        elif os.path.isfile(src_path):
            # strip leading slash on dest_path
            dest_path = dest_path.lstrip('/')

            with open(src_path, 'rb') as data:
                bucket.upload_fileobj(data, dest_path)

        else:
            raise StorageException(
                _('%(path)s is neither a file nor a directory, may not exist') %
                {'path': src_path})
