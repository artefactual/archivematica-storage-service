# -*- coding: utf-8 -*-
from __future__ import absolute_import

# stdlib, alphabetical
import logging
import os
import pprint
from functools import wraps

# Core Django, alphabetical
from django.conf import settings
from django.db import models
from django.utils.translation import ugettext_lazy as _

# Third party dependencies, alphabetical
import boto3
import botocore
import re
import scandir

# This project, alphabetical
from common import utils

# This module, alphabetical
from . import StorageException
from .location import Location


LOGGER = logging.getLogger(__name__)

if settings.S3_DEBUG:
    # Log all debug messages from S3. See the site configuration script
    # for more information about why this should not be run in
    # production unless the data protection ramifications are completely
    # understood and accepted.
    boto3.set_stream_logger(name="", level="DEBUG")


def boto_exception(fn):
    @wraps(fn)
    def _inner(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except botocore.exceptions.BotoCoreError as e:
            raise StorageException("AWS error: %r", e)

    return _inner


class S3(models.Model):
    space = models.OneToOneField("Space", to_field="uuid")
    access_key_id = models.CharField(
        max_length=64, blank=True, verbose_name=_("Access Key ID to authenticate")
    )
    secret_access_key = models.CharField(
        max_length=256,
        blank=True,
        verbose_name=_("Secret Access Key to authenticate with"),
    )
    endpoint_url = models.CharField(
        max_length=2048,
        verbose_name=_("S3 Endpoint URL"),
        help_text=_("S3 Endpoint URL. Eg. https://s3.amazonaws.com"),
    )
    region = models.CharField(
        max_length=64,
        verbose_name=_("Region"),
        help_text=_("Region in S3. Eg. us-east-2"),
    )
    bucket = models.CharField(
        max_length=64,
        verbose_name=_("S3 Bucket"),
        blank=True,
        help_text=_("S3 Bucket Name"),
    )

    class Meta:
        verbose_name = _("S3")
        app_label = "locations"

    ALLOWED_LOCATION_PURPOSE = [
        Location.AIP_STORAGE,
        Location.REPLICATOR,
        Location.TRANSFER_SOURCE,
    ]

    @property
    def resource(self):
        if not hasattr(self, "_resource"):
            config = botocore.config.Config(
                connect_timeout=settings.S3_TIMEOUTS, read_timeout=settings.S3_TIMEOUTS
            )
            boto_args = {
                "service_name": "s3",
                "endpoint_url": self.endpoint_url,
                "region_name": self.region,
                "config": config,
            }
            if self.access_key_id and self.secret_access_key:
                boto_args.update(
                    aws_access_key_id=self.access_key_id,
                    aws_secret_access_key=self.secret_access_key,
                )
            self._resource = boto3.resource(**boto_args)
        return self._resource

    @boto_exception
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
        LOGGER.debug("Test the S3 bucket '%s' exists", self.bucket_name)
        try:
            loc_info = self.resource.meta.client.get_bucket_location(
                Bucket=self.bucket_name
            )
            LOGGER.debug("S3 bucket's response: %s", loc_info)
        except botocore.exceptions.ClientError as err:
            error_code = err.response["Error"]["Code"]
            if error_code != "NoSuchBucket":
                raise StorageException(err)
            LOGGER.info("Creating S3 bucket '%s'", self.bucket_name)
            # LocationConstraint cannot be specified if it us-east-1 because it is the default, see: https://github.com/boto/boto3/issues/125
            if self.region.lower() == "us-east-1":
                self.resource.create_bucket(Bucket=self.bucket_name)
            else:
                self.resource.create_bucket(
                    Bucket=self.bucket_name,
                    CreateBucketConfiguration={"LocationConstraint": self.region},
                )

    @property
    def bucket_name(self):
        return self.bucket or self.space_id

    def browse(self, path):
        LOGGER.debug("Browsing s3://%s/%s on S3 storage", self.bucket_name, path)
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

        objects = self.resource.Bucket(self.bucket_name).objects.filter(Prefix=path)

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
            elif relative_key != "":
                entries.add(relative_key)
                properties[relative_key] = {
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
        obj = self.resource.Bucket(self.bucket_name).objects.filter(Prefix=delete_path)
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
        bucket = self.resource.Bucket(self.bucket_name)

        # strip leading slash on src_path
        src_path = src_path.lstrip("/").rstrip(".")
        dest_path = dest_path.rstrip(".")

        # Directories need to have trailing slashes to ensure they are created
        # on the staging path.
        if not utils.package_is_file(dest_path):
            dest_path = os.path.join(dest_path, "")

        objects = self.resource.Bucket(self.bucket_name).objects.filter(Prefix=src_path)

        for objectSummary in objects:
            dest_file = objectSummary.key.replace(src_path, dest_path, 1)
            self.space.create_local_directory(dest_file)
            if not os.path.isdir(dest_file):
                bucket.download_file(objectSummary.key, dest_file)

    def move_from_storage_service(self, src_path, dest_path, package=None):
        self._ensure_bucket_exists()
        bucket = self.resource.Bucket(self.bucket_name)

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
