# stdlib, alphabetical
import logging
import os
import subprocess

# Core Django, alphabetical
from django.db import models

# Third party dependencies, alphabetical

# This project, alphabetical

# This module, alphabetical
from location import Location

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

    def browse(self, path):
        user = self.remote_user
        host = self.remote_name
        private_ssh_key = '/var/lib/archivematica/.ssh/id_rsa'

        # Get entries
        command = 'ls -p -1 "{}"'.format(path.replace('"', '\"'))
        ssh_command = ["ssh", "-i", private_ssh_key, user + "@" + host, command]
        LOGGER.info("ssh+ls command: %s", ssh_command)
        try:
            output = subprocess.check_output(ssh_command)
        except Exception as e:
            LOGGER.warning("ssh+ls failed: %s", e, exc_info=True)
            entries = []
            directories = []
        else:
            entries = output.splitlines()
            directories = [d for d in entries if d.endswith('/')]

        directories = sorted(directories, key=lambda s: s.lower())
        entries = sorted(entries, key=lambda s: s.lower())
        return {'directories': directories, 'entries': entries}

    def delete_path(self, delete_path):
        user = self.remote_user
        host = self.remote_name
        command = 'rm -rf "{}"'.format(delete_path.replace('"', '\"'))
        ssh_command = ["ssh", user + "@" + host, command]
        LOGGER.info("ssh+rm command: %s", ssh_command)
        try:
            subprocess.check_call(ssh_command)
        except Exception:
            LOGGER.warning("ssh+rm failed: %s", ssh_command, exc_info=True)
            raise

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
        src_path = "{user}@{host}:{path}".format(
            user=self.remote_user,
            host=self.remote_name,
            path=src_path)
        self.space._create_local_directory(dest_path)
        return self.space._move_rsync(src_path, dest_path)

    def post_move_to_storage_service(self, *args, **kwargs):
        # TODO delete original file?
        pass

    def move_from_storage_service(self, source_path, destination_path):
        """ Moves self.staging_path/src_path to dest_path. """

        # Need to make sure destination exists
        command = 'mkdir -p {}'.format(os.path.dirname(destination_path))
        ssh_command = ["ssh", self.remote_user + "@" + self.remote_name, command]
        LOGGER.info("ssh+mkdir command: %s", ssh_command)
        try:
            subprocess.check_call(ssh_command)
        except subprocess.CalledProcessError as e:
            LOGGER.warning("ssh+mkdir failed: %s", e)
            raise

        # Prepend user and host to destination
        destination_path = "{user}@{host}:{path}".format(
            user=self.remote_user,
            host=self.remote_name,
            path=destination_path)

        # Move file
        return self.space._move_rsync(source_path, destination_path)

    def post_move_from_storage_service(self, staging_path, destination_path, package):
        # TODO Remove the staging file, since rsync leaves it behind
        pass
