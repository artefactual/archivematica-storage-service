import json
import logging
import os
import subprocess
import time

from common import utils
from django.db import models
from django.utils.translation import gettext_lazy as _

from . import StorageException
from .location import Location

LOGGER = logging.getLogger(__name__)


class RClone(models.Model):
    """Space for storing packages in a variety of systems using rclone."""

    space = models.OneToOneField("Space", to_field="uuid", on_delete=models.CASCADE)

    remote_name = models.CharField(
        max_length=64,
        verbose_name=_("Remote Name"),
        blank=True,
        help_text=_("Must match rclone environment variables"),
    )
    container = models.CharField(
        max_length=64,
        verbose_name=_("Bucket or Container Name"),
        blank=True,
        help_text=_("S3 bucket or object store container name"),
    )

    class Meta:
        verbose_name = _("RClone")
        app_label = _("locations")

    MAX_RETRIES = 5
    RETRIABLE_EXIT_CODES = (5,)

    ALLOWED_LOCATION_PURPOSE = [
        Location.AIP_STORAGE,
        Location.DIP_STORAGE,
        Location.REPLICATOR,
        Location.TRANSFER_SOURCE,
    ]

    def _execute_rclone_subcommand(self, subcommand):
        """Execute rclone subcommand.

        Retriable errors from rclone (indicated by exit code 5) will be
        attempted up to five times, waiting two seconds in between each
        attempt.

        :param subcommand: command to execute (list)

        :returns: stdout returned by rclone
        :throws: StorageException on non-zero, non-5 exit code or after
            5 attempts at retriable errors.
        """
        cmd = ["rclone"] + subcommand
        attempt = 0
        while attempt < self.MAX_RETRIES:
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True,
                )
                (stdout, stderr) = proc.communicate()

                LOGGER.debug("rclone cmd: %s", cmd)
                LOGGER.debug("rclone stdout: %s", stdout)
                if stderr:
                    LOGGER.warning("rclone stderr: %s", stderr)

                # Handle retriable error.
                if proc.returncode in self.RETRIABLE_EXIT_CODES:
                    attempt += 1
                    if attempt >= self.MAX_RETRIES:
                        err_msg = "rclone failed to succesfully run command after {} attempts".format(
                            self.MAX_RETRIES
                        )
                        LOGGER.error(err_msg)
                        raise StorageException(err_msg)

                    LOGGER.warning(
                        "rclone command failed with retriable error. Trying again."
                    )
                    time.sleep(2)
                    continue
                # Handle non-retriable error.
                elif proc.returncode != 0:
                    raise StorageException(
                        "rclone returned non-zero return code: %s. stderr: %s",
                        proc.returncode,
                        stderr,
                    )
                return stdout
            except FileNotFoundError as err:
                err_msg = f"rclone executable not found at path. Details: {err}"
                LOGGER.error(err_msg)
                raise StorageException(err_msg)
            except Exception as err:
                err_msg = "Error running rclone command. Command called: {}. Details: {}".format(
                    cmd, err
                )
                LOGGER.error(err_msg)
                raise StorageException(err_msg)

    @property
    def remote_prefix(self):
        """Return remote prefix from env vars matching case-insensitive RClone.remote_name."""
        SUFFIXED_SPACE_REMOTE_NAME = self.remote_name.lower().rstrip(":") + ":"
        remotes = self._execute_rclone_subcommand(["listremotes"])
        remotes_list = remotes.split("\n")
        for remote in remotes_list:
            if remote == SUFFIXED_SPACE_REMOTE_NAME:
                LOGGER.debug("rclone remote selected: %s", remote)
                return remote
        raise StorageException("rclone remote matching %s not found", self.remote_name)

    def _ensure_container_exists(self):
        """Ensure that the S3 bucket or other container exists by asking it
        something about itself. If we cannot retrieve metadata about it then
        we attempt to create the bucket, else, we raise a StorageException.
        """
        LOGGER.debug("Test that container '%s' exists", self.container)
        prefixed_container_name = f"{self.remote_prefix}{self.container}"
        cmd = ["ls", prefixed_container_name]
        try:
            self._execute_rclone_subcommand(cmd)
        except StorageException:
            LOGGER.info("Creating container '%s'", self.container)
            create_container_cmd = ["mkdir", prefixed_container_name]
            try:
                self._execute_rclone_subcommand(create_container_cmd)
            except StorageException:
                err_msg = "Unable to find or create container {}".format(
                    prefixed_container_name
                )
                LOGGER.error(err_msg)
                raise StorageException(err_msg)

    def browse(self, path):
        """Browse RClone location."""
        LOGGER.debug("Browsing //%s/%s in RClone Space", self.container, path)
        path = path.lstrip("/")

        container = ""
        if self.container:
            self._ensure_container_exists()
            container = os.path.join(self.container, "")

        prefixed_path = f"{self.remote_prefix}{container}{path}"
        cmd = ["lsjson", prefixed_path]
        stdout = self._execute_rclone_subcommand(cmd)

        directories = set()
        entries = set()
        properties = {}

        try:
            objects = json.loads(stdout)
        except json.decoder.JSONDecodeError:
            raise StorageException("Unable to decode JSON from rclone lsjson")

        for object_ in objects:
            name = object_.get("Name")

            entries.add(name)

            is_dir = object_.get("IsDir")
            if is_dir and is_dir is True:
                directories.add(name)
                properties[name] = {
                    "timestamp": object_.get("ModTime"),
                }
            else:
                properties[name] = {
                    "size": object_.get("Size"),
                    "timestamp": object_.get("ModTime"),
                    "mimetype": object_.get("MimeType"),
                }

        return {
            "directories": list(directories),
            "entries": list(entries),
            "properties": properties,
        }

    def delete_path(self, delete_path):
        """Delete package."""
        if delete_path.startswith(os.sep):
            LOGGER.info(
                "Rclone path to delete {} begins with {}; removing from path prior to deletion".format(
                    delete_path, os.sep
                )
            )
            delete_path = delete_path.lstrip(os.sep)

        container = ""
        if self.container:
            self._ensure_container_exists()
            container = os.path.join(self.container, "")

        cmd = [
            "delete",
            "{}{}{}".format(self.remote_prefix, container, delete_path.lstrip("/")),
        ]
        self._execute_rclone_subcommand(cmd)

    def move_to_storage_service(self, src_path, dest_path, dest_space):
        """Moves src_path to dest_space.staging_path/dest_path."""
        # strip leading slash on src_path
        src_path = src_path.rstrip(".").lstrip("/")
        dest_path = dest_path.rstrip(".")

        subcommand = "copyto"
        if not utils.package_is_file(src_path):
            subcommand = "copy"

        container = ""
        if self.container:
            self._ensure_container_exists()
            container = os.path.join(self.container, "")

        # Directories need to have trailing slashes to ensure they are created
        # on the staging path.
        if not utils.package_is_file(dest_path):
            dest_path = os.path.join(dest_path, "")

        cmd = [
            subcommand,
            f"{self.remote_prefix}{container}{src_path}",
            dest_path,
        ]
        self._execute_rclone_subcommand(cmd)

    def move_from_storage_service(self, src_path, dest_path, package=None):
        """Moves self.staging_path/src_path to dest_path."""
        dest_path = dest_path.lstrip("/")

        if not self.container:
            self.space.create_local_directory(dest_path)
        subcommand = "copyto"
        if not utils.package_is_file(src_path):
            subcommand = "copy"

        container = ""
        if self.container:
            self._ensure_container_exists()
            container = os.path.join(self.container, "")

        cmd = [
            subcommand,
            src_path,
            f"{self.remote_prefix}{container}{dest_path}",
        ]
        self._execute_rclone_subcommand(cmd)
