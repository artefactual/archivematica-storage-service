# stdlib, alphabetical
from collections import OrderedDict
import json
import logging
import os
import re
import zipfile

# Core Django, alphabetical
from django.db import models
from django.utils.translation import ugettext_lazy as _

# Third party dependencies, alphabetical
import requests

# This project, alphabetical
LOGGER = logging.getLogger(__name__)

# This module, alphabetical
from . import StorageException  # noqa: E402
from .location import Location  # noqa: E402
from .urlmixin import URLMixin  # noqa: E40


class Dataverse(URLMixin, models.Model):
    space = models.OneToOneField("Space", to_field="uuid", on_delete=models.CASCADE)

    host = models.CharField(
        max_length=256,
        verbose_name=_("Host"),
        help_text=_("Hostname of the Dataverse instance. Eg. apitest.dataverse.org"),
    )
    api_key = models.CharField(
        max_length=50,
        verbose_name=_("API key"),
        help_text=_(
            "API key for Dataverse instance. Eg. "
            "b84d6b87-7b1e-4a30-a374-87191dbbbe2d"
        ),
    )
    agent_name = models.CharField(
        max_length=50,
        verbose_name=_("Agent name"),
        help_text=_("Agent name for premis:agentName in Archivematica"),
    )
    agent_type = models.CharField(
        max_length=50,
        verbose_name=_("Agent type"),
        help_text=_("Agent type for premis:agentType in Archivematica"),
    )
    agent_identifier = models.CharField(
        max_length=256,
        verbose_name=_("Agent identifier"),
        help_text=_(
            "URI agent identifier for premis:agentIdentifierValue " "in Archivematica"
        ),
    )
    # FIXME disallow string in space.path

    class Meta:
        verbose_name = _("Dataverse")
        app_label = "locations"

    ALLOWED_LOCATION_PURPOSE = [Location.TRANSFER_SOURCE]

    @staticmethod
    def get_query_value(key, path, default=None):
        """Retrieve the value corresponding to ``key`` from the string
        ``path``, then remove both the key and the value from path so that we
        can recurse through it for all the key-value pairs used to construct
        a Dataverse query. Finally return the value and path as a 2-tuple.
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
            path = re.sub(re.escape(key) + r"\s*" + re.escape(value), "", path)
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
        query_string, path = self.get_query_value("query:", path, default="*")
        return dataset, subtree, query_string

    def browse(self, path):
        """Fetch the datasets in this dataverse or the files in the dataset
        referenced in ``path``.
        """
        LOGGER.info("Path received: %s", path)
        dataset_id, subtree, query_string = self.get_query_and_subtree(path)
        LOGGER.info(
            "Dataset ID: %s Subtree: %s Query: %s", dataset_id, subtree, query_string
        )
        if dataset_id:
            return self._browse_dataset(dataset_id)
        return self._browse_dataverse(query_string, subtree)

    def _browse_dataverse(self, query_string, subtree):
        """Return all datasets in all Dataverses (conforming to ``browse``
        protocol).
        """
        LOGGER.info("Subtree: %s", subtree)
        LOGGER.info("Query: %s", query_string)
        url = self._generate_dataverse_url(slug="/api/search/")
        params = {
            "key": self.api_key,
            "q": query_string,
            "subtree": subtree,
            "type": "dataset",
            "sort": "name",
            "order": "asc",
            "start": 0,
            "per_page": 50,
            "show_entity_ids": True,
        }
        properties = OrderedDict()
        while True:
            LOGGER.debug("URL: %s, params: %s", url, params)
            response = requests.get(url, params=params)
            LOGGER.debug("Response: %s", response)
            # If the request isn't successful, i.e. doesn't return 200, then
            # raise an exception. Other use cases from Dataverse might need to
            # be considered, but we haven't examples of those as yet to go on
            # and test with. We're only looking for 200 OK at present.
            if response.status_code != 200:
                LOGGER.warning("%s: Response: %s", response, response.text)
                raise StorageException(
                    _("Unable to fetch datasets from %(url)s") % {"url": url}
                )
            try:
                data = response.json()["data"]
                items = data["items"]
            except json.JSONDecodeError:
                LOGGER.error("Could not parse JSON from response to %s", url)
                raise StorageException(
                    _("Unable to parse JSON from response to %(url)s") % {"url": url}
                )
            for ds in items:
                properties[str(ds["entity_id"])] = {"verbose name": ds["name"]}
            if params["start"] + data["count_in_response"] < data["total_count"]:
                params["start"] += data["count_in_response"]
            else:
                break
        entries = list(properties.keys())
        return {"directories": entries, "entries": entries, "properties": properties}

    def _browse_dataset(self, dataset_identifier):
        """Return all files in the dataset with ``entity_id``
        ``dataset_identifier`` (conforming to ``browse`` protocol).
        """
        files_in_dataset_path = (
            "/api/v1/datasets/{dataset_identifier}/versions/:latest".format(
                dataset_identifier=dataset_identifier
            )
        )
        url = self._generate_dataverse_url(slug=files_in_dataset_path)
        params = {"key": self.api_key, "sort": "name", "order": "asc"}
        LOGGER.debug("URL: %s, params: %s", url, params)
        response = requests.get(url, params=params)
        LOGGER.debug("Response: %s", response)
        # If the request isn't successful, i.e. doesn't return 200, then raise
        # an exception. Other use cases from Dataverse might need to be
        # considered, but we haven't examples of those as yet to go on and test
        # with. We're only looking for 200 OK at present.
        if response.status_code != 200:
            LOGGER.warning("%s: Response: %s", response, response.text)
            raise StorageException(
                _("Unable to fetch datasets from %(url)s") % {"url": url}
            )
        try:
            data = response.json()["data"]
            files = data["files"]
        except json.JSONDecodeError:
            LOGGER.error("Could not parse JSON from response to %s", url)
            raise StorageException(
                _("Unable to parse JSON from response to %(url)s") % {"url": url}
            )
        properties = OrderedDict()
        for f in files:
            properties[f["dataFile"]["filename"]] = {"size": f["dataFile"]["filesize"]}
        entries = list(properties.keys())
        return {"directories": [], "entries": entries, "properties": properties}

    def move_to_storage_service(self, src_path, dest_path, dest_space):
        """
        Fetch dataset with ID `src_path` to dest_space.staging_path/dest_path.
        """
        # Strip everything that isn't a number.
        src_path = "".join(c for c in src_path if c.isdigit())
        # Verify src_path has to be a number
        if not src_path.isdigit():
            storage_err = _(
                "Invalid value for src_path: %(value)s. Must be a numeric " "entity_id"
            ) % {"value": src_path}
            raise StorageException(storage_err)
        # Fetch dataset info
        datasets_url = f"/api/datasets/{src_path}"
        url = self._generate_dataverse_url(slug=datasets_url)
        params = {"key": self.api_key}
        LOGGER.debug("URL: %s, params: %s", url, params)
        response = requests.get(url, params=params)
        LOGGER.debug("Response: %s", response)
        if response.status_code != 200:
            raise StorageException(
                _("Unable to fetch dataset %(path)s from %(url)s")
                % {"path": src_path, "url": url}
            )
        try:
            dataset = response.json()["data"]
        except json.JSONDecodeError:
            LOGGER.error("Could not parse JSON from response to %s", url)
            raise StorageException(_("Unable parse JSON from response to %s" % url))

        # Create directories
        self.space.create_local_directory(dest_path)

        # Write out dataset info as dataset.json to the metadata directory
        os.makedirs(os.path.join(dest_path, "metadata"))
        datasetjson_path = os.path.join(dest_path, "metadata", "dataset.json")
        with open(datasetjson_path, "w") as f:
            json.dump(dataset, f, sort_keys=True, indent=4, separators=(",", ": "))

        # Fetch all files in dataset.json
        for file_entry in dataset["latestVersion"]["files"]:
            zipped_bundle = False
            entry_id = str(file_entry["dataFile"]["id"])
            if file_entry["label"].endswith(".tab"):
                # If the file is a tab file, download the bundle instead.
                #
                # A table based dataset ingested into Dataverse is called a
                # Tabular Data File. The .tab file format is downloaded as a
                # 'bundle' from Dataverse. This bundle provides multiple
                # representations in different formats of the same data.
                #
                # A bundle has the property of being a zip file when pulled
                # down by the storage service. We want to extract this bundle
                # below, and allow Archivematica to process other zip files as
                # it would normally (as configured) in the transfer workflow.
                #
                # Integrity checks are completed by the Dataverse
                # microservices.
                zipped_bundle = True
                download_path = os.path.join(
                    dest_path, file_entry["label"][:-4] + ".zip"
                )
                bundle_url = f"/api/access/datafile/bundle/{entry_id}"
                url = self._generate_dataverse_url(slug=bundle_url)
            else:
                download_path = os.path.join(
                    dest_path, file_entry["dataFile"]["filename"]
                )
                datafile_url = f"/api/access/datafile/{entry_id}"
                url = self._generate_dataverse_url(slug=datafile_url)
            LOGGER.debug("URL: %s, params: %s", url, params)
            response = requests.get(url, params=params, stream=True)
            with open(download_path, "wb") as f:
                for chunk in response.iter_content(8192):
                    f.write(chunk)
            if zipped_bundle:
                # The bundle .zip itself is ephemeral, and so once downloaded
                # unzip and remove the container here.
                LOGGER.info("Bundle downloaded. Deleting.")
                self.extract_and_remove_bundle(dest_path, download_path)

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
            json.dump(agent_info, f, sort_keys=True, indent=4, separators=(",", ": "))

    @staticmethod
    def extract_and_remove_bundle(dest_path, bundle_path):
        """Given a bundle from Dataverse, extract the files from the ZIP and
        then remove the original file from the file system.
        """
        try:
            with zipfile.ZipFile(bundle_path, "r") as unzipper:
                unzipper.extractall(dest_path)
                os.unlink(bundle_path)
        except zipfile.BadZipfile as err:
            # Log the error and return without extracting the bundle.
            # Archivematica may still be able to work with the data returned.
            LOGGER.info("Bundle '%s' error: %s", bundle_path, err)
        except OSError as err:
            # Unlink has the potential to also raise an IOError so capture
            # that here.
            LOGGER.info("Issue deleting bundle zip from file system: %s", err)

    def _generate_dataverse_url(self, slug=""):
        """Manage the generation of a URL for various different Dataverse API
        calls.

        Example URLs we are creating might be:
        ```
           url = 'https://<host>/api/search/'
           url = 'https://<host><files_in_dataset>'
           url = "https://<host>/api/datasets/<dataset_path>"
           url = "https://<host>/api/access/datafile/bundle/<id>"
           url = "https://<host/api/access/datafile/<id>"
        ```
        """
        url = f"{self.host}{slug}"
        return self.parse_and_fix_url(url, scheme="https").geturl()
