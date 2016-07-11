"""
Integration with DSpace, using SWORD2 as the protocol.

Space path can be left empty, and the Location path should be the collection's
IRI.
"""
from __future__ import absolute_import
# stdlib, alphabetical
import logging

# Core Django, alphabetical
from django.db import models

# Third party dependencies, alphabetical
import sword2

# This project, alphabetical

# This module, alphabetical
from .location import Location

LOGGER = logging.getLogger(__name__)


class DSpace(models.Model):
    """Integration with DSpace using the SWORD2 protocol."""
    space = models.OneToOneField('Space', to_field='uuid')
    sd_iri = models.URLField(max_length=256, verbose_name="Service Document IRI",
        help_text='URL of the service document. E.g. http://demo.dspace.org/swordv2/servicedocument')
    user = models.CharField(max_length=64, help_text='DSpace username to authenticate as')
    password = models.CharField(max_length=64, help_text='DSpace password to authenticate with')

    sword_connection = None

    class Meta:
        verbose_name = "DSpace via SWORD2 API"
        app_label = 'locations'

    ALLOWED_LOCATION_PURPOSE = [
        Location.AIP_STORAGE,
    ]

    def __str__(self):
        return 'space: {s.space_id}; sd_iri: {s.sd_iri}; user: {s.user}'.format(s=self)

    def _get_sword_connection(self):
        if self.sword_connection is None:
            LOGGER.debug('Getting sword connection')
            self.sword_connection = sword2.Connection(
                service_document_iri=self.sd_iri,
                download_service_document=True,
                user_name=self.user,
                user_pass=self.password,
                keep_history=True,
                # http_impl=sword2.http_layer.UrlLib2Layer(),  # This causes the deposit receipt to return the wrong URLs
            )
            LOGGER.debug('Getting service document')
            self.sword_connection.get_service_document()

        return self.sword_connection

    def browse(self, path):
        pass

    def delete_path(self, delete_path):
        pass

    def move_to_storage_service(self, src_path, dest_path, dest_space):
        """ Moves src_path to dest_space.staging_path/dest_path. """
        pass

    def move_from_storage_service(self, source_path, destination_path):
        """ Moves self.staging_path/src_path to dest_path. """
        pass
