# stdlib, alphabetical
import logging

# Core Django, alphabetical
from django.db import models

# Third party dependencies, alphabetical

# This project, alphabetical
LOGGER = logging.getLogger(__name__)

# This module, alphabetical
from location import Location


class Dataverse(models.Model):
    space = models.OneToOneField('Space', to_field='uuid')
    host = models.CharField(max_length=256,
        help_text='Hostname of the Dataverse instance. Eg. apitest.dataverse.org')
    api_key = models.CharField(max_length=50,
        help_text='API key for Dataverse instance. Eg. b84d6b87-7b1e-4a30-a374-87191dbbbe2d')

    class Meta:
        verbose_name = "Dataverse"
        app_label = 'locations'

    ALLOWED_LOCATION_PURPOSE = [
        Location.TRANSFER_SOURCE,
    ]

    def browse(self, path):
        pass

    def move_to_storage_service(self, src_path, dest_path, dest_space):
        """ Moves src_path to dest_space.staging_path/dest_path. """
        pass
