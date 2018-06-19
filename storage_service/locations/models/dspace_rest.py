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
    rest_url = models.URLField(max_length=256, verbose_name=_l("REST URL "),
        help_text=_l('URL of the REST API. E.g. http://demo.dspace.org/rest'))
    user = models.CharField(max_length=64, verbose_name=_l("User"), help_text=_l('DSpace username to authenticate as'))
    password = models.CharField(max_length=64, verbose_name=_l("Password"), help_text=_l('DSpace password to authenticate with'))

    ARCHIVE_FORMAT_ZIP = 'ZIP'
    ARCHIVE_FORMAT_7Z = '7Z'
    ARCHIVE_FORMAT_CHOICES = (
        (ARCHIVE_FORMAT_ZIP, 'ZIP'),
        (ARCHIVE_FORMAT_7Z, '7z'),
    )
    archive_format = models.CharField(max_length=3, choices=ARCHIVE_FORMAT_CHOICES, default=ARCHIVE_FORMAT_ZIP, verbose_name=_l('Archive format'))

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
        LOGGER.warning('move_to_storage_service called but not implemented.')
        raise NotImplementedError(_('DSpace does not implement fetching packages'))

    def _getDMDIDs(self, parentObj, dmdids=None):
        if parentObj is not None:
            if dmdids is None:
                dmdids = {}
            for obj in parentObj:
                if obj.get('DMDID'):
                    dmdids[obj.get('DMDID')] = obj.get('LABEL')
                self._getDMDIDs(obj, dmdids)
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

        dmdids = self._getDMDIDs(root.find("//mets:structMap[@ID='structMap_1']/", namespaces=utils.NSMAP))
        inv_dmdids = {v: k for k, v in dmdids.iteritems()}
        LOGGER.info('Dmdids: %s', dmdids)
        metadata = []
        repository_collections = {}
        package_title = ''

        if 'objects' in inv_dmdids:
            for anId in str(inv_dmdids['objects']).split(' '):
                dc_metadata = root.find('mets:dmdSec[@ID="' + anId + '"]/mets:mdWrap/mets:xmlData/dcterms:dublincore', namespaces=utils.NSMAP)#recurIter(dmdSec, None, 'MDTYPE
                other_metadata = root.find('mets:dmdSec[@ID="' + anId + '"]/mets:mdWrap[@MDTYPE="OTHER"]/mets:xmlData', namespaces=utils.NSMAP)#recurIter(dmdSec, None, 'MDTYPE', 'OTHER')

                if other_metadata is not None:
                    repository_collections['dspace_dip_collection'] = other_metadata.findtext('dspace_dip_collection')
                    repository_collections['dspace_aip_collection'] = other_metadata.findtext('dspace_aip_collection')
                    repository_collections['archivesspace_dip_collection'] = other_metadata.findtext('archivesspace_dip_collection')
                    repository_collections['archivesspace_aip_collection'] = other_metadata.findtext('archivesspace_aip_collection')
                elif dc_metadata is not None:
                    for md in dc_metadata:
                        dc_term = str(md.tag)[str(md.tag).find('}') + 1:]

                        if dc_term == 'title':
                            dc_term = 'dc.' + dc_term
                            package_title = dc_metadata.findtext(md.tag, namespaces=utils.NSMAP)
                        else:
                            dc_term = 'dcterms.' + dc_term

                        metadata.append(self._format_metadata(dc_term, dc_metadata.findtext(md.tag, namespaces=utils.NSMAP)))

        if len(metadata) == 0: # We have nothing and therefore filename becomes title
            LOGGER.warning('Could not find SIP level Dublin Core metadata in %s', input_path)
            metadata = [self._format_metadata('dc.title', dirname[:dirname.find(aip_uuid)-1].replace('_', ' ').title())]
            #metadata = [self._format_metadata('dc.title', 'No metadata found')]
            LOGGER.info('Metadata: %s', metadata)

        os.remove(mets_path)
        return metadata, repository_collections, package_title

    def _archive(self, src, dst):
        """
        Combine a number of files into one archive file.

        `dst` is the path of the archive file. The file extension must not be
        included, instead this function will return the final destination with
        the extension on it according to the archive format preferred.
        """
        if self.archive_format == self.ARCHIVE_FORMAT_ZIP:
            dst, command = self._archive_zip(src, dst)
        elif self.archive_format == self.ARCHIVE_FORMAT_7Z:
            dst, command = self._archive_7z(src, dst)
        else:
            raise ValueError('Archive format not supported')

        try:
            subprocess.check_call(command)
        except subprocess.CalledProcessError:
            LOGGER.error('Could not compress %s', src)
            raise

        return dst

    def _archive_zip(self, src, dst):
        """Return the command that creates the ZIP archive file."""
        if not dst.endswith('.zip'):
            dst += '.zip'

        return (dst, [
            '7z', 'a',  # Add
            '-bd',  # Disable percentage indicator
            '-tzip',  # Type of archive
            '-y',  # Assume Yes on all queries
            '-mtc=on',  # Keep timestamps (create, mod, access)
            '-mmt=on',  # Multithreaded
            dst,  # Destination
            src,  # Source
        ])

    def _archive_7z(self, src, dst):
        """Return the command that creates the 7z archive file."""
        if not dst.endswith('.7z'):
            dst += '.7z'

        return (dst, [
            '7z', 'a',  # Add
            '-bd',  # Disable percentage indicator
            '-t7z',  # Type of archive
            '-y',  # Assume Yes on all queries
            '-m0=bzip2',  # Compression method
            '-mtc=on', '-mtm=on', '-mta=on',  # Keep timestamps (create, mod, access)
            '-mmt=on',  # Multithreaded
            dst,  # Destination
            src,  # Source
        ])

    def _split_package(self, input_path):
        """
        Splits the input package into objects and metadata & logs.

        :param str input_path: Path to the input AIP
        :return: List of packages to be stored
        """
        # TODO Should output dir be a temp dir?
        output_dir = os.path.dirname(input_path) + '/'
        dirname = os.path.splitext(os.path.basename(input_path))[0]
        command = ['unar', '-force-overwrite', '-output-directory', output_dir, input_path]
        try:
            LOGGER.info('Contents of %s: %s', output_dir, os.listdir(output_dir))
            p = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            output, err = p.communicate()
            LOGGER.info('Output: %s', output)
            # subprocess.check_call(command)
        except subprocess.CalledProcessError:
            LOGGER.error('Could not extract %s', input_path)
            raise

        # Move objects into their own directory
        objects_dir = os.path.join(output_dir, 'objects')
        metadata_dir = os.path.join(output_dir, dirname)
        os.mkdir(objects_dir)
        for item in os.listdir(os.path.join(metadata_dir, 'data', 'objects')):
            if item in ('metadata', 'submissionDocumentation'):
                continue

            src = os.path.join(metadata_dir, 'data', 'objects', item)
            dst = os.path.join(objects_dir, item)
            os.rename(src, dst)

        # Does this have to be the same compression as before?
        # Compress objects
        # objects_zip = self._archive(objects_dir, os.path.join(output_dir, 'objects'))
        # shutil.rmtree(objects_dir)

        # Compress everything else
        metadata_zip = self._archive(metadata_dir, os.path.join(output_dir, 'metadata'))
        shutil.rmtree(metadata_dir)

        # os.remove(input_path)

        return [objects_dir, metadata_zip]

    # Reformats the metadata for the REST API

    def _format_metadata(self, dc, value):
        return {'key': dc, 'value': value, 'language': ''}

    def move_from_storage_service(self, source_path, destination_path, package=None):
        LOGGER.info('source_path: %s, destination_path: %s, package: %s', source_path, destination_path, package)
        LOGGER.info('Package UUID: %s', package.uuid)
        LOGGER.info('Package type: %s', package.package_type)

        if package is None:
            LOGGER.warning('DSpace requires package param')
            return

        # This only handles compressed AIPs
        #if not os.path.isfile(source_path):
        #    raise NotImplementedError(_('Storing in DSpace does not support uncompressed AIPs'))

        # Item to be created in DSpace

        dspace_collection = '09c098c1-99b1-4130-8337-7733409d39b8'
        package_title = ''

        metadata, repository_collections, package_title = self._get_metadata(source_path, package.uuid, package.package_type)

        if 'dspace_' + package.package_type.lower() + '_collection' in repository_collections:
            dspace_collection = repository_collections['dspace_' + package.package_type.lower() + '_collection']

        LOGGER.info("Repo coll: %s", repository_collections)
        item = {
            "type": "item",
            "metadata": metadata
        }

        LOGGER.info("Item: %s", item)

        # Headers for connecting to DSpace REST API
        headers = {
            'Accept': 'application/json',
            "Content-Type": 'application/json',
        }

        parsed_url = urlparse.urlparse(self.rest_url)
        dspace_url = urlparse.urlunparse((parsed_url.scheme, parsed_url.netloc, '', '', '', '')).replace('http:', 'https:') # Make sure https is used
        collection_url = dspace_url + '/rest/collections/' + dspace_collection + '/items' # Hard-coded collection for nows

        # Log in to get DSpace REST API token
        url = dspace_url + '/rest/login'
        body = {'email': self.user, 'password': self.password}
        try:
            response = requests.post(url, data=body, verify=False)
            LOGGER.info('Logged in to REST API.')
        except Exception:
            LOGGER.warning('Error logging in to DSpace REST API, aborting', exc_info=True)
            return

        set_cookie = response.headers['Set-Cookie'].split(';')[0]

        sessionid = set_cookie[set_cookie.find('=') + 1:]

        # Create item in DSpace
        response = requests.post(collection_url, headers=headers, cookies={'JSESSIONID': sessionid}, data=json.dumps(item), verify=False)

        LOGGER.info("Response: %s", response)
        LOGGER.info("Response text: %s", response.text)

        dspace_item = json.loads(response.text)

        #package.misc_attributes.update({'handle': dspace_item['handle']})
        #package.save()

        LOGGER.info('DSpace UUID: %s', dspace_item['uuid'])

        if package.package_type == 'DIP':
            LOGGER.info('Package is DIP. Splitting package.')
            # Split package
            #upload_paths = self._split_package(source_path)

            for root, dirs, files in os.walk(source_path):
                for name in files:
                    with open(os.path.join(root, name), 'r') as f:
                        content = f.read()

                    newname = name

                    if package.uuid in name:
                        newname = name[len(package.uuid):]

                    bitstream_url = dspace_url + '/rest/items/' + dspace_item['uuid'] + '/bitstreams?name=' + urllib.quote(newname)

                    response = requests.post(bitstream_url, headers=headers, cookies={'JSESSIONID': sessionid}, data=content,
                                 verify=False)
                    LOGGER.info('Path: %s', root)
                    LOGGER.debug('%s being sent to %s', name, bitstream_url)
            shutil.rmtree(source_path)

            client = archivesspace.ArchivesSpaceClient('http://lac-archives-test.is.ed.ac.uk', 'archivematica',
                                                       'arch1vemat1ca', 8089, 14)

            client.add_digital_object('/repositories/14/archival_objects/135569', package.uuid, title=package_title,
                                      uri='https://test.digitalpreservation.is.ed.ac.uk/handle/' + dspace_item['handle'])
            LOGGER.info('ArchivesSpace Client: %s', client)

        else:
            LOGGER.info('Package is AIP. Sending file.')
            with open(source_path, 'r') as f:
                content = f.read()

            bitstream_url = dspace_url + '/rest/items/' + dspace_item['uuid'] + '/bitstreams?name=' + urllib.quote(
                os.path.basename(source_path))

            response = requests.post(bitstream_url, headers=headers, cookies={'JSESSIONID': sessionid}, data=content,
                                     verify=False)
            LOGGER.debug('Dest: %s', bitstream_url)

        # Logout from DSpace API
        url = dspace_url + '/rest/logout'
        try:
            requests.post(url, headers=headers, cookies={'JSESSIONID': sessionid}, verify=False)
            LOGGER.info('Logged out of REST API.')
        except Exception:
            LOGGER.info('Error logging out of DSpace REST API', exc_info=True)

