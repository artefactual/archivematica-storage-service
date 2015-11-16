# stdlib, alphabetical
import logging
import sys

# Core Django, alphabetical
from django.core import validators
from django.db import models

# Third party dependencies, alphabetical
from django_extensions.db.fields import UUIDField
import requests

# This project, alphabetical
from common import utils

# This module, alphabetical
from local_filesystem import LocalFilesystem
from location import Location, LocationPipeline
from managers import Enabled
from space import Space

__all__ = ('Pipeline', )

LOGGER = logging.getLogger(__name__)


class Pipeline(models.Model):
    """ Information about Archivematica instances using the storage service. """
    uuid = UUIDField(unique=True, version=4, auto=False, verbose_name="UUID",
        help_text="Identifier for the Archivematica pipeline",
        validators=[validators.RegexValidator(
            r'\w{8}-\w{4}-\w{4}-\w{4}-\w{12}',
            "Needs to be format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx where x is a hexadecimal digit.",
            "Invalid UUID")])
    description = models.CharField(max_length=256, default=None,
        null=True, blank=True,
        help_text="Human readable description of the Archivematica instance.")
    remote_name = models.CharField(max_length=256, default=None,
        null=True, blank=True,
        help_text="Host or IP address of the pipeline server for making API calls.")
    api_username = models.CharField(max_length=256, default=None,
        null=True, blank=True,
        help_text="Username to use when making API calls to the pipeline.")
    api_key = models.CharField(max_length=256, default=None,
        null=True, blank=True,
        help_text="API key to use when making API calls to the pipeline.")
    enabled = models.BooleanField(default=True,
        help_text="Enabled if this pipeline is able to access the storage service.")

    class Meta:
        verbose_name = "Pipeline"
        app_label = 'locations'

    objects = models.Manager()
    active = Enabled()

    def __unicode__(self):
        return u"{description} ({uuid})".format(
            uuid=self.uuid,
            description=self.description)

    def save(self, create_default_locations=False, shared_path=None, *args, **kwargs):
        """ Save pipeline and optionally create default locations. """
        super(Pipeline, self).save(*args, **kwargs)
        if create_default_locations:
            self.create_default_locations(shared_path)

    def create_default_locations(self, shared_path=None):
        """ Creates default locations for a pipeline based on config.

        Creates a local filesystem Space and currently processing location in
        it.  If a shared_path is provided, currently processing location is at
        that path.  Creates Transfer Source and AIP Store locations based on
        configuration from administration.Settings.
        """
        # Use shared path if provided
        if not shared_path:
            shared_path = '/var/archivematica/sharedDirectory'
        shared_path = shared_path.strip('/') + '/'
        LOGGER.info("Creating default locations for pipeline %s.", self)

        space, space_created = Space.objects.get_or_create(
            access_protocol=Space.LOCAL_FILESYSTEM, path='/')
        if space_created:
            local_fs = LocalFilesystem(space=space)
            local_fs.save()
            LOGGER.info("Protocol Space created: %s", local_fs)
        currently_processing, _ = Location.active.get_or_create(
            purpose=Location.CURRENTLY_PROCESSING,
            defaults={
                'space': space,
                'relative_path': shared_path
            })
        LocationPipeline.objects.get_or_create(
            pipeline=self, location=currently_processing)
        LOGGER.info("Currently processing: %s", currently_processing)

        purposes = [
            {'default': 'default_transfer_source',
             'new': 'new_transfer_source',
             'purpose': Location.TRANSFER_SOURCE},
            {'default': 'default_aip_storage',
             'new': 'new_aip_storage',
             'purpose': Location.AIP_STORAGE},
            {'default': 'default_dip_storage',
             'new': 'new_dip_storage',
             'purpose': Location.DIP_STORAGE},
            {'default': 'default_backlog',
             'new': 'new_backlog',
             'purpose': Location.BACKLOG},
            {'default': 'default_recovery',
             'new': 'new_recovery',
             'purpose': Location.AIP_RECOVERY},
        ]
        for p in purposes:
            defaults = utils.get_setting(p['default'], [])
            for uuid in defaults:
                if uuid == 'new':
                    # Create new location
                    new_location = utils.get_setting(p['new'])
                    location = Location.objects.create(
                        purpose=p['purpose'], **new_location)
                else:
                    # Fetch existing location
                    location = Location.objects.get(uuid=uuid)
                    assert location.purpose == p['purpose']
                LOGGER.info("Adding new %s %s to %s",
                    p['purpose'], location, self)
                LocationPipeline.objects.get_or_create(
                    pipeline=self, location=location)

    # HTTP API CALLS

    def _request_api(self, method, path, fields=None):
        url = 'http://{}/api/{}'.format(
            self.remote_name,
            path.lstrip('/'),
        )
        data = {
            'username': self.api_username,
            'api_key': self.api_key
        }
        if fields:
            data.update(fields)

        LOGGER.debug('URL: %s; data: %s', url, data)
        try:
            resp = requests.request(method, url, data=data, allow_redirects=True)
        except requests.exceptions.RequestException:
            LOGGER.exception('Unable to connect to pipeline %s.', self)
            raise
        else:
            LOGGER.debug('Response: %s %s', resp.status_code, resp.text)
            return resp

    def get_processing_config(self, name):
        """
        Obtain a processing configuration XML document given its name. The
        content is returned as a string. An exception is raised if the
        string is empty.
        """
        url = 'processing-configuration/' + name
        resp = self._request_api('GET', url)
        if resp.status_code != requests.codes.ok:
            raise requests.exceptions.RequestException('Pipeline {} returned an unexpected status code: {}'.format(self, resp.status_code))
        if not resp.text:
            raise requests.exceptions.RequestException('Pipeline {}: empty processing configuration ({}).'.format(self, name))
        return resp.text

    def reingest(self, name, uuid, target='transfer'):
        """
        Approve reingest in the pipeline.
        """
        url = '{}/reingest'.format(target)
        fields = {'name': name, 'uuid': uuid}
        resp = self._request_api('POST', url, fields=fields)
        if resp.status_code != requests.codes.ok:
            try:
                json_error = resp.json().get('message')
                raise requests.exceptions.RequestException('Pipeline {} returned an unexpected status code: {} ({})'.format(self, resp.status_code, json_error))
            except ValueError:  # Failed to decode JSON
                raise requests.exceptions.RequestException('Pipeline {} returned an unexpected status code: {}'.format(self, resp.status_code))
        return resp.json()
