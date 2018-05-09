"""
Integration with DSpace, using the REST API.

Space path can be left empty, and the Location path should be the collection's
IRI.

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
import jsonfield

# This project, alphabetical

# This module, alphabetical
from common import utils
from .location import Location

LOGGER = logging.getLogger(__name__)


class DSpace(models.Model):
    """Integration with DSpace using the REST API."""
    space = models.OneToOneField('Space', to_field='uuid')
    sd_iri = models.URLField(max_length=256, verbose_name=_l("Service Document IRI"), # This is redundant for the REST
        help_text=_l('URL of the service document. E.g. http://demo.dspace.org/swordv2/servicedocument'))
    user = models.CharField(max_length=64, verbose_name=_l("User"), help_text=_l('DSpace username to authenticate as'))
    password = models.CharField(max_length=64, verbose_name=_l("Password"),
                                help_text=_l('DSpace password to authenticate with'))
    metadata_policy = jsonfield.JSONField(
        blank=True, null=True, default=[],
        verbose_name=_l('Restricted metadata policy'),
        help_text=_l(
            'Policy for restricted access metadata policy. '
            'Must be specified as a list of objects in JSON. '
            'This will override existing policies. '
            'Example: [{"action":"READ","groupId":"5","rpType":"TYPE_CUSTOM"}]'))

    ARCHIVE_FORMAT_ZIP = 'ZIP'
    ARCHIVE_FORMAT_7Z = '7Z'
    ARCHIVE_FORMAT_CHOICES = (
        (ARCHIVE_FORMAT_ZIP, 'ZIP'),
        (ARCHIVE_FORMAT_7Z, '7z'),
    )
    archive_format = models.CharField(max_length=3, choices=ARCHIVE_FORMAT_CHOICES,
                                      default=ARCHIVE_FORMAT_ZIP, verbose_name=_l('Archive format'))

    sword_connection = None

    class Meta:
        verbose_name = _l("DSpace via REST API")
        app_label = 'locations'

    ALLOWED_LOCATION_PURPOSE = [
        Location.AIP_STORAGE,
    ]

    def __str__(self):
        return 'space: {s.space_id}; sd_iri: {s.sd_iri}; user: {s.user}'.format(s=self)

    def browse(self, path):
        raise NotImplementedError(_('Dspace does not implement browse'))

    def delete_path(self, delete_path):
        raise NotImplementedError(_('DSpace does not implement deletion'))

    def move_to_storage_service(self, src_path, dest_path, dest_space):
        """ Moves src_path to dest_space.staging_path/dest_path. """
        LOGGER.warning('move_to_storage_service called but not implemented.')
        raise NotImplementedError(_('DSpace does not implement fetching packages'))

    def _get_metadata(self, input_path, aip_uuid):
        """Get metadata for DSpace from METS file."""

        # Extract METS file
        # TODO Should output dir be a temp dir?
        output_dir = os.path.dirname(input_path) + '/'
        dirname = os.path.splitext(os.path.basename(input_path))[0]
        relative_mets_path = os.path.join(dirname, 'data', 'METS.' + aip_uuid + '.xml')
        mets_path = os.path.join(output_dir, relative_mets_path)
        command = ['unar', '-force-overwrite', '-o', output_dir, input_path, relative_mets_path]
        try:
            subprocess.check_call(command)
        except subprocess.CalledProcessError:
            LOGGER.error('Could not extract %s from %s', mets_path, input_path, exc_info=True)
            return {}

        # Fetch info
        root = etree.parse(mets_path)
        find_mets = 'mets:structMap/mets:div/mets:div[@LABEL="objects"]'
        dmdid = root.find(find_mets, namespaces=utils.NSMAP).attrib.get('DMDID', '')
        find_mets = 'mets:dmdSec[@ID="' + dmdid + '"]/mets:mdWrap/mets:xmlData/dcterms:dublincore'
        dc = root.find(find_mets, namespaces=utils.NSMAP)

        if dc is None:
            LOGGER.warning('Could not find SIP level Dublin Core metadata in %s', input_path)
            metadata = [self._format_metadata('dc.title', 'No metadata found')]
        else:
            # Create mapping
            metadata = [
                self._format_metadata('dcterms.description', dc.findtext('dc:description', namespaces=utils.NSMAP)),
                self._format_metadata('dcterms.creator', dc.findtext('dc:creator', namespaces=utils.NSMAP)),
                self._format_metadata('dcterms.issued', dc.findtext('dc:date', namespaces=utils.NSMAP)),
                self._format_metadata('dcterms.rights', dc.findtext('dc:rights', namespaces=utils.NSMAP)),
                self._format_metadata('dcterms.relation', dc.findtext('dc:relation', namespaces=utils.NSMAP)),
                self._format_metadata('dc.title', dc.findtext('dc:title', namespaces=utils.NSMAP)),
            ]
            LOGGER.debug('Dublin Core insert metadata for DSpace: %s', metadata)
        os.remove(mets_path)
        return metadata

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
        except OSError as e:
            LOGGER.error('Is %s installed? %s', command[0], e)
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

    # Logs in to DSpace 6 REST API
    # REST API Authentication changed in DSpace 6.x.  It now uses a JSESSIONID cookie.
    # The previous (5.x) authentication scheme using a rest-dspace-token is no longer supported.
    # https://wiki.duraspace.org/display/DSDOC6x/REST+API#RESTAPI-Index/Authentication
    def _login_to_rest(self, dspace_url):
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

        return set_cookie[set_cookie.find('=') + 1:]

    def move_from_storage_service(self, source_path, destination_path, package=None):
        LOGGER.info('source_path: %s, destination_path: %s, package: %s', source_path, destination_path, package)
        if package is None:
            LOGGER.warning('DSpace requires package param')
            return

        # This only handles compressed AIPs
        if not os.path.isfile(source_path):
            raise NotImplementedError(_('Storing in DSpace does not support uncompressed AIPs'))

        # Item to be created in DSpace
        item = {
            "type": "item",
            "metadata": self._get_metadata(source_path, package.uuid)
        }

        # Headers for connecting to DSpace REST API
        headers = {
            'Accept': 'application/json',
            "Content-Type": 'application/json',
        }

        parsed_url = urlparse.urlparse(self.sd_iri)
        dspace_url = urlparse.urlunparse((parsed_url.scheme, parsed_url.netloc, '', '', '', ''))\
            .replace('http:', 'https:') # Make sure https is used

        # Hard-coded collection for now
        collection_url = dspace_url + '/rest/collections/541fd622-8a8a-42db-80fd-81437c69945d/items'

        sessionid = _login_to_rest(self, dspace_url)

        # Create item in DSpace
        response = requests.post(collection_url, headers=headers, cookies={'JSESSIONID': sessionid},
                                 data=json.dumps(item), verify=False)

        # We need the response item to be able to get UUID for new DSpace item
        dspace_item = json.loads(response.text)

        LOGGER.info('Response: %s', response.text)

        LOGGER.info('DSpace UUID: %s', dspace_item['uuid'])

        # Split package
        upload_paths = self._split_package(source_path)

        for root, dirs, files in os.walk(upload_paths[0]):
            for name in files:
                with open(os.path.join(root, name), 'r') as f:
                    content = f.read()

                bitstream_url = dspace_url + '/rest/items/' + dspace_item['uuid'] +\
                                '/bitstreams?name=' + urllib.quote(name)

                response = requests.post(bitstream_url, headers=headers, cookies={'JSESSIONID': sessionid},
                                         data=content, verify=False)
                LOGGER.info('Path: %s', root)
                LOGGER.debug('%s being sent to %s', name, bitstream_url)
        # Deleting path where objects were unpacked using _split_package() method
        shutil.rmtree(upload_paths[0])

        with open(upload_paths[1], 'r') as f:
            content = f.read()

        bitstream_url = dspace_url + '/rest/items/' + dspace_item['uuid'] +\
                        '/bitstreams?name=' + urllib.quote(os.path.basename(upload_paths[1]))

        response = requests.post(bitstream_url, headers=headers, cookies={'JSESSIONID': sessionid},
                                 data=content, verify=False)
        LOGGER.debug('Dest: %s', bitstream_url)

        # Logout from DSpace API
        url = dspace_url + '/rest/logout'
        try:
            requests.post(url, headers=headers, cookies={'JSESSIONID': sessionid}, verify=False)
            LOGGER.info('Logged out of REST API.')
        except Exception:
            LOGGER.info('Error logging out of DSpace REST API', exc_info=True)

