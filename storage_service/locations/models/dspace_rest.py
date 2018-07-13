"""
Integration with DSpace, using REST API as the protocol.

"""
from __future__ import absolute_import
# stdlib, alphabetical
import json
import logging
import os
# import shutil
import subprocess
import urllib

# Core Django, alphabetical
from django.db import models
from django.utils.six.moves.urllib.parse import urlparse
from django.utils.translation import ugettext as _, ugettext_lazy as _l

# Third party dependencies, alphabetical
from lxml import etree
import requests
from requests import RequestException

# This project, alphabetical
from agentarchives import archivesspace

# This module, alphabetical
from common import utils
from .location import Location

LOGGER = logging.getLogger(__name__)


class DSpaceRESTException(Exception):
    pass


class DSpaceREST(models.Model):
    """Integration with DSpace using the REST API."""
    space = models.OneToOneField('Space', to_field='uuid')
    ds_rest_url = models.URLField(max_length=256,
                                  verbose_name=_l("REST URL"),
                                  help_text=_l('URL of the REST API. E.g. http://demo.dspace.org/rest'))

    ds_user = models.CharField(max_length=64,
                               verbose_name=_l("User"),
                               help_text=_l('DSpace username to authenticate as'))

    ds_password = models.CharField(max_length=64,
                                   verbose_name=_l("Password"),
                                   help_text=_l('DSpace password to authenticate with'))

    ds_dip_collection = models.CharField(max_length=64,
                                         verbose_name=_l("Default DSpace DIP collection id"),
                                         help_text=_l('UUID of default DSpace collection for the DIP to be deposited to'))

    ds_aip_collection = models.CharField(max_length=64,
                                         verbose_name=_l("Default DSpace AIP collection id"),
                                         help_text=_l('UUID of default DSpace collection for the AIP to be deposited to'))

    as_url = models.URLField(blank=True,
                             max_length=256,
                             verbose_name=_l("ArchivesSpace URL"),
                             help_text=_l('URL of ArchivesSpace server. E.g. http://sandbox.archivesspace.org:8089/ (default port 8089 if omitted)'))

    as_user = models.CharField(blank=True,
                               max_length=64,
                               verbose_name=_l("ArchivesSpace user"),
                               help_text=_l('ArchivesSpace username to authenticate as'))

    as_password = models.CharField(blank=True,
                                   max_length=64,
                                   verbose_name=_l("ArchivesSpace password"),
                                   help_text=_l('ArchivesSpace password to authenticate with'))

    as_repository = models.CharField(blank=True,
                                     max_length=64,
                                     verbose_name=_l("Default ArchivesSpace repository"),
                                     help_text=_l('Identifier of the default ArchivesSpace repository'))

    as_archival_object = models.CharField(blank=True,
                                          max_length=64,
                                          verbose_name=_l("Default ArchivesSpace archival object"),
                                          help_text=_l('Identifier of the default ArchivesSpace archival object'))

    verify_ssl = models.BooleanField(blank=True, default=True, verbose_name=_l("Verify SSL certificates?"),
                                     help_text=_l("If checked, HTTPS requests will verify the SSL certificates"))

    class Meta:
        verbose_name = _l("DSpace via REST API")
        app_label = 'locations'

    ALLOWED_LOCATION_PURPOSE = [
        Location.AIP_STORAGE,
        Location.DIP_STORAGE,
    ]

    def __str__(self):
        return 'space: {s.space_id}; rest_url: {s.ds_rest_url}; user: {s.user}'.format(s=self)

    def browse(self, path):
        raise NotImplementedError(_('Dspace does not implement browse'))

    def delete_path(self, delete_path):
        raise NotImplementedError(_('DSpace does not implement deletion'))

    def move_to_storage_service(self, src_path, dest_path, dest_space):
        """ Moves src_path to dest_space.staging_path/dest_path. """
        raise NotImplementedError(_('DSpace does not implement fetching packages'))

    def _getdmdids(self, parentobj, dmdids=None):
        if parentobj is not None:
            if dmdids is None:
                dmdids = {}
            for obj in parentobj:
                if obj.get('DMDID'):
                    dmdids[obj.get('DMDID')] = obj.get('LABEL')
                self._getdmdids(obj, dmdids)
            return dmdids

    def _get_metadata(self, input_path, aip_uuid, package_type):
        """Get metadata for DSpace from METS file."""
        output_dir = os.path.dirname(input_path) + '/'
        dirname = os.path.splitext(os.path.basename(input_path))[0]
        mets_path = ''

        if package_type == 'AIP':
            # Extract METS file
            # TODO Should output dir be a temp dir?
            relative_mets_path = os.path.join(dirname, 'data', 'METS.' + aip_uuid + '.xml')
            mets_path = os.path.join(output_dir, relative_mets_path)
            command = ['unar', '-force-overwrite', '-o', output_dir, input_path, relative_mets_path]
            try:
                p = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                output, err = p.communicate()
                LOGGER.info('Output: %s', output)
            except subprocess.CalledProcessError:
                LOGGER.warning('Could not extract {} from {}'.format(mets_path, input_path), exc_info=True)
        elif package_type == 'DIP':
            for dip_file in os.listdir(input_path):
                if dip_file.startswith('METS') and dip_file.endswith(".xml"):
                    LOGGER.info("Dip file: %s", dip_file)
                    mets_path = os.path.join(input_path, dip_file)
                    break

        # Fetch info
        root = etree.parse(mets_path)

        dmdids = {v: k for k, v in self._getdmdids(root.find("//mets:structMap[@ID='structMap_1']/", namespaces=utils.NSMAP)).iteritems()}
        # LOGGER.info('Dmdids: %s', dmdids)
        metadata = []
        repos = {}
        package_title = ''

        if 'objects' in dmdids:
            for anId in str(dmdids['objects']).split(' '):
                dc_metadata = root.find('mets:dmdSec[@ID="' + anId + '"]/mets:mdWrap/mets:xmlData/dcterms:dublincore',
                                        namespaces=utils.NSMAP)
                other_metadata = root.find('mets:dmdSec[@ID="' + anId + '"]/mets:mdWrap[@MDTYPE="OTHER"]/mets:xmlData',
                                           namespaces=utils.NSMAP)

                if other_metadata is not None:
                    repos['dspace_dip_collection'] = other_metadata.findtext('dspace_dip_collection')
                    repos['dspace_aip_collection'] = other_metadata.findtext('dspace_aip_collection')
                    repos['archivesspace_dip_collection'] = other_metadata.findtext('archivesspace_dip_collection')
                elif dc_metadata is not None:
                    for md in dc_metadata:
                        dc_term = str(md.tag)[str(md.tag).find('}') + 1:]

                        if dc_term == 'title':
                            dc_term = 'dc.' + dc_term
                            package_title = dc_metadata.findtext(md.tag, namespaces=utils.NSMAP)
                        else:
                            dc_term = 'dcterms.' + dc_term

                        metadata.append(self._format_metadata(dc_term, dc_metadata.findtext(md.tag,
                                                                                            namespaces=utils.NSMAP)))

        if not metadata:  # We have nothing and therefore filename becomes title
            LOGGER.warning('Could not find SIP level Dublin Core metadata in %s', input_path)
            package_title = dirname[:dirname.find(aip_uuid) - 1].replace('_', ' ').title()
            metadata = [self._format_metadata('dc.title', package_title)]
            LOGGER.info('Metadata: %s', metadata)

        os.remove(mets_path)
        return metadata, repos, package_title

    # Reformats the metadata for the REST API

    @staticmethod
    def _format_metadata(dc, value):
        return {'key': dc, 'value': value, 'language': ''}

    def _login_to_dspace_rest(self):
        # Log in to get DSpace REST API token
        body = {'email': self.ds_user, 'password': self.ds_password}
        rest_url = self.ds_rest_url.scheme + '://' + self.ds_rest_url.netloc + self.ds_rest_url.path
        try:
            response = requests.post(rest_url + '/login', data=body, verify=self.verify_ssl)
            LOGGER.info('Logged in to REST API.')
        except Exception:
            LOGGER.warning('Error logging in to DSpace REST API, aborting', exc_info=True)
            return

        set_cookie = response.headers['Set-Cookie'].split(';')[0]

        return set_cookie[set_cookie.find('=') + 1:]

    def _logout_from_dspace_rest(self, headers, ds_sessionid):
        # Logout from DSpace API
        url = self.ds_rest_url.scheme + '://' + self.ds_rest_url.netloc + self.ds_rest_url.path + 'logout'
        try:
            requests.post(url, headers=headers, cookies={'JSESSIONID': ds_sessionid}, verify=self.verify_ssl)
            LOGGER.info('Logged out of REST API.')
        except Exception:
            LOGGER.warning('Error logging out of DSpace REST API', exc_info=True)

    def _parse_and_clean_urls(self):
        self.ds_rest_url = urlparse(self.ds_rest_url)
        self.as_url = urlparse(self.as_url)

        if self.ds_rest_url.scheme != 'https':
            self.ds_rest_url = self.ds_rest_url._replace(scheme='https')

        if not self.as_url.port:
            self.as_url = self.as_url._replace(netloc=self.as_url.netloc + ":8089")

        if not self.ds_rest_url.port:
            self.ds_rest_url = self.ds_rest_url._replace(netloc=self.ds_rest_url.netloc + ":443")

        LOGGER.info('DS REST Cleaned: %s', self.ds_rest_url)
        LOGGER.info('AS Cleaned: %s', self.as_url)

    def _create_dspace_record(self, headers, metadata, ds_sessionid, ds_collection):
        item = {  # Structure necessary to create DSpace record
            "type": "item",
            "metadata": metadata
        }

        LOGGER.info("Item: %s", item)

        collection_url = self.ds_rest_url.scheme + '://' + self.ds_rest_url.netloc + self.ds_rest_url.path + '/collections/' + ds_collection + '/items'

        # Create item in DSpace
        try:
            response = requests.post(collection_url,
                                     headers=headers,
                                     cookies={'JSESSIONID': ds_sessionid},
                                     data=json.dumps(item),
                                     verify=self.verify_ssl)
        except RequestException:
            msg = 'Could not create DSpace record: {}'.format(collection_url)
            LOGGER.error(msg)
            raise DSpaceRESTException(msg)

        return response.json()

    def _assign_destination(self, package_type, destinations):
        ds_collection = as_archival_obj = None

        if package_type == 'DIP':
            ds_collection = destinations.get('dspace_dip_collection', self.ds_dip_collection)

            as_archival_obj = destinations.get('archivesspace_dip_archival_object', self.as_archival_object)

        elif package_type == 'AIP':
            ds_collection = destinations.get('dspace_aip_collection', self.ds_aip_collection)

        LOGGER.info("Repo coll: %s", destinations)

        return ds_collection, as_archival_obj

    def _deposit_dip_to_dspace(self, source_path, headers, ds_item, ds_sessionid):
        LOGGER.info('Package is DIP. Sending file by file.')
        base_url = self.ds_rest_url.scheme + '://' + self.ds_rest_url.netloc + self.ds_rest_url.path
        base_url += '/items/' + ds_item['uuid']

        for root, __, files in os.walk(source_path):
            for name in files:
                bitstream_url = base_url + '/bitstreams?name=' + urllib.quote(name.encode('utf-8'))

                try:
                    with open(os.path.join(root, name), 'rb') as content:
                        requests.post(bitstream_url,
                                      headers=headers,
                                      cookies={'JSESSIONID': ds_sessionid},
                                      data=content,
                                      verify=self.verify_ssl)
                    LOGGER.debug('%s successfully sent to %s', name, bitstream_url)
                except Exception:
                    msg = 'Error sending {}, to {}'.format(name, bitstream_url)
                    LOGGER.error(msg)
                    raise DSpaceRESTException(msg)

        # shutil.rmtree(source_path)

    def _link_dip_to_archivesspace(self, as_archival_obj, package_uuid, package_title, ds_item):
        try:
            client = archivesspace.ArchivesSpaceClient(self.as_url.scheme + '://' + self.as_url.hostname,
                                                       self.as_user,
                                                       self.as_password,
                                                       self.as_url.port,
                                                       self.as_repository)
        except Exception:
            msg = 'Could not login to ArchivesSpace server: {}, port: {}, user: {}, repository: {}'\
                .format(self.as_url, self.as_url.port, self.as_user, self.as_repository)
            LOGGER.error(msg)
            raise DSpaceRESTException(msg)

        LOGGER.info('ArchivesSpace Client: %s', client)

        try:
            client.add_digital_object('/repositories/' + self.as_repository + '/archival_objects/' + as_archival_obj,
                                      package_uuid,
                                      title=package_title,
                                      uri=self.ds_rest_url.scheme + '://' + self.ds_rest_url.netloc + '/handle/' + ds_item['handle'])
        except RequestException as e:
            LOGGER.error('Could not add digital object to ArchivesSpace')
            if e.response and e.response.status_code == 404:
                msg = 'Either repository {} or archival object {} does not exist'.format(self.as_repository, as_archival_obj)
                raise ValueError(msg)

            msg = 'ArchivesSpace Server error: {}'.format(e.response.text)
            raise DSpaceRESTException(msg)

    def _deposit_aip_to_dspace(self, source_path, headers, ds_item, ds_sessionid):
        LOGGER.info('Package is AIP. Sending file.')

        bitstream_url = self.ds_rest_url.scheme + '://' + self.ds_rest_url.netloc + self.ds_rest_url.path + '/items/'
        bitstream_url += ds_item['uuid'] + '/bitstreams?name=' + urllib.quote(os.path.basename(source_path).encode('utf-8'))

        try:
            with open(source_path, 'rb') as content:
                requests.post(bitstream_url,
                              headers=headers,
                              cookies={'JSESSIONID': ds_sessionid},
                              data=content,
                              verify=self.verify_ssl)
            LOGGER.debug('%s successfully sent to %s', source_path, bitstream_url)
        except Exception:
            msg = 'Error sending {}, to {}'.format(source_path, bitstream_url)
            LOGGER.error(msg)
            raise DSpaceRESTException(msg)

    def move_from_storage_service(self, source_path, destination_path, package=None):
        LOGGER.info('source_path: %s, destination_path: %s, package: %s', source_path, destination_path, package)
        LOGGER.info('Package UUID: %s', package.uuid)
        LOGGER.info('Package type: %s', package.package_type)
        LOGGER.info('Verify SSL: %s', self.verify_ssl)

        if package is None:
            LOGGER.error('DSpace requires package param')
            return

        # This only handles compressed AIPs
        if package.package_type == 'AIP' and not os.path.isfile(source_path):
            raise NotImplementedError(_('Storing in DSpace does not support uncompressed AIPs'))

        self._parse_and_clean_urls()

        # Item to be created in DSpace
        metadata, destinations, package_title = self._get_metadata(source_path, package.uuid, package.package_type)

        ds_collection, as_archival_obj = self._assign_destination(package.package_type, destinations)

        ds_sessionid = self._login_to_dspace_rest()  # Logging in to REST api gives us a session id

        # Headers for connecting to DSpace REST API
        headers = {
            'Accept': 'application/json',
            "Content-Type": 'application/json',
        }

        try:
            ds_item = self._create_dspace_record(headers, metadata, ds_sessionid, ds_collection)

            LOGGER.info('DSpace item: %s', ds_item)

            if package.package_type == 'DIP':
                self._deposit_dip_to_dspace(source_path, headers, ds_item, ds_sessionid)

                if all([self.as_url, self.as_user, self.as_password, self.as_repository, as_archival_obj]):
                    self._link_dip_to_archivesspace(as_archival_obj, package.uuid, package_title, ds_item)

            else:
                self._deposit_aip_to_dspace(source_path, headers, ds_item, ds_sessionid)

                # Send AIP to Tivoli Storage Manager using command-line client
                command = ['dsmc', 'archive', source_path]
                try:
                    LOGGER.info('Command: %s', command)
                    p = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    output, err = p.communicate()
                    LOGGER.info('Output: %s', output)
                except OSError:
                    LOGGER.error('Could not run %s', command[0], exc_info=True)
                except subprocess.CalledProcessError:
                    LOGGER.error('Could not archive %s using %s', source_path, command[0], exc_info=True)
        except DSpaceRESTException as e:
            msg = 'Error depositing to DSpace or ArchiveSpace: {}'.format(e)
            LOGGER.error(msg)
            raise DSpaceRESTException(msg)
        finally:
            self._logout_from_dspace_rest(headers, ds_sessionid)
