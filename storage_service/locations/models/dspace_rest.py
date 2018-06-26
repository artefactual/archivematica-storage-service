"""
Integration with DSpace, using REST API as the protocol.

NOTE THAT IN ALL REQUESTS TO THE REST API THE SSL VERIFICATION HAS BEEN DISABLED

"""
from __future__ import absolute_import
# stdlib, alphabetical
import json
import logging
import os
import shutil
import subprocess
import urlparse
import urllib

# Core Django, alphabetical
from django.db import models
from django.utils.translation import ugettext as _, ugettext_lazy as _l

# Third party dependencies, alphabetical
from lxml import etree
import requests

# This project, alphabetical
from agentarchives import archivesspace

# This module, alphabetical
from common import utils
from .location import Location

LOGGER = logging.getLogger(__name__)


class DSpaceREST(models.Model):
    """Integration with DSpace using the REST API."""
    space = models.OneToOneField('Space', to_field='uuid')
    rest_url = models.URLField(max_length=256,
                               verbose_name=_l("REST URL "),
                               help_text=_l('URL of the REST API. E.g. http://demo.dspace.org/rest')) # ATTENTION could be with or without slash at end
    user = models.CharField(max_length=64,
                            verbose_name=_l("User"),
                            help_text=_l('DSpace username to authenticate as'))
    password = models.CharField(max_length=64,
                                verbose_name=_l("Password"),
                                help_text=_l('DSpace password to authenticate with'))

    ARCHIVE_FORMAT_ZIP = 'ZIP'
    ARCHIVE_FORMAT_7Z = '7Z'
    ARCHIVE_FORMAT_CHOICES = (
        (ARCHIVE_FORMAT_ZIP, 'ZIP'),
        (ARCHIVE_FORMAT_7Z, '7z'),
    )
    archive_format = models.CharField(max_length=3,
                                      choices=ARCHIVE_FORMAT_CHOICES,
                                      default=ARCHIVE_FORMAT_ZIP,
                                      verbose_name=_l('Archive format'))

    class Meta:
        verbose_name = _l("DSpace via REST API")
        app_label = 'locations'

    ALLOWED_LOCATION_PURPOSE = [
        Location.AIP_STORAGE,
        Location.DIP_STORAGE,
    ]

    def __str__(self):
        return 'space: {s.space_id}; rest_url: {s.rest_url}; user: {s.user}'.format(s=self)

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
                LOGGER.error('Could not extract %s from %s', mets_path, input_path, exc_info=True)
                return {}
        elif package_type == 'DIP':
            for dip_file in os.listdir(input_path):
                if dip_file.startswith('METS') and dip_file.endswith(".xml"):
                    LOGGER.info("Dip file: %s", dip_file)
                    mets_path = os.path.join(input_path, dip_file)

        # Fetch info
        root = etree.parse(mets_path)

        dmdids = self._getdmdids(root.find("//mets:structMap[@ID='structMap_1']/", namespaces=utils.NSMAP))
        inv_dmdids = {v: k for k, v in dmdids.iteritems()}
        #LOGGER.info('Dmdids: %s', dmdids)
        metadata = []
        repos = {}
        package_title = ''

        if 'objects' in inv_dmdids:
            for anId in str(inv_dmdids['objects']).split(' '):
                dc_metadata = root.find('mets:dmdSec[@ID="' + anId + '"]/mets:mdWrap/mets:xmlData/dcterms:dublincore',
                                        namespaces=utils.NSMAP)
                other_metadata = root.find('mets:dmdSec[@ID="' + anId + '"]/mets:mdWrap[@MDTYPE="OTHER"]/mets:xmlData',
                                           namespaces=utils.NSMAP)

                if other_metadata is not None:
                    repos['dspace_dip_collection'] = other_metadata.findtext('dspace_dip_collection')
                    repos['dspace_aip_collection'] = other_metadata.findtext('dspace_aip_collection')
                    repos['archivesspace_dip_collection'] = other_metadata.findtext('archivesspace_dip_collection')
                    repos['archivesspace_aip_collection'] = other_metadata.findtext('archivesspace_aip_collection')
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

        if len(metadata) == 0: # We have nothing and therefore filename becomes title
            LOGGER.warning('Could not find SIP level Dublin Core metadata in %s', input_path)
            metadata = [self._format_metadata('dc.title', dirname[:dirname.find(aip_uuid)-1].replace('_', ' ').title())]
            LOGGER.info('Metadata: %s', metadata)

        os.remove(mets_path)
        return metadata, repos, package_title

    # Reformats the metadata for the REST API

    def _format_metadata(self, dc, value):
        return {'key': dc, 'value': value, 'language': ''}

    def _login_to_dspace_rest(self):
        # Log in to get DSpace REST API token
        body = {'email': self.user, 'password': self.password}
        try:
            response = requests.post(self.rest_url + '/login', data=body, verify=False)
            LOGGER.info('Logged in to REST API.')
        except Exception:
            LOGGER.warning('Error logging in to DSpace REST API, aborting', exc_info=True)
            return

        set_cookie = response.headers['Set-Cookie'].split(';')[0]

        return set_cookie[set_cookie.find('=') + 1:]

    def move_from_storage_service(self, source_path, destination_path, package=None):
        LOGGER.info('source_path: %s, destination_path: %s, package: %s', source_path, destination_path, package)
        LOGGER.info('Package UUID: %s', package.uuid)
        LOGGER.info('Package type: %s', package.package_type)
        self.rest_url = self.rest_url.replace('http:', 'https:')# DSPACE REST API really dislikes http

        if self.rest_url[-1:] == '/':# Get rid of trailing slash
            self.rest_url = self.rest_url[:-1]

        if package is None:
            LOGGER.warning('DSpace requires package param')
            return

        # This only handles compressed AIPs
        #if not os.path.isfile(source_path):
        #    raise NotImplementedError(_('Storing in DSpace does not support uncompressed AIPs'))

        # Item to be created in DSpace

        dspace_collection = '09c098c1-99b1-4130-8337-7733409d39b8'
        archivesspace_collection = '135569'
        package_title = ''

        metadata, repository_collections, package_title = self._get_metadata(source_path,
                                                                             package.uuid,
                                                                             package.package_type)

        if 'dspace_' + package.package_type.lower() + '_collection' in repository_collections:
            dspace_collection = repository_collections['dspace_' + package.package_type.lower() + '_collection']

        if 'archivesspace_' + package.package_type.lower() + '_collection' in repository_collections:
            archivesspace_collection = repository_collections['archivesspace_' + package.package_type.lower()
                                                              + '_collection']

        LOGGER.info("Repo coll: %s", repository_collections)
        item = { # Structure necessary to create DSpace record
            "type": "item",
            "metadata": metadata
        }

        LOGGER.info("Item: %s", item)

        # Headers for connecting to DSpace REST API
        headers = {
            'Accept': 'application/json',
            "Content-Type": 'application/json',
        }

        collection_url = self.rest_url + '/collections/' + dspace_collection + '/items'

        dspace_sessionid = self._login_to_dspace_rest() # Logging in to REST api gives us a session id

        # Create item in DSpace
        try:
            response = requests.post(collection_url,
                                     headers=headers,
                                     cookies={'JSESSIONID': dspace_sessionid},
                                     data=json.dumps(item),
                                     verify=False)
        except Exception:
            LOGGER.error('Could not create record: %s', collection_url)

        dspace_item = response.json()

        LOGGER.info('DSpace item: %s', dspace_item)

        if package.package_type == 'DIP':
            LOGGER.info('Package is DIP. Splitting package.')

            for root, dirs, files in os.walk(source_path):
                for name in files:
                    with open(os.path.join(root, name), 'r') as f:
                        content = f.read()

                    newname = name#name[len(package.uuid):]

                    bitstream_url = self.rest_url + '/items/' + dspace_item['uuid']\
                                    + '/bitstreams?name=' + urllib.quote(newname)

                    try:
                        requests.post(bitstream_url,
                                      headers=headers,
                                      cookies={'JSESSIONID': dspace_sessionid},
                                      data=content,
                                      verify=False)
                        LOGGER.debug('%s successfully sent to %s', name, bitstream_url)
                    except Exception:
                        LOGGER.info('Error sending %s, to %s', name, bitstream_url)

                    #LOGGER.info('Path: %s', root)
            shutil.rmtree(source_path)

            try:
                # Create digital object in ArchivesSpace linking to DIP
                client = archivesspace.ArchivesSpaceClient('http://lac-archives-test.is.ed.ac.uk', 'archivematica',
                                                           'arch1vemat1ca', 8089, 14)
            except Exception:
                LOGGER.error('Could not login to ArchivesSpace server')

            try:
                client.add_digital_object('/repositories/14/archival_objects/' + archivesspace_collection,
                                          package.uuid,
                                          title=package_title,
                                          uri=self.rest_url[:-4] + '/handle/' + dspace_item['handle'])
            except Exception:
                LOGGER.error('Could not add digital object to ArchivesSpace')

            LOGGER.info('ArchivesSpace Client: %s', client)
            LOGGER.info('URL: %s', self.rest_url[:-4] + '/handle/' + dspace_item['handle'])

        else:
            LOGGER.info('Package is AIP. Sending file.')
            with open(source_path, 'r') as f:
                content = f.read()

            bitstream_url = self.rest_url + '/items/' + dspace_item['uuid'] + '/bitstreams?name=' + urllib.quote(
                os.path.basename(source_path))

            try:
                requests.post(bitstream_url,
                              headers=headers,
                              cookies={'JSESSIONID': dspace_sessionid},
                              data=content,
                              verify=False)
                LOGGER.debug('%s successfully sent to %s', source_path, bitstream_url)
            except Exception:
                LOGGER.info('Error sending %s, to %s', source_path, bitstream_url)

            #LOGGER.debug('Dest: %s', bitstream_url)

            # Send AIP to Tivoli Storage Manager using command-line client
            command = ['dsmc', 'archive', source_path]
            try:
                LOGGER.info('Command: %s', command)
                LOGGER.info('IS file: %s', os.path.isfile(source_path))
                p = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                output, err = p.communicate()
                LOGGER.info('Output: %s', output)
            except OSError:
                LOGGER.error('Could not run %s', command[0], exc_info=True)
            except subprocess.CalledProcessError:
                LOGGER.error('Could not archive %s using %s', source_path, command[0], exc_info=True)

        # Logout from DSpace API
        url = self.rest_url + 'logout'
        try:
            requests.post(url, headers=headers, cookies={'JSESSIONID': dspace_sessionid}, verify=False)
            LOGGER.info('Logged out of REST API.')
        except Exception:
            LOGGER.info('Error logging out of DSpace REST API', exc_info=True)

