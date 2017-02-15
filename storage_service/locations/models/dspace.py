"""
Integration with DSpace, using SWORD2 as the protocol.

Space path can be left empty, and the Location path should be the collection's
IRI.
"""
from __future__ import absolute_import
# stdlib, alphabetical
import logging
import mimetypes
import os
import re
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
import sword2
import jsonfield

# This project, alphabetical

# This module, alphabetical
from common import utils
from .location import Location

LOGGER = logging.getLogger(__name__)


class DSpace(models.Model):
    """Integration with DSpace using the SWORD2 protocol."""
    space = models.OneToOneField('Space', to_field='uuid')
    sd_iri = models.URLField(max_length=256, verbose_name=_l("Service Document IRI"),
        help_text=_l('URL of the service document. E.g. http://demo.dspace.org/swordv2/servicedocument'))
    user = models.CharField(max_length=64, verbose_name=_l("User"), help_text=_l('DSpace username to authenticate as'))
    password = models.CharField(max_length=64, verbose_name=_l("Password"), help_text=_l('DSpace password to authenticate with'))
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
    archive_format = models.CharField(max_length=3, choices=ARCHIVE_FORMAT_CHOICES, default=ARCHIVE_FORMAT_ZIP, verbose_name=_l('Archive format'))

    sword_connection = None

    class Meta:
        verbose_name = _l("DSpace via SWORD2 API")
        app_label = 'locations'

    ALLOWED_LOCATION_PURPOSE = [
        Location.AIP_STORAGE,
    ]

    def __str__(self):
        return 'space: {s.space_id}; sd_iri: {s.sd_iri}; user: {s.user}'.format(s=self)

    def _get_sword_connection(self):
        if self.sword_connection is None:
            LOGGER.debug('Getting sword connection')
            self.sword_connection = sword2.Connection(
                service_document_iri=self.sd_iri,
                download_service_document=True,
                user_name=self.user,
                user_pass=self.password,
                keep_history=False,
                cache_deposit_receipts=False,
                http_impl=sword2.http_layer.HttpLib2Layer(cache_dir=None)
                # http_impl=sword2.http_layer.UrlLib2Layer(),  # This causes the deposit receipt to return the wrong URLs
            )
            LOGGER.debug('Getting service document')
            self.sword_connection.get_service_document()

        return self.sword_connection

    def browse(self, path):
        raise NotImplementedError(_('Dspace does not implement browse'))

    def delete_path(self, delete_path):
        raise NotImplementedError(_('DSpace does not implement deletion'))

    def move_to_storage_service(self, src_path, dest_path, dest_space):
        """ Moves src_path to dest_space.staging_path/dest_path. """
        raise NotImplementedError(_('DSpace does not implement fetching packages'))

    def _get_metadata(self, input_path, aip_uuid):
        """Get metadata for DSpace from METS file."""
        # Warning: This is specific for Deep Blue, and may not work with generic DSpace

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
        dmdid = root.find('mets:structMap/mets:div/mets:div[@LABEL="objects"]', namespaces=utils.NSMAP).attrib.get('DMDID', '')
        dc = root.find('mets:dmdSec[@ID="' + dmdid + '"]/mets:mdWrap/mets:xmlData/dcterms:dublincore', namespaces=utils.NSMAP)
        if dc is None:
            LOGGER.warning('Could not find SIP level Dublin Core metadata in %s', input_path)
            kwargs = {}
        else:
            # Create mapping
            kwargs = {
                'dcterms_title': dc.findtext('dc:title', namespaces=utils.NSMAP),
                'dcterms_description.abstract': dc.findtext('dc:description', namespaces=utils.NSMAP),
                'dcterms_contributor.author': dc.findtext('dc:creator', namespaces=utils.NSMAP),
                'dcterms_date.issued': dc.findtext('dc:date', namespaces=utils.NSMAP),
                'dcterms_rights.copyright': dc.findtext('dc:rights', namespaces=utils.NSMAP),
                'dcterms_relation.ispartofseries': dc.findtext('dc:relation', namespaces=utils.NSMAP),
            }
            LOGGER.debug('Dublin Core metadata for DSpace: %s', kwargs)
        os.remove(mets_path)
        return kwargs

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
            subprocess.check_call(command)
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
        objects_zip = self._archive(objects_dir, os.path.join(output_dir, 'objects'))
        shutil.rmtree(objects_dir)

        # Compress everything else
        metadata_zip = self._archive(metadata_dir, os.path.join(output_dir, 'metadata'))
        shutil.rmtree(metadata_dir)

        # os.remove(input_path)

        return [objects_zip, metadata_zip]

    def move_from_storage_service(self, source_path, destination_path, package=None):
        LOGGER.info('source_path: %s, destination_path: %s, package: %s', source_path, destination_path, package)
        if package is None:
            LOGGER.warning('DSpace requires package param')
            return

        # This only handles compressed AIPs
        if not os.path.isfile(source_path):
            raise NotImplementedError(_('Storing in DSpace does not support uncompressed AIPs'))

        self._get_sword_connection()
        # Create item by depositing AtoM doc
        LOGGER.debug('Create SWORD2 entry')
        kwargs = self._get_metadata(source_path, package.uuid)
        entry = sword2.Entry(
            title=kwargs.get('dcterms_title'),
            **kwargs
        )

        destination_path = package.current_location.relative_path
        LOGGER.debug('POST SWORD2 entry %s %s', destination_path, entry)
        entry_receipt = self.sword_connection.create(
            col_iri=destination_path,
            in_progress=True,
            metadata_entry=entry,
        )

        # TODO store these in Package.misc_attributes
        LOGGER.info('Edit IRI: %s', entry_receipt.edit)
        LOGGER.info('Edit Media IRI: %s', entry_receipt.edit_media)
        LOGGER.info('Statement IRI: %s', entry_receipt.atom_statement_iri)

        # Split package
        upload_paths = self._split_package(source_path)

        for upload_path in upload_paths:
            LOGGER.info('Add file %s to %s', upload_path, entry_receipt.edit_media)
            # Add file to DSpace item
            with open(upload_path, 'r') as f:
                content = f.read()  # sword2 iterates over this twice

            # Note: This has problems because httplib2 tries all requests using basic auth without any auth and retries after getting a 401. This breaks with files over 2097152 bytes.
            # A possible solution is to use a different http_impl in the connection, but that returns incorrect URIs in the deposit recept
            # LOGGER.debug('Using sword2')
            # self.sword_connection.add_file_to_resource(
            #     edit_media_iri=entry_receipt.edit_media,
            #     payload=content,
            #     filename=os.path.basename(upload_path),
            #     mimetype=mimetypes.guess_type(upload_path),
            # )

            # This replicates the sword2 behaviour but using requests for the basic auth
            LOGGER.debug('Using requests')
            headers = {
                'Content-Type': str(mimetypes.guess_type(upload_path)),
                # 'Content-MD5': str(md5sum),
                'Content-Length': str(os.path.getsize(upload_path)),
                'Content-Disposition': "attachment; filename=%s" % urllib.quote(os.path.basename(upload_path)),
            }
            requests.post(entry_receipt.edit_media, headers=headers, data=content, auth=(self.user, self.password))

        # Finalize deposit
        LOGGER.info('Complete deposit for %s', entry_receipt.edit)
        try:
            complete_receipt = self.sword_connection.complete_deposit(dr=entry_receipt)
        except Exception:
            LOGGER.error('Error creating item: Status: %s, response: %s', self.sword_connection.history[-1]['payload']['response'].status, self.sword_connection.history[-1]['payload']['response'].resp)
            LOGGER.error(self.sword_connection.history[-1])
            raise
        LOGGER.info('Complete receipt: %s', complete_receipt)

        package.current_path = entry_receipt.atom_statement_iri
        package.save()

        # Fetch statement
        LOGGER.info('Request Atom serialisation of the deposit statement from %s', entry_receipt.atom_statement_iri)
        try:
            statement = self.sword_connection.get_atom_sword_statement(entry_receipt.atom_statement_iri)
        except Exception:
            LOGGER.error('Error creating item: Status: %s, response: %s', self.sword_connection.history[-1]['payload']['response'].status, self.sword_connection.history[-1]['payload']['response'].resp)
            LOGGER.error(self.sword_connection.history[-1])
            raise
        LOGGER.info('Statement: %s', statement.xml_document)

        # Get DSpace handle
        regex = r'bitstream/(?P<handle>\d+/\d+)/'  # get Dspace handle regex
        match = re.search(regex, statement.original_deposits[0].id)
        if match:
            LOGGER.info('Handle: %s', match.group('handle'))
            handle = match.group('handle')
        else:
            LOGGER.warning('No match found in %s', statement.original_deposits[0].id)
            return

        package.misc_attributes.update({'handle': handle})
        package.save()

        # Set permissions on metadata bitstreams
        self._set_permissions(package)

    def _set_permissions(self, package):
        try:
            handle = package.misc_attributes['handle']
        except KeyError:
            LOGGER.warning('Cannot update permissions - package handle unknown')
            return

        # Only set if policy exists
        if not self.metadata_policy:
            LOGGER.info('Restricted metadata policy is empty (%s), not setting', self.metadata_policy)
            return

        # Set bitstream permissions for bitstreams attached to handle
        parsed_url = urlparse.urlparse(self.sd_iri)
        dspace_url = urlparse.urlunparse((parsed_url.scheme, parsed_url.netloc, '', '', '', ''))
        # Log in to get DSpace REST API token
        url = dspace_url + '/rest/login'
        body = {'email': self.user, 'password': self.password}
        try:
            response = requests.post(url, json=body)
        except Exception:
            LOGGER.warning('Error logging in to DSpace REST API, aborting', exc_info=True)
            return
        rest_token = response.text

        # Fetch bitstream information for item
        url = dspace_url + '/rest/handle/' + handle
        headers = {
            'Accept': 'application/json',
            'rest-dspace-token': rest_token,
        }
        params = {'expand': 'bitstreams'}
        try:
            response = requests.get(url, headers=headers, params=params)
        except Exception:
            LOGGER.warning('Error fetching bitstream information for handle %s', handle, exc_info=True)
        LOGGER.debug('REST API handle mapping %s %s', response.status_code, response)
        LOGGER.debug('Body %s', response.json())

        # Update bitstream policies & descriptions through REST API
        for bitstream in response.json()['bitstreams']:
            url = dspace_url + bitstream['link']
            LOGGER.debug('Bitstream policy URL %s', url)
            body = bitstream
            if bitstream['name'] == 'metadata.7z':
                # Overwrite existing policies, instead of adding
                body['policies'] = self.metadata_policy
                # Add bitstream description for metadata when depositing to DSpace
                body['description'] = 'Administrative information.'
            elif bitstream['name'] == 'objects.7z':
                # Add bitstream description for objects when depositing to DSpace
                body['description'] = 'Archival materials.'
            else:
                LOGGER.debug('skipping non-metadata bitstream named %s', bitstream['name'])
                continue
            LOGGER.debug('Posting bitstream body %s', body)
            try:
                response = requests.put(url, headers=headers, json=body)
            except Exception:
                LOGGER.warning('Error posting bitstream body', exc_info=True)
                continue
            LOGGER.debug('Response: %s %s', response.status_code, response.text)

        # Logout from DSpace API
        url = dspace_url + '/rest/logout'
        try:
            requests.post(url, headers=headers)
        except Exception:
            LOGGER.info('Error logging out of DSpace REST API', exc_info=True)
        return
