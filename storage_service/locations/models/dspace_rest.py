"""
Integration with DSpace, using REST API as the protocol.

"""

# stdlib, alphabetical
from urllib.parse import quote, urlparse
import json
import logging
import os
import subprocess
import traceback

# Core Django, alphabetical
from django.db import models
from django.utils.translation import ugettext_lazy as _

# Third party dependencies, alphabetical
from lxml import etree
import requests
import scandir
from requests import RequestException

# This project, alphabetical
from agentarchives import archivesspace
from agentarchives.archivesspace.client import CommunicationError

# This module, alphabetical
from common import utils
from .location import Location

LOGGER = logging.getLogger(__name__)


AS_DO_ADD_ERR = "Could not add digital object to ArchivesSpace. "
# Headers for connecting to DSpace REST API
HEADERS = {"Accept": "application/json", "Content-Type": "application/json"}
DS_SCHEME = "https"
DFLT_AS_PORT = 8089
DFLT_DS_PORT = 443


class DSpaceRESTException(Exception):
    def __init__(self, msg, url=None, email=None, exc_info=False):
        msg = [msg]
        if url:
            msg.append(f' Using url "{url}".')
        if email:
            msg.append(f' Using email "{email}".')
        if exc_info:
            msg.append(f" {traceback.format_exc()}")
        super().__init__("".join(msg))


class DSpaceREST(models.Model):
    """Integration with DSpace using the REST API."""

    space = models.OneToOneField("Space", to_field="uuid", on_delete=models.CASCADE)
    ds_rest_url = models.URLField(
        max_length=256,
        verbose_name=_("REST URL"),
        help_text=_("URL of the REST API. E.g. http://demo.dspace.org/rest"),
    )

    ds_user = models.CharField(
        max_length=64,
        verbose_name=_("User"),
        help_text=_("DSpace username to authenticate as"),
    )

    ds_password = models.CharField(
        max_length=64,
        verbose_name=_("Password"),
        help_text=_("DSpace password to authenticate with"),
    )

    ds_dip_collection = models.CharField(
        max_length=64,
        verbose_name=_("Default DSpace DIP collection id"),
        help_text=_(
            "UUID of default DSpace collection for the DIP to be" " deposited to"
        ),
    )

    ds_aip_collection = models.CharField(
        max_length=64,
        verbose_name=_("Default DSpace AIP collection id"),
        help_text=_(
            "UUID of default DSpace collection for the AIP to be" " deposited to"
        ),
    )

    as_url = models.URLField(
        blank=True,
        max_length=256,
        verbose_name=_("ArchivesSpace URL"),
        help_text=_(
            "URL of ArchivesSpace server. E.g."
            " http://sandbox.archivesspace.org:8089/ (default port"
            " 8089 if omitted)"
        ),
    )

    as_user = models.CharField(
        blank=True,
        max_length=64,
        verbose_name=_("ArchivesSpace user"),
        help_text=_("ArchivesSpace username to authenticate as"),
    )

    as_password = models.CharField(
        blank=True,
        max_length=64,
        verbose_name=_("ArchivesSpace password"),
        help_text=_("ArchivesSpace password to authenticate with"),
    )

    as_repository = models.CharField(
        blank=True,
        max_length=64,
        verbose_name=_("Default ArchivesSpace repository"),
        help_text=_("Identifier of the default ArchivesSpace repository"),
    )

    as_archival_object = models.CharField(
        blank=True,
        max_length=64,
        verbose_name=_("Default ArchivesSpace archival object"),
        help_text=_("Identifier of the default ArchivesSpace archival object"),
    )

    verify_ssl = models.BooleanField(
        blank=True,
        default=True,
        verbose_name=_("Verify SSL certificates?"),
        help_text=_("If checked, HTTPS requests will verify the SSL" " certificates"),
    )

    upload_to_tsm = models.BooleanField(
        blank=True,
        default=False,
        verbose_name=_("Send AIP to Tivoli Storage Manager?"),
        help_text=_(
            "If checked, will attempt to send the AIP to the Tivoli"
            " Storage Manager using command-line client dsmc, which"
            " must be installed manually"
        ),
    )

    class Meta:
        verbose_name = _("DSpace via REST API")
        app_label = "locations"

    ALLOWED_LOCATION_PURPOSE = [Location.AIP_STORAGE, Location.DIP_STORAGE]

    def __str__(self):
        return (
            "space: {s.space_id}; rest_url: {s.ds_rest_url}; user:"
            " {s.ds_user}".format(s=self)
        )

    def browse(self, path):
        raise NotImplementedError("Dspace does not implement browse")

    def delete_path(self, delete_path):
        raise NotImplementedError("DSpace does not implement deletion")

    def move_to_storage_service(self, src_path, dest_path, dest_space):
        raise NotImplementedError("DSpace does not implement fetching packages")

    @staticmethod
    def _get_mets_el(package_type, output_dir, input_path, dirname, aip_uuid):
        """Locate, extract (if necessary), XML-parse and return the METS file
        for this package.
        """
        if package_type == "AIP":
            relative_mets_path = os.path.join(
                dirname, "data", "METS." + aip_uuid + ".xml"
            )
            mets_path = os.path.join(output_dir, relative_mets_path)
            command = [
                "unar",
                "-force-overwrite",
                "-o",
                output_dir,
                input_path,
                relative_mets_path,
            ]
            try:
                subprocess.Popen(
                    command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
                ).communicate()
                mets_el = etree.parse(mets_path)
                os.remove(mets_path)
                return mets_el
            except subprocess.CalledProcessError as err:
                raise DSpaceRESTException(
                    "Could not extract {} from {}: {}.".format(
                        mets_path, input_path, err
                    )
                )
        elif package_type == "DIP":
            for dip_file in os.listdir(input_path):
                if dip_file.startswith("METS") and dip_file.endswith(".xml"):
                    mets_path = os.path.join(input_path, dip_file)
                    return etree.parse(mets_path)

    def _analyze_md_els(self, mets_el, dmdids, metadata, repos, package_title):
        """Find metadata elements in ``mets_el`` using id string ``dmdids`` and
        use the data in these elements to modify ``metadata``, ``repos`` and
        ``package_title``, returning these last as a 3-tuple.
        """
        for dmdid in dmdids.split():
            dc_metadata = mets_el.find(
                'mets:dmdSec[@ID="{}"]/mets:mdWrap/mets:xmlData/'
                "dcterms:dublincore".format(dmdid),
                namespaces=utils.NSMAP,
            )
            other_metadata = mets_el.find(
                'mets:dmdSec[@ID="{}"]/mets:mdWrap[@MDTYPE="OTHER"]/'
                "mets:xmlData".format(dmdid),
                namespaces=utils.NSMAP,
            )
            if other_metadata is not None:
                for repo_key in [
                    "dspace_dip_collection",
                    "dspace_aip_collection",
                    "archivesspace_dip_repository",
                    "archivesspace_dip_collection",
                ]:
                    val = other_metadata.findtext(repo_key)
                    if val is not None:
                        repos[repo_key] = val
            elif dc_metadata is not None:
                for md in dc_metadata:
                    dc_term = str(md.tag)[str(md.tag).find("}") + 1 :]
                    if dc_term == "title":
                        dc_term = "dc." + dc_term
                        package_title = md.text
                    else:
                        dc_term = "dcterms." + dc_term
                    metadata.append(self._format_metadata(dc_term, md.text))
        return metadata, repos, package_title

    def _get_metadata(self, input_path, aip_uuid, package_type):
        """Get metadata for DSpace from METS file.

        Returns a 3-tuple consisting of a metadata list, a repos dict and a
        package title string.
        """
        metadata = []
        repos = {}
        package_title = ""
        output_dir = os.path.dirname(input_path) + "/"
        dirname = os.path.splitext(os.path.basename(input_path))[0]

        mets_el = self._get_mets_el(
            package_type, output_dir, input_path, dirname, aip_uuid
        )
        root_objects_el = mets_el.find(
            "//mets:structMap[@TYPE='physical']" "/mets:div/mets:div[@LABEL='objects']",
            namespaces=utils.NSMAP,
        )
        if root_objects_el is None:
            return metadata, repos, package_title
        dmdids = root_objects_el.get("DMDID")
        if not dmdids:
            return metadata, repos, package_title
        metadata, repos, package_title = self._analyze_md_els(
            mets_el, dmdids, metadata, repos, package_title
        )
        if not metadata:  # We have nothing and therefore filename becomes title
            package_title = (
                dirname[: dirname.find(aip_uuid) - 1].replace("_", " ").title()
            )
            metadata = [self._format_metadata("dc.title", package_title)]
        return metadata, repos, package_title

    @staticmethod
    def _format_metadata(dc, value):
        """Reformats the metadata for the REST API."""
        return {"key": dc, "value": value, "language": ""}

    def _login_to_dspace_rest(self):
        """Log in to get DSpace REST API token."""
        body = {"email": self.ds_user, "password": self.ds_password}
        login_url = f"{self._get_base_url(self.ds_rest_url)}/login"
        try:
            response = self._post(login_url, data=body, headers=None)
            response.raise_for_status()
        except requests.HTTPError as err:
            raise DSpaceRESTException(
                "Bad response {} received when attempting to login via the"
                " DSpace REST API: {}.".format(response.status_code, err),
                url=login_url,
                email=self.ds_user,
            )
        except Exception as err:
            raise DSpaceRESTException(
                "Unexpected error encountered when attempting to login via the"
                " DSpace REST API: {}.".format(err),
                url=login_url,
                email=self.ds_user,
            )
        else:
            try:
                set_cookie = response.headers["Set-Cookie"].split(";")[0]
            except KeyError:
                raise DSpaceRESTException(
                    "Unable to login to the DSpace REST API: no"
                    ' "Set-Cookie" in response headers:'
                    " {}.".format(response.headers)
                )
            return set_cookie[set_cookie.find("=") + 1 :]

    def _logout_from_dspace_rest(self, ds_sessionid):
        """Logout from DSpace API."""
        try:
            self._post(
                f"{self._get_base_url(self.ds_rest_url)}/logout",
                cookies={"JSESSIONID": ds_sessionid},
            )
        except Exception as err:
            LOGGER.warning("Failed to log out of DSpace REST API: %s.", err)

    def _parse_and_clean_urls(self):
        self.ds_rest_url = urlparse(self.ds_rest_url)
        self.as_url = urlparse(self.as_url)
        if self.ds_rest_url.scheme != DS_SCHEME:
            self.ds_rest_url = self.ds_rest_url._replace(scheme=DS_SCHEME)
        if not self.as_url.port:
            self.as_url = self.as_url._replace(
                netloc=f"{self.as_url.netloc}:{DFLT_AS_PORT}"
            )
        if not self.ds_rest_url.port:
            self.ds_rest_url = self.ds_rest_url._replace(
                netloc=f"{self.ds_rest_url.netloc}:{DFLT_DS_PORT}"
            )

    def _post(self, url, data=None, cookies=None, headers=HEADERS):
        return requests.post(
            url, cookies=cookies, data=data, headers=headers, verify=self.verify_ssl
        )

    def _create_dspace_record(self, metadata, ds_sessionid, ds_collection):
        # Structure necessary to create DSpace record
        item = {"type": "item", "metadata": metadata}
        collection_url = "{base_url}/collections/{ds_collection}/items".format(
            base_url=self._get_base_url(self.ds_rest_url), ds_collection=ds_collection
        )
        try:  # Create item in DSpace
            response = self._post(
                collection_url,
                cookies={"JSESSIONID": ds_sessionid},
                data=json.dumps(item),
            )
            response.raise_for_status()
            return response.json()
        except RequestException as err:
            raise DSpaceRESTException(
                f"Could not create DSpace record: {collection_url}: {err}."
            )
        except ValueError:
            raise DSpaceRESTException("Not a JSON response.")

    def _assign_destination(self, package_type, destinations):
        ds_collection = as_archival_repo = as_archival_obj = None
        if package_type == "DIP":
            ds_collection = destinations.get(
                "dspace_dip_collection", self.ds_dip_collection
            )
            as_archival_repo = destinations.get(
                "archivesspace_dip_repository", self.as_repository
            )
            as_archival_obj = destinations.get(
                "archivesspace_dip_archival_object", self.as_archival_object
            )
        elif package_type == "AIP":
            ds_collection = destinations.get(
                "dspace_aip_collection", self.ds_aip_collection
            )
        return ds_collection, as_archival_repo, as_archival_obj

    @staticmethod
    def _get_base_url(parsed_url):
        return "{url.scheme}://{url.netloc}{url.path}".format(url=parsed_url)

    def _deposit_dip_to_dspace(self, source_path, ds_item, ds_sessionid):
        base_url = "{}/items/{}".format(
            self._get_base_url(self.ds_rest_url), ds_item["uuid"]
        )
        for root, __, files in scandir.walk(source_path):
            for name in files:
                bitstream_url = "{}/bitstreams?name={}".format(
                    base_url, quote(name.encode("utf-8"))
                )
                try:
                    with open(os.path.join(root, name), "rb") as content:
                        self._post(
                            bitstream_url,
                            data=content,
                            cookies={"JSESSIONID": ds_sessionid},
                        )
                except Exception:
                    raise DSpaceRESTException(
                        f"Error sending {name} to {bitstream_url}."
                    )

    def _get_as_client(self, as_archival_repo):
        try:
            login_url = f"{self.as_url.scheme}://{self.as_url.hostname}"
            return archivesspace.ArchivesSpaceClient(
                login_url,
                self.as_user,
                self.as_password,
                self.as_url.port,
                as_archival_repo,
            )
        except Exception:
            raise DSpaceRESTException(
                "Could not login to ArchivesSpace server: {}, port: {},"
                " user: {}, repository: {}.".format(
                    login_url, self.as_url.port, self.as_user, as_archival_repo
                )
            )

    def _link_dip_to_archivesspace(
        self,
        as_client,
        as_archival_repo,
        as_archival_obj,
        package_uuid,
        package_title,
        ds_item,
    ):
        try:
            as_client.add_digital_object(
                "/repositories/{}/archival_objects/{}".format(
                    as_archival_repo, as_archival_obj
                ),
                package_uuid,
                title=package_title,
                uri="{}://{}/handle/{}".format(
                    self.ds_rest_url.scheme, self.ds_rest_url.netloc, ds_item["handle"]
                ),
            )
        except CommunicationError as err:
            if err.response and err.response.status_code == 404:
                raise DSpaceRESTException(
                    "{}Either repository {} or archival object {} does not"
                    " exist.".format(AS_DO_ADD_ERR, self.as_repository, as_archival_obj)
                )
            raise DSpaceRESTException(
                f"{AS_DO_ADD_ERR}ArchivesSpace Server error: {err}."
            )
        except Exception as err:
            raise DSpaceRESTException(f"ArchivesSpace Server error: {err}.")

    def _deposit_aip_to_dspace(self, source_path, ds_item, ds_sessionid):
        bitstream_url = "{base_url}/items/{uuid}/bitstreams?name={name}".format(
            base_url=self._get_base_url(self.ds_rest_url),
            uuid=ds_item["uuid"],
            name=quote(os.path.basename(source_path).encode("utf-8")),
        )
        try:
            with open(source_path, "rb") as content:
                response = self._post(
                    bitstream_url, data=content, cookies={"JSESSIONID": ds_sessionid}
                )
            response.raise_for_status()
        except Exception:
            raise DSpaceRESTException(
                "Error depositing AIP at {} to DSpace via URL {}.".format(
                    source_path, bitstream_url
                )
            )

    def _handle_dip(
        self,
        source_path,
        ds_item,
        ds_sessionid,
        as_archival_repo,
        as_archival_obj,
        package,
        package_title,
    ):
        self._deposit_dip_to_dspace(source_path, ds_item, ds_sessionid)
        if all(
            [
                self.as_url,
                self.as_user,
                self.as_password,
                self.as_repository,
                as_archival_obj,
            ]
        ):
            self._link_dip_to_archivesspace(
                self._get_as_client(as_archival_repo),
                as_archival_repo,
                as_archival_obj,
                package.uuid,
                package_title,
                ds_item,
            )

    def _handle_aip(self, source_path, ds_item, ds_sessionid):
        self._deposit_aip_to_dspace(source_path, ds_item, ds_sessionid)
        if self.upload_to_tsm:
            self._upload_to_tsm(source_path)

    @staticmethod
    def _upload_to_tsm(source_path):
        """Send AIP to Tivoli Storage Manager using command-line client."""
        command = ["dsmc", "archive", source_path]
        try:
            subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            ).communicate()
        except OSError as err:
            raise DSpaceRESTException(f"Could not run {command[0]}: {err}.")
        except subprocess.CalledProcessError as err:
            raise DSpaceRESTException(
                "Could not archive {} using {}: {}.".format(
                    source_path, command[0], err
                )
            )

    def move_from_storage_service(self, source_path, destination_path, package=None):
        LOGGER.info(
            "source_path: %s, destination_path: %s, package: %s, verify" " SSL: %s",
            source_path,
            destination_path,
            package,
            self.verify_ssl,
        )
        if package is None:
            raise DSpaceRESTException("DSpace requires package param.")
        if package.package_type == "AIP" and not os.path.isfile(source_path):
            raise DSpaceRESTException(
                "Storing in DSpace does not support uncompressed AIPs."
            )
        self._parse_and_clean_urls()
        # Item to be created in DSpace
        metadata, destinations, package_title = self._get_metadata(
            source_path, package.uuid, package.package_type
        )
        ds_collection, as_archival_repo, as_archival_obj = self._assign_destination(
            package.package_type, destinations
        )
        # Logging in to REST api gives us a session id
        ds_sessionid = self._login_to_dspace_rest()
        try:
            ds_item = self._create_dspace_record(metadata, ds_sessionid, ds_collection)
            if package.package_type == "DIP":
                self._handle_dip(
                    source_path,
                    ds_item,
                    ds_sessionid,
                    as_archival_repo,
                    as_archival_obj,
                    package,
                    package_title,
                )
            else:
                self._handle_aip(source_path, ds_item, ds_sessionid)
        finally:
            self._logout_from_dspace_rest(ds_sessionid)
