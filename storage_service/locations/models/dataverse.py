# stdlib, alphabetical
import json
import logging

# Core Django, alphabetical
from django.db import models

# Third party dependencies, alphabetical
import requests

# This project, alphabetical
LOGGER = logging.getLogger(__name__)

# This module, alphabetical
from . import StorageException
from location import Location


class Dataverse(models.Model):
    space = models.OneToOneField('Space', to_field='uuid')
    host = models.CharField(max_length=256,
        help_text='Hostname of the Dataverse instance. Eg. apitest.dataverse.org')
    api_key = models.CharField(max_length=50,
        help_text='API key for Dataverse instance. Eg. b84d6b87-7b1e-4a30-a374-87191dbbbe2d')
    # FIXME disallow string in space.path

    class Meta:
        verbose_name = "Dataverse"
        app_label = 'locations'

    ALLOWED_LOCATION_PURPOSE = [
        Location.TRANSFER_SOURCE,
    ]

    def browse(self, path):
        """
        Fetch a list of datasets from Dataverse based on the query in the location path.

        Datasets are considered directories when browsing.
        """
        # Use http://guides.dataverse.org/en/latest/api/search.html to search and return datasets
        # Location path is query string
        # FIXME only browse one layer deep
        url = 'https://' + self.host + '/api/search/'
        params = {
            'key': self.api_key,
            'q': path,
            'type': 'dataset',
            'sort': 'name',
            'order': 'asc',
            'start': 0,
            'per_page': 10,
            'show_entity_ids': True,
        }
        entries = []
        properties = {}
        while True:
            LOGGER.debug('URL: %s, params: %s', url, params)
            response = requests.get(url, params=params)
            LOGGER.debug('Response: %s', response)
            if response.status_code != 200:
                LOGGER.warning('%s: Response: %s', response, response.text)
                raise StorageException('Unable to fetch datasets from %s with query %s' % (url, path))
            try:
                data = response.json()['data']
            except json.JSONDecodeError:
                LOGGER.error('Could not parse JSON from response to %s', url)
                raise StorageException('Unable parse JSON from response to %s with query %s' % (url, path))

            entries += [str(x['entity_id']) for x in data['items']]

            properties.update({
                str(x['entity_id']): {'verbose name': x['name']}
                for x in data['items']
            })

            if params['start'] + data['count_in_response'] < data['total_count']:
                params['start'] += data['count_in_response']
            else:
                break

        directories = entries
        return {
            'directories': directories,
            'entries': entries,
            'properties': properties,
        }

    def move_to_storage_service(self, src_path, dest_path, dest_space):
        """ Moves src_path to dest_space.staging_path/dest_path. """
        pass
