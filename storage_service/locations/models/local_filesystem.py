from __future__ import absolute_import
# stdlib, alphabetical
import datetime
import os

# Core Django, alphabetical
from django.db import models

# Third party dependencies, alphabetical

# This project, alphabetical

# This module, alphabetical
from .location import Location


class LocalFilesystem(models.Model):
    """ Spaces found in the local filesystem of the storage service."""
    space = models.OneToOneField('Space', to_field='uuid')

    class Meta:
        verbose_name = "Local Filesystem"
        app_label = 'locations'

    ALLOWED_LOCATION_PURPOSE = [
        Location.AIP_RECOVERY,
        Location.AIP_STORAGE,
        Location.DIP_STORAGE,
        Location.CURRENTLY_PROCESSING,
        Location.STORAGE_SERVICE_INTERNAL,
        Location.TRANSFER_SOURCE,
        Location.BACKLOG,
    ]

    def move_to_storage_service(self, src_path, dest_path, dest_space):
        """ Moves src_path to dest_space.staging_path/dest_path. """
        # Archivematica expects the file to still be on disk even after stored
        self.space.create_local_directory(dest_path)
        return self.space.move_rsync(src_path, dest_path)

    def move_from_storage_service(self, source_path, destination_path):
        """ Moves self.staging_path/src_path to dest_path. """
        self.space.create_local_directory(destination_path)
        return self.space.move_rsync(source_path, destination_path, try_mv_local=True)

    def verify(self):
        """ Verify that the space is accessible to the storage service. """
        # TODO run script to verify that it works
        verified = os.path.isdir(self.space.path)
        self.space.verified = verified
        self.space.last_verified = datetime.datetime.now()
