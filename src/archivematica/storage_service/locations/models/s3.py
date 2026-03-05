import logging
import os
import pprint
import re
import time
from functools import wraps
from urllib.parse import urlparse

import boto3
import botocore
from boto3.s3.transfer import TransferConfig
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from archivematica.storage_service.common import utils
from archivematica.storage_service.locations.models import StorageException
from archivematica.storage_service.locations.models.location import Location

LOGGER = logging.getLogger(__name__)

RETRYABLE_CLIENT_ERRORS = {
    "InternalError",
    "RequestTimeout",
    "RequestTimeoutException",
    "SlowDown",
    "Throttling",
    "ThrottlingException",
    "ServiceUnavailable",
    "PriorRequestNotComplete",
}


def boto_exception(fn):
    @wraps(fn)
    def _inner(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except botocore.exceptions.BotoCoreError as e:
            raise StorageException("AWS error: %r", e)

    return _inner


class S3(models.Model):
    space = models.OneToOneField("Space", to_field="uuid", on_delete=models.CASCADE)
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
        Location.DIP_STORAGE,
        Location.REPLICATOR,
        Location.TRANSFER_SOURCE,
    ]

    @property
    def resource(self):
        if not hasattr(self, "_resource"):
            config = botocore.config.Config(
                connect_timeout=settings.S3_CONNECT_TIMEOUTS,
                read_timeout=settings.S3_READ_TIMEOUTS,
                retries={
                    "mode": settings.S3_RETRY_MODE,
                    "max_attempts": settings.S3_MAX_ATTEMPTS,
                },
            )
            boto_args = {
                "service_name": "s3",
                "region_name": self.region,
                "config": config,
            }
            if not self._is_global_endpoint(self.endpoint_url):
                boto_args["endpoint_url"] = self.endpoint_url
            if self.access_key_id and self.secret_access_key:
                boto_args.update(
                    aws_access_key_id=self.access_key_id,
                    aws_secret_access_key=self.secret_access_key,
                )
            self._resource = boto3.resource(**boto_args)
        return self._resource

    def _is_global_endpoint(self, url):
        return urlparse(url).netloc == "s3.amazonaws.com"

    @property
    def upload_transfer_config(self):
        if not hasattr(self, "_upload_transfer_config"):
            self._upload_transfer_config = TransferConfig(
                use_threads=settings.S3_UPLOAD_USE_THREADS
            )
        return self._upload_transfer_config

    @property
    def download_transfer_config(self):
        if not hasattr(self, "_download_transfer_config"):
            self._download_transfer_config = TransferConfig(
                use_threads=settings.S3_DOWNLOAD_USE_THREADS,
                num_download_attempts=settings.S3_DOWNLOAD_ATTEMPTS,
            )
        return self._download_transfer_config

    def _should_retry_transfer_error(self, err):
        if isinstance(err, botocore.exceptions.BotoCoreError):
            return True
        if isinstance(err, botocore.exceptions.ClientError):
            error = err.response.get("Error", {})
            code = error.get("Code")
            status_code = err.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if code in RETRYABLE_CLIENT_ERRORS:
                return True
            return status_code is not None and status_code >= 500
        return False

    def _run_transfer_with_retries(self, operation_name, fn, *args, **kwargs):
        max_retries = settings.S3_TRANSFER_MAX_RETRIES
        backoff = settings.S3_TRANSFER_RETRY_BACKOFF
        attempts = max_retries + 1

        for attempt in range(1, attempts + 1):
            try:
                return fn(*args, **kwargs)
            except (
                botocore.exceptions.BotoCoreError,
                botocore.exceptions.ClientError,
            ) as err:
                if attempt >= attempts or not self._should_retry_transfer_error(err):
                    raise
                LOGGER.warning(
                    "Retrying S3 %s after attempt %d/%d: %s",
                    operation_name,
                    attempt,
                    attempts,
                    err,
                )
                time.sleep(backoff * attempt)

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
        return self.bucket or str(self.space_id)

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

        directories = set()
        entries = set()
        properties = {}

        client = self.resource.meta.client
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(
            Bucket=self.bucket_name,
            Prefix=path,
            Delimiter="/",
        ):
            for obj in page.get("Contents", []):
                relative_key = obj["Key"].replace(path, "", 1).lstrip("/")
                if relative_key:
                    entries.add(relative_key)
                    properties[relative_key] = {
                        "size": obj["Size"],
                        "timestamp": obj["LastModified"],
                        "e_tag": obj["ETag"],
                    }

            for cp in page.get("CommonPrefixes", []):
                relative_key = cp["Prefix"].replace(path, "", 1).lstrip("/")
                directory_name = re.sub("/.*", "", relative_key)
                if directory_name:
                    directories.add(directory_name)
                    entries.add(directory_name)

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
                f"S3 path to delete {delete_path} begins with {os.sep}; removing from path prior to deletion"
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
            err_str = f"No packages found in S3 at: {delete_path}"
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

        for object_key in self._iter_source_object_keys(src_path):
            dest_file = object_key.replace(src_path, dest_path, 1)
            self.space.create_local_directory(dest_file)
            if not os.path.isdir(dest_file):
                self._run_transfer_with_retries(
                    "download",
                    bucket.download_file,
                    object_key,
                    dest_file,
                    Config=self.download_transfer_config,
                )

    def _iter_source_object_keys(self, src_path):
        client = self.resource.meta.client

        if not src_path.endswith("/"):
            try:
                client.head_object(Bucket=self.bucket_name, Key=src_path)
                yield src_path
                return
            except botocore.exceptions.ClientError as err:
                error_code = err.response.get("Error", {}).get("Code")
                if error_code not in {"404", "NoSuchKey", "NotFound"}:
                    raise

        # If the source is not an exact object key, treat it as a directory prefix.
        prefix = src_path if src_path.endswith("/") else f"{src_path}/"
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket_name, Prefix=prefix):
            for obj in page.get("Contents", []):
                yield obj["Key"]

    def move_from_storage_service(self, src_path, dest_path, package=None):
        self._ensure_bucket_exists()
        bucket = self.resource.Bucket(self.bucket_name)

        if os.path.isdir(src_path):
            # ensure trailing slash on both paths
            src_path = os.path.join(src_path, "")
            dest_path = os.path.join(dest_path, "")

            # strip leading slash on dest_path
            dest_path = dest_path.lstrip("/")

            for path, _dirs, files in os.walk(src_path):
                for basename in files:
                    entry = os.path.join(path, basename)
                    dest = entry.replace(src_path, dest_path, 1)

                    self.upload_object(bucket, dest, entry)

        elif os.path.isfile(src_path):
            # strip leading slash on dest_path
            dest_path = dest_path.lstrip("/")

            self.upload_object(bucket, dest_path, src_path)

        else:
            raise StorageException(
                _("%(path)s is neither a file nor a directory, may not exist")
                % {"path": src_path}
            )

    def upload_object(self, bucket, path, data):
        extra_args = {}
        mtype = utils.get_mimetype(path)
        if mtype:
            extra_args["ContentType"] = mtype

        with open(data, "rb") as d:
            self._run_transfer_with_retries(
                "upload",
                bucket.upload_fileobj,
                d,
                path,
                ExtraArgs=extra_args,
                Config=self.upload_transfer_config,
            )
