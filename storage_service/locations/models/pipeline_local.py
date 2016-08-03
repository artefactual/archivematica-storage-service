from __future__ import absolute_import
# stdlib, alphabetical
from datetime import datetime
import logging
import os
import shutil
import re
import subprocess
import tempfile

# Core Django, alphabetical
from django.db import models

# Third party dependencies, alphabetical

# This project, alphabetical
from common import utils

# This module, alphabetical
from .location import Location

LOGGER = logging.getLogger(__name__)


class PipelineLocalFS(models.Model):
    """ Spaces local to the creating machine, but not to the storage service.

    Use case: currently processing locations. """
    space = models.OneToOneField('Space', to_field='uuid')

    remote_user = models.CharField(max_length=64,
        help_text="Username on the remote machine accessible via ssh")
    remote_name = models.CharField(max_length=256,
        help_text="Name or IP of the remote machine.")
    # Space.path is the path on the remote machine

    class Meta:
        verbose_name = "Pipeline Local FS"
        app_label = 'locations'

    ALLOWED_LOCATION_PURPOSE = [
        Location.AIP_RECOVERY,
        Location.AIP_STORAGE,
        Location.DIP_STORAGE,
        Location.CURRENTLY_PROCESSING,
        Location.TRANSFER_SOURCE,
        Location.BACKLOG,
    ]

    def _format_host_path(self, path, user=None, host=None):
        """Formats a remote path suitable for use with rsync."""
        if user is None:
            user = self.remote_user
        if host is None:
            host = self.remote_name

        return "{}@{}:{}".format(user, host, utils.coerce_str(path))

    def browse(self, path):
        path = os.path.join(path, '')
        ssh_path = self._format_host_path(path)
        return self.space.browse_rsync(ssh_path)

    def delete_path(self, delete_path):
        # Sync from an empty directory to delete the contents of delete_path;
        # passing --delete to rsync causes it to delete all contents from the
        # destination path that don't exist in the source which, since it's an
        # empty directory, is everything.
        temp_dir = tempfile.mkdtemp()
        dest_path = self._format_host_path(os.path.join(delete_path, ''))
        command = ['rsync', '-vv', '--itemize-changes', '--protect-args',
                   '--delete', '--dirs',
                   os.path.join(temp_dir, ''),
                   dest_path]
        LOGGER.info("rsync delete command: %s", command)
        try:
            subprocess.check_call(command)
        except Exception:
            LOGGER.warning("rsync delete failed: %s", command, exc_info=True)
            raise
        finally:
            shutil.rmtree(temp_dir)

    def move_to_storage_service(self, src_path, dest_path, dest_space):
        """ Moves src_path to dest_space.staging_path/dest_path. """
        # if dest_space == self:
        #     # If moving within same space, don't bring to storage service
        #     # FIXME dest_path is relative, and intended for staging_path, need
        #     # real destination path - memoize something and retrieve it in
        #     # move_from_storage_service?  Move to self.space.path/dest_path?
        #     command = 'mkdir -p "{dest_dir}" && mv "{src_path}" "{dest_path}"'.format(
        #         dest_dir=os.path.dirname(dest_path),
        #         src_user=self.remote_user, src_host=self.remote_name,
        #         src_path=src_path, dest_path=dest_path,
        #         )
        #     ssh_command = ["ssh", self.remote_user+"@"+self.remote_name, command]
        #     LOGGER.info("ssh+mv command: %s", ssh_command)
        #     try:
        #         subprocess.check_call(ssh_command)
        #     except subprocess.CalledProcessError as e:
        #         LOGGER.warning("ssh+mv failed: %s", e)
        #         raise
        # else:
        src_path = self._format_host_path(src_path)
        self.space.create_local_directory(dest_path)
        return self.space.move_rsync(src_path, dest_path)

    def post_move_to_storage_service(self, *args, **kwargs):
        # TODO delete original file?
        pass

    def move_from_storage_service(self, source_path, destination_path):
        """ Moves self.staging_path/src_path to dest_path. """

        self.space.create_rsync_directory(destination_path, self.remote_user, self.remote_name)

        # Prepend user and host to destination
        destination_path = self._format_host_path(destination_path)

        # Move file
        return self.space.move_rsync(source_path, destination_path)
