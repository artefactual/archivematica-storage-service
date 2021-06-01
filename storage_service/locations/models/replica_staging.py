# -*- coding: utf-8 -*-
from __future__ import absolute_import
import logging
import os

from django.db import models
from django.utils.translation import ugettext_lazy as _

from common import utils

from .location import Location

LOGGER = logging.getLogger(__name__)


class OfflineReplicaStaging(models.Model):
    """Space for storing packages for write-only offline replication.

    Uncompressed packages in this Space will be packaged as a tarball
    prior to storing.
    """

    packaged_space = True

    space = models.OneToOneField("Space", to_field="uuid", on_delete=models.CASCADE)

    class Meta:
        verbose_name = _("Write-Only Replica Staging on Local Filesystem")
        app_label = _("locations")

    ALLOWED_LOCATION_PURPOSE = [Location.REPLICATOR]

    def browse(self, path):
        raise NotImplementedError(
            _("Write-Only Offline Staging does not implement browse")
        )

    def delete_path(self, delete_path):
        raise NotImplementedError(
            _("Write-Only Offline Staging does not implement deletion")
        )

    def move_to_storage_service(self, src_path, dest_path, dest_space):
        """ Moves src_path to dest_space.staging_path/dest_path. """
        raise NotImplementedError(
            _("Write-Only Offline Staging does not implement fetching packages")
        )

    def move_from_storage_service(self, src_path, dest_path, package=None):
        """ Moves self.staging_path/src_path to dest_path."""
        self.space.create_local_directory(dest_path)
        if not package.is_packaged(src_path):
            return self._store_tar_replica(src_path, dest_path, package)
        self.space.move_rsync(src_path, dest_path)

    def _store_tar_replica(self, src_path, dest_path, package):
        """Create and store TAR replica."""
        tar_src_path = src_path.rstrip("/") + utils.TAR_EXTENSION
        tar_dest_path = dest_path.rstrip("/") + utils.TAR_EXTENSION
        try:
            utils.create_tar(src_path, extension=True)
        except utils.TARException:
            raise
        package.current_path = tar_dest_path
        self.space.move_rsync(tar_src_path, tar_dest_path)

        # Cleanup tar in staging directory
        try:
            os.remove(tar_src_path)
        except OSError as err:
            LOGGER.warning(
                "Unable to delete staged replica {}: {}".format(tar_src_path, err)
            )

        # Cleanup empty directory created by space.create_local_directory.
        os.rmdir(dest_path)
