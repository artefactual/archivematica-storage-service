from __future__ import absolute_import
# stdlib, alphabetical
import json
import logging
import os

# Core Django, alphabetical
from django.db import models
from django.utils.translation import ugettext as _, ugettext_lazy as _l

# Third party dependencies, alphabetical
import requests

# This project, alphabetical
LOGGER = logging.getLogger(__name__)

# This module, alphabetical
from . import StorageException
from .location import Location


class Dataverse(models.Model):
    space = models.OneToOneField('Space', to_field='uuid')
    host = models.CharField(max_length=256,
        verbose_name=_l('Host'),
        help_text=_l('Hostname of the Dataverse instance. Eg. apitest.dataverse.org'))
    api_key = models.CharField(max_length=50,
        verbose_name=_l('API key'),
        help_text=_l('API key for Dataverse instance. Eg. b84d6b87-7b1e-4a30-a374-87191dbbbe2d'))
    agent_name = models.CharField(max_length=50,
        verbose_name=_l('Agent name'),
        help_text=_l('Agent name for premis:agentName in Archivematica'))
    agent_type = models.CharField(max_length=50,
        verbose_name=_l('Agent type'),
        help_text=_l('Agent type for premis:agentType in Archivematica'))
    agent_identifier = models.CharField(max_length=256,
        verbose_name=_l('Agent identifier'),
        help_text=_l('URI agent identifier for premis:agentIdentifierValue in Archivematica'))
    # FIXME disallow string in space.path

    class Meta:
        verbose_name = _l("Dataverse")
        app_label = 'locations'

    ALLOWED_LOCATION_PURPOSE = [
        Location.TRANSFER_SOURCE,
    ]

    def browse(self, path):
        """
        Fetch a list of datasets from Dataverse based on the query in the location path.

        Datasets are considered directories when browsing.
        """
        # Remove things earlier layers added
        path = path.rstrip('/')
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
                raise StorageException(
                    _('Unable to fetch datasets from %(url)s with query %(path)s') %
                    {'url': url, 'path': path})
            try:
                data = response.json()['data']
            except json.JSONDecodeError:
                LOGGER.error('Could not parse JSON from response to %s', url)
                raise StorageException(
                    _('Unable parse JSON from response to %(url)s with query %(path)s') %
                    {'url': url, 'path': path})

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
        """
        Fetch dataset with ID `src_path` to dest_space.staging_path/dest_path.
        """
        # TODO how to strip location path if location isn't passed in?
        # HACK strip everything that isn't a number
        src_path = ''.join(c for c in src_path if c.isdigit())
        # Verify src_path has to be a number
        if not src_path.isdigit():
            raise StorageException(_('Invalid value for src_path: %(value)s. Must be a numberic entity_id') % {'value': src_path})
        # Fetch dataset info
        url = 'https://' + self.host + '/api/datasets/' + src_path
        params = {
            'key': self.api_key,
        }
        LOGGER.debug('URL: %s, params: %s', url, params)
        response = requests.get(url, params=params)
        LOGGER.debug('Response: %s', response)
        if response.status_code != 200:
            LOGGER.warning('%s: Response: %s', response, response.text)
            raise StorageException(
                _('Unable to fetch dataset %(path)s from %(url)s') %
                {'path': src_path, 'url': url})
        try:
            dataset = response.json()['data']
        except json.JSONDecodeError:
            LOGGER.error('Could not parse JSON from response to %s', url)
            raise StorageException('Unable parse JSON from response to %s' % url,)

        # Create directories
        self.space.create_local_directory(dest_path)

        # Write out dataset info as dataset.json to the metadata directory
        os.makedirs(os.path.join(dest_path, 'metadata'))
        datasetjson_path = os.path.join(dest_path, 'metadata', 'dataset.json')
        with open(datasetjson_path, 'w') as f:
            json.dump(dataset, f)

        # Fetch all files in dataset.json
        for file_entry in dataset['latestVersion']['files']:
            entry_id = str(file_entry['dataFile']['id'])
            if not file_entry['label'].endswith('.tab'):
                download_path = os.path.join(dest_path, file_entry['dataFile']['filename'])
                url = 'https://' + self.host + '/api/access/datafile/' + entry_id
            else:
                # If the file is the tab file, download the bundle instead
                download_path = os.path.join(dest_path, file_entry['label'][:-4] + '.zip')
                url = 'https://' + self.host + '/api/access/datafile/bundle/' + entry_id
            LOGGER.debug('URL: %s, params: %s', url, params)
            response = requests.get(url, params=params)
            LOGGER.debug('Response: %s', response)
            with open(download_path, 'wb') as f:
                f.write(response.content)

        # Add Agent info
        agent_info = [
            {
                'agentIdentifierType': 'URI',
                'agentIdentifierValue': self.agent_identifier,
                'agentName': self.agent_name,
                'agentType': self.agent_type,
            }
        ]
        agentjson_path = os.path.join(dest_path, 'metadata', 'agents.json')
        with open(agentjson_path, 'w') as f:
            json.dump(agent_info, f)
