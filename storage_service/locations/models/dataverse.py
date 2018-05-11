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
from . import StorageException  # noqa: E402
from .location import Location  # noqa: E402


class Dataverse(models.Model):
    space = models.OneToOneField("Space", to_field="uuid")

    host = models.CharField(
        max_length=256,
        verbose_name=_l("Host"),
        help_text=_l(
            "Hostname of the Dataverse instance. Eg. apitest.dataverse.org"
        ),
    )
    api_key = models.CharField(
        max_length=50,
        verbose_name=_l("API key"),
        help_text=_l(
            "API key for Dataverse instance. Eg. "
            "b84d6b87-7b1e-4a30-a374-87191dbbbe2d"
        ),
    )
    agent_name = models.CharField(
        max_length=50,
        verbose_name=_l("Agent name"),
        help_text=_l("Agent name for premis:agentName in Archivematica"),
    )
    agent_type = models.CharField(
        max_length=50,
        verbose_name=_l("Agent type"),
        help_text=_l("Agent type for premis:agentType in Archivematica"),
    )
    agent_identifier = models.CharField(
        max_length=256,
        verbose_name=_l("Agent identifier"),
        help_text=_l(
            "URI agent identifier for premis:agentIdentifierValue "
            "in Archivematica"
        ),
    )
    # FIXME disallow string in space.path

    class Meta:
        verbose_name = _l("Dataverse")
        app_label = "locations"

    ALLOWED_LOCATION_PURPOSE = [Location.TRANSFER_SOURCE]

    def get_query_value(self, key, path, default=None):
        """Retrieve a value from a string and then remove it where it exists so
        that we can recurse through it for all the values we need.
        """
        path = path.lower()
        value = path.split(key.lower(), 1)
        try:
            value = value[1].strip()
        except IndexError:
            value = default
        if value == "":
            value = default
        if value is None:
            path = path.replace(key, "")
        else:
            path = path.replace(value, "").replace(key, "")
        return value, path.strip()

    def get_query_and_subtree(self, path):
        """Split the query string we have received and try and break it into
        components that we can use to populate the transfer tree.

        All the components are optional. We pull them apart right-to-left,
        where a dataset identifier might be provided to us from the transfer
        browser. We can then retrieve the subtree and the query string which
        can be used to return a listing of datasets available in the Dataverse.
        """
        dataset, path = self.get_query_value("/", path)
        subtree, path = self.get_query_value("subtree:", path)
        query_string, path = self.get_query_value(
            "query:", path, "*")
        return dataset, subtree, query_string

    def browse(self, path):
        """Fetch the datasets in this dataverse or the files in the dataset
        referenced in ``path``.
        """
        path = path.rstrip('/').replace(self.space.path, "")\
            .replace("\r\n", " ")
        # Log the path we want to deconstruct now the noise has been removed.
        LOGGER.info("Path received: %s", path)
        dataset_id, subtree, query_string = self.get_query_and_subtree(path)
        LOGGER.info("Dataset ID: %s Subtree: %s Query: %s",
            dataset_id, subtree, query_string)
        if dataset_id:
            return self._browse_dataset(dataset_id)
        else:
            self.query_string = query_string
            self.subtree = subtree
            return self._browse_dataverse()

    def _browse_dataverse(self):
        """Return all datasets in all dataverses (conforming to ``browse``
        protocol).

        Note: we could add a subtree key to the ``params`` dict below to
        restrict this to returning the datasets within a specified dataverse.
        For now, we are not doing that.
        """
        LOGGER.info("Subtree: %s", self.subtree)
        LOGGER.info("Query: %s", self.query_string)
        url = 'https://{}/api/search/'.format(self.host)
        params = {
            'key': self.api_key,
            'q': self.query_string,
            'subtree': self.subtree,
            'type': 'dataset',
            'sort': 'name',
            'order': 'asc',
            'start': 0,
            'per_page': 50,
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
                    _('Unable to fetch datasets from %(url)s')
                    % {'url': url})
            try:
                data = response.json()['data']
                items = data['items']
            except json.JSONDecodeError:
                LOGGER.error('Could not parse JSON from response to %s', url)
                raise StorageException(
                    _('Unable to parse JSON from response to %(url)s')
                    % {'url': url})
            entries += [str(ds['entity_id']) for ds in items]
            properties.update(
                {str(ds['entity_id']): {'verbose name': ds['name']}
                 for ds in items})
            if params['start'] + data['count_in_response'] < data['total_count']:
                params['start'] += data['count_in_response']
            else:
                break
        return {
            'directories': entries,
            'entries': entries,
            'properties': properties,
        }

    def _browse_dataset(self, dataset_identifier):
        """Return all files in the dataset with ``entity_id``
        ``dataset_identifier`` (conforming to ``browse`` protocol).
        """
        files_in_dataset_path = (
            '/api/v1/datasets/{dataset_identifier}/versions/:latest'.format(
                dataset_identifier=dataset_identifier))
        url = 'https://{}{}'.format(self.host, files_in_dataset_path)
        params = {'key': self.api_key}
        LOGGER.debug('URL: %s, params: %s', url, params)
        response = requests.get(url, params=params)
        LOGGER.debug('Response: %s', response)
        if response.status_code != 200:
            LOGGER.warning('%s: Response: %s', response, response.text)
            raise StorageException(
                _('Unable to fetch datasets from %(url)s')
                % {'url': url})
        try:
            data = response.json()['data']
            files = data['files']
        except json.JSONDecodeError:
            LOGGER.error('Could not parse JSON from response to %s', url)
            raise StorageException(
                _('Unable to parse JSON from response to %(url)s')
                % {'url': url})
        entries = [f['dataFile']['filename'] for f in files]
        properties = {
            f['dataFile']['filename']: {'size': f['dataFile']['filesize']}
            for f in files}
        return {
            'directories': [],
            'entries': entries,
            'properties': properties,
        }

    def move_to_storage_service(self, src_path, dest_path, dest_space):
        """
        Fetch dataset with ID `src_path` to dest_space.staging_path/dest_path.
        """
        # TODO how to strip location path if location isn't passed in?
        # HACK strip everything that isn't a number
        src_path = "".join(c for c in src_path if c.isdigit())
        # Verify src_path has to be a number
        if not src_path.isdigit():
            raise StorageException(
                _(
                    "Invalid value for src_path: %(value)s. Must be a "
                    "numberic entity_id"
                )
                % {"value": src_path}
            )
        # Fetch dataset info
        url = "https://{}/api/datasets/{}".format(self.host, src_path)
        params = {"key": self.api_key}
        LOGGER.debug("URL: %s, params: %s", url, params)
        response = requests.get(url, params=params)
        LOGGER.debug("Response: %s", response)
        if response.status_code != 200:
            LOGGER.warning("%s: Response: %s", response, response.text)
            raise StorageException(
                _("Unable to fetch dataset %(path)s from %(url)s")
                % {"path": src_path, "url": url}
            )
        try:
            dataset = response.json()["data"]
        except json.JSONDecodeError:
            LOGGER.error("Could not parse JSON from response to %s", url)
            raise StorageException(
                "Unable parse JSON from response to %s" % url
            )

        # Create directories
        self.space.create_local_directory(dest_path)

        # Write out dataset info as dataset.json to the metadata directory
        os.makedirs(os.path.join(dest_path, "metadata"))
        datasetjson_path = os.path.join(dest_path, "metadata", "dataset.json")
        with open(datasetjson_path, "w") as f:
            json.dump(dataset, f)

        # Fetch all files in dataset.json
        for file_entry in dataset["latestVersion"]["files"]:
            entry_id = str(file_entry["dataFile"]["id"])
            if not file_entry["label"].endswith(".tab"):
                download_path = os.path.join(
                    dest_path, file_entry["dataFile"]["filename"]
                )
                url = "https://{}/api/access/datafile/{}".format(
                    self.host, entry_id
                )
            else:
                # If the file is the tab file, download the bundle instead
                download_path = os.path.join(
                    dest_path, file_entry["label"][:-4] + ".zip"
                )
                url = "https://{}/api/access/datafile/bundle/{}".format(
                    self.host, entry_id
                )
            LOGGER.debug("URL: %s, params: %s", url, params)
            response = requests.get(url, params=params)
            LOGGER.debug("Response: %s", response)
            with open(download_path, "wb") as f:
                f.write(response.content)

        # Add Agent info
        agent_info = [
            {
                "agentIdentifierType": "URI",
                "agentIdentifierValue": self.agent_identifier,
                "agentName": self.agent_name,
                "agentType": self.agent_type,
            }
        ]
        agentjson_path = os.path.join(dest_path, "metadata", "agents.json")
        with open(agentjson_path, "w") as f:
            json.dump(agent_info, f)
