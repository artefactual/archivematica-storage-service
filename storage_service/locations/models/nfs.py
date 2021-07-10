# stdlib, alphabetical
import datetime
import os

# Core Django, alphabetical
from django.db import models
from django.utils.translation import ugettext_lazy as _

# Third party dependencies, alphabetical

# This project, alphabetical

# This module, alphabetical
from .location import Location


class NFS(models.Model):
    """ Spaces accessed over NFS. """

    space = models.OneToOneField("Space", to_field="uuid", on_delete=models.CASCADE)

    # Space.path is the local path
    remote_name = models.CharField(
        max_length=256,
        verbose_name=_("Remote name"),
        help_text=_("Name of the NFS server."),
    )
    remote_path = models.TextField(
        verbose_name=_("Remote path"),
        help_text=_("Path on the NFS server to the export."),
    )
    version = models.CharField(
        max_length=64,
        default="nfs4",
        verbose_name=_("Version"),
        help_text=_(
            "Type of the filesystem, i.e. nfs, or nfs4. \
        Should match a command in `mount`."
        ),
    )
    # https://help.ubuntu.com/community/NFSv4Howto
    manually_mounted = models.BooleanField(
        verbose_name=_("Manually mounted"), default=False
    )

    class Meta:
        verbose_name = _("Network File System (NFS)")
        app_label = "locations"

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
        self.space.create_local_directory(dest_path)
        return self.space.move_rsync(src_path, dest_path)

    def post_move_to_storage_service(self, *args, **kwargs):
        # TODO delete original file?
        pass

    def move_from_storage_service(self, source_path, destination_path, package=None):
        """ Moves self.staging_path/src_path to dest_path. """
        self.space.create_local_directory(destination_path)
        return self.space.move_rsync(source_path, destination_path, try_mv_local=True)

    def save(self, *args, **kwargs):
        self.verify()
        super().save(*args, **kwargs)

    def verify(self):
        """ Verify that the space is accessible to the storage service. """
        # TODO run script to verify that it works
        if self.manually_mounted:
            verified = os.path.ismount(self.space.path)
            self.space.verified = verified
            self.space.last_verified = datetime.datetime.now()

    def mount(self):
        """ Mount the NFS export with the provided info. """
        # sudo mount -t nfs -o proto=tcp,port=2049 192.168.1.133:/export /mnt/
        # sudo mount -t self.version -o proto=tcp,port=2049 self.remote_name:self.remote_path self.space.path
        # or /etc/fstab
        # self.remote_name:self.remote_path   self.space.path   self.version    auto,user  0  0
        # may need to tweak options
        pass

    def posix_move(
        self, source_path, destination_path, destination_space, package=None
    ):
        """
        Move from this POSIX filesystem to another POSIX filesytem; copying
        from self.path/source_path to destination_space.path/destination_path
        bypassing staging.
        """
        destination_space.create_local_directory(destination_path)
        return self.space.move_rsync(source_path, destination_path, try_mv_local=True)
