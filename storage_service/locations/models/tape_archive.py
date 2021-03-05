# -*- coding: utf-8 -*-

"""Tape Archive Space created for the Norwegian Health Archive."""

from __future__ import absolute_import


from django.db import models
from django.utils.translation import ugettext_lazy as _

from .location import Location
from .location_helpers.helpers import create_tar, extract_tar


class TAR(models.Model):
    """Space for storing packages as a Tape Archive File."""

    # Package will use this attribute to determine whether the Space
    # is for storing Tape Archive objects.
    packaged_space = True

    space = models.OneToOneField("Space", to_field="uuid", on_delete=models.CASCADE)

    class Meta:
        verbose_name = _("Tape Archive (TAR) on Local Filesystem")
        app_label = _("locations")

    ALLOWED_LOCATION_PURPOSE = [Location.AIP_STORAGE, Location.REPLICATOR]

    def move_to_storage_service(self, src_path, dest_path, dest_space):
        """ Moves src_path to dest_space.staging_path/dest_path. """
        self.space.create_local_directory(dest_path)
        self.space.move_rsync(src_path, dest_path, try_mv_local=True)
        extract_tar(dest_path)

    def move_from_storage_service(self, src_path, dest_path, package=None):
        """ Moves self.staging_path/src_path to dest_path. """
        self.space.create_local_directory(dest_path)
        self.space.move_rsync(src_path, dest_path)
        create_tar(dest_path)
        if package.should_have_pointer_file():
            """Update the pointer file to represent the TAR packaging."""
