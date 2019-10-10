# -*- coding: utf-8 -*-
from __future__ import absolute_import

# stdlib, alphabetical
import logging
import os
import pprint

# Core Django, alphabetical
from django.db import models
from django.utils.translation import ugettext_lazy as _

# Third party dependencies, alphabetical
import boto3
import re
import scandir

# This project, alphabetical

# This module, alphabetical
from . import StorageException
from .location import Location

LOGGER = logging.getLogger(__name__)


class S3(models.Model):
    space = models.OneToOneField("Space", to_field="uuid")
    endpoint_url = models.CharField(
        max_length=2048,
        verbose_name=_("S3 Endpoint URL"),
        help_text=_("S3 Endpoint URL. Eg. https://s3.amazonaws.com"),
    )
    access_key_id = models.CharField(
        max_length=64, verbose_name=_("Access Key ID to authenticate")
    )
    secret_access_key = models.CharField(
        max_length=256, verbose_name=_("Secret Access Key to authenticate with")
    )
    region = models.CharField(
        max_length=64,
        verbose_name=_("Region"),
        help_text=_("Region in S3. Eg. us-east-2"),
    )

    class Meta:
        verbose_name = _("S3")
        app_label = "locations"

    ALLOWED_LOCATION_PURPOSE = [Location.AIP_STORAGE]

    def __init__(self, *args, **kwargs):
        super(S3, self).__init__(*args, **kwargs)
        self._client = None
        self._resource = None

    @property
    def client(self):
        if self._client is None:
            self._client = boto3.client(
                service_name="s3",
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.access_key_id,
                aws_secret_access_key=self.secret_access_key,
                region_name=self.region,
            )
        return self._client

    @property
    def resource(self):
        if self._resource is None:
            self._resource = boto3.resource(
                service_name="s3",
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.access_key_id,
                aws_secret_access_key=self.secret_access_key,
                region_name=self.region,
            )
        return self._resource

    def _ensure_bucket_exists(self):
        """Ensure that the bucket exists by asking it something about itself.
        If we cannot retrieve metadata about it, and specifically, we can
        determine the endpoint has returned a `NoSuchBucket' error code then
        we attempt to create the bucket, else, we raise a StorageException.

        NB. Boto3 has an API called head_bucket that looks to return 400,
        Bad Request at time of 1.9.174 when the S3 documents suggest 404, or
        more 'specifically':

            > Otherwise, the operation might return responses such as 404 Not
            > Found and 403 Forbidden. "
            via-- Amazon AWS: https://docs.aws.amazon.com/AmazonS3/latest/API/RESTBucketHEAD.html
        """
        LOGGER.debug("Test the S3 bucket '%s' exists", self._bucket_name())
        try:
            loc_info = self.client.get_bucket_location(Bucket=self._bucket_name())
            LOGGER.debug("S3 bucket's response: %s", loc_info)
        except self.client.exceptions.ClientError as err:
            error_code = err.response["Error"]["Code"]
            if error_code != "NoSuchBucket":
                raise StorageException(err)
            LOGGER.info("Creating S3 bucket '%s'", self._bucket_name())
            self.client.create_bucket(
                Bucket=self._bucket_name(),
                CreateBucketConfiguration={"LocationConstraint": self.region},
            )

    def _bucket_name(self):
        return self.space_id

    def browse(self, path):
        # strip leading slash on path
        path = path.lstrip("/")

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
        if path != "":
            path = path.rstrip("/") + "/"

        objects = self.resource.Bucket(self._bucket_name()).objects.filter(Prefix=path)

        directories = set()
        entries = set()
        properties = {}

        for objectSummary in objects:
            relative_key = objectSummary.key.replace(path, "", 1).lstrip("/")

            if "/" in relative_key:
                directory_name = re.sub("/.*", "", relative_key)
                if directory_name:
                    directories.add(directory_name)
                    entries.add(directory_name)
            else:
                entries.add(relative_key)
                properties[relative_key] = {
                    "verbose name": objectSummary.key,
                    "size": objectSummary.size,
                    "timestamp": objectSummary.last_modified,
                    "e_tag": objectSummary.e_tag,
                }

        return {
            "directories": list(directories),
            "entries": list(entries),
            "properties": properties,
        }

    def delete_path(self, delete_path):
        """Delete an object from an S3 bucket. We assume an object exists, if
        it doesn't then the generator returned by the S3 library (Boto3) cannot
        be iterated, and we raise a StorageException.
        """
        if delete_path.startswith(os.sep):
            LOGGER.info(
                "S3 path to delete {} begins with {}; removing from path prior to deletion".format(
                    delete_path, os.sep
                )
            )
            delete_path = delete_path.lstrip(os.sep)
        obj = self.resource.Bucket(self._bucket_name()).objects.filter(
            Prefix=delete_path
        )
        items = False
        for object_summary in obj:
            items = True
            resp = object_summary.delete()
            LOGGER.debug("S3 response when attempting to delete:")
            LOGGER.debug(pprint.pformat(resp))
        if not items:
            err_str = "No packages found in S3 at: {}".format(delete_path)
            LOGGER.warning(err_str)
            raise StorageException(err_str)

    def move_to_storage_service(self, src_path, dest_path, dest_space):
        self._ensure_bucket_exists()
        bucket = self.resource.Bucket(self._bucket_name())

        # strip leading slash on src_path
        src_path = src_path.lstrip("/")

        objects = self.resource.Bucket(self._bucket_name()).objects.filter(
            Prefix=src_path
        )

        for objectSummary in objects:
            dest_file = objectSummary.key.replace(src_path, dest_path, 1)
            self.space.create_local_directory(dest_file)

            bucket.download_file(objectSummary.key, dest_file)

    def move_from_storage_service(self, src_path, dest_path, package=None):
        self._ensure_bucket_exists()
        bucket = self.resource.Bucket(self._bucket_name())

        if os.path.isdir(src_path):
            # ensure trailing slash on both paths
            src_path = os.path.join(src_path, "")
            dest_path = os.path.join(dest_path, "")

            # strip leading slash on dest_path
            dest_path = dest_path.lstrip("/")

            for path, dirs, files in scandir.walk(src_path):
                for basename in files:
                    entry = os.path.join(path, basename)
                    dest = entry.replace(src_path, dest_path, 1)

                    with open(entry, "rb") as data:
                        bucket.upload_fileobj(data, dest)

        elif os.path.isfile(src_path):
            # strip leading slash on dest_path
            dest_path = dest_path.lstrip("/")

            with open(src_path, "rb") as data:
                bucket.upload_fileobj(data, dest_path)

        else:
            raise StorageException(
                _("%(path)s is neither a file nor a directory, may not exist")
                % {"path": src_path}
            )
