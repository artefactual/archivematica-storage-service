from __future__ import absolute_import
# stdlib, alphabetical
import datetime
import os

# Core Django, alphabetical
from django.db import models

# Third party dependencies, alphabetical
from django_extensions.db.fields import UUIDField

# This project, alphabetical
from .location import Location


class Fedora(models.Model):
    """ Accepts deposits from FEDORA via a SWORD2 server. """
    space = models.OneToOneField('Space', to_field='uuid')

    # Authentication related attributes
    fedora_user = models.CharField(max_length=64,
        help_text="Fedora user name (for SWORD functionality)")
    fedora_password = models.CharField(max_length=256,
        help_text="Fedora password (for SWORD functionality)")
    fedora_name = models.CharField(max_length=256,
        help_text="Name or IP of the remote Fedora machine.")

    class Meta:
        verbose_name = "FEDORA"
        app_label = 'locations'

    ALLOWED_LOCATION_PURPOSE = [
        Location.SWORD_DEPOSIT
    ]

    def save(self, *args, **kwargs):
        self.verify()
        super(Fedora, self).save(*args, **kwargs)

    def verify(self):
        """ Verify that the space is accessible to the storage service. """
        # TODO run script to verify that it works
        verified = os.path.isdir(self.space.path)
        self.space.verified = verified
        self.space.last_verified = datetime.datetime.now()


# For SWORD asynchronous downloading support
class PackageDownloadTask(models.Model):
    uuid = UUIDField(editable=False, unique=True, version=4,
        help_text="Unique identifier")
    package = models.ForeignKey('Package', to_field='uuid')

    downloads_attempted = models.IntegerField(default=0)
    downloads_completed = models.IntegerField(default=0)
    download_completion_time = models.DateTimeField(default=None, null=True, blank=True)

    class Meta:
        verbose_name = "Package Download Task"
        app_label = 'locations'

    def __unicode__(self):
        return u'PackageDownloadTask ID: {uuid} for {package}'.format(
            uuid=self.uuid, package=self.package)

    COMPLETE = 'complete'
    INCOMPLETE = 'incomplete'
    FAILED = 'failed'

    def downloading_status(self):
        """
        In order to determine the downloading status we need to check
        for three possibilities:
        1) The task involved no downloads. The downloads_attempted
           DB row column should be 0. This would be unusual, however,
           as there's no reason to make a task if not attempting
           to download anything.
        2) The task is downloading, but the downloading is not
           yet complete. downloads_attempted is greater than 0, but
           download_completion_time is not set.
        3) The task finished downloading and completed successfully.
           download_completion_time is set. downloads_attempted is
           equal to downloads_completed.
        4) The task finished downloading and completed unsuccessfully.
           download_completion_time is set. downloads_attempted isn't
           equal to downloads_completed.
        """
        if self.downloads_attempted == 0:
            return self.COMPLETE
        elif self.download_completion_time is None:
            return self.INCOMPLETE
        elif self.downloads_attempted == self.downloads_completed:
            return self.COMPLETE
        else:
            return self.FAILED


class PackageDownloadTaskFile(models.Model):
    uuid = UUIDField(editable=False, unique=True, version=4,
        help_text="Unique identifier")
    task = models.ForeignKey('PackageDownloadTask', to_field='uuid', related_name='download_file_set')

    filename = models.CharField(max_length=256)
    url = models.TextField()

    completed = models.BooleanField(default=False,
        help_text="True if file downloaded successfully.")
    failed = models.BooleanField(default=False,
        help_text="True if file failed to download.")

    class Meta:
        verbose_name = "Package Download Task File"
        app_label = 'locations'

    def __unicode__(self):
        return u'Download {filename} from {url} ({status})'.format(
            filename=self.filename,
            url=self.url,
            status=self.downloading_status())

    def downloading_status(self):
        if self.completed:
            return 'complete'
        else:
            if self.failed:
                return 'failed'
            else:
                return 'downloading'
