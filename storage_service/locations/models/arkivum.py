# stdlib, alphabetical
import logging

# Core Django, alphabetical
from django.conf import settings
from django.db import models

# Third party dependencies, alphabetical

# This project, alphabetical

# This module, alphabetical
from location import Location

LOGGER = logging.getLogger(__name__)

if settings.DEBUG:
    VERIFY = False
else:
    VERIFY = True


class Arkivum(models.Model):
    space = models.OneToOneField('Space', to_field='uuid')

    class Meta:
        verbose_name = "Arkivum"
        app_label = 'locations'

    ALLOWED_LOCATION_PURPOSE = [
        Location.AIP_STORAGE,
    ]

    def browse(self, path):
        # This is AIP storage only - do not support browse
        logging.warning('Arkivum does not support browsing')
        return {'directories': [], 'entries': []}

    def delete_path(self, delete_path):
        pass

    def move_to_storage_service(self, src_path, dest_path, dest_space):
        """ Moves src_path to dest_space.staging_path/dest_path. """
        pass

    def move_from_storage_service(self, source_path, destination_path):
        """ Moves self.staging_path/src_path to dest_path. """
        pass

    def update_package_status(self, package):
        pass
