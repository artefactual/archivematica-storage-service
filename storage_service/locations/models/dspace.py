"""
Integration with DSpace, using SWORD2 as the protocol.

Space path can be left empty, and the Location path should be the collection's
IRI.
"""
# stdlib, alphabetical
import logging
import mimetypes
import os
import re
import urlparse
import urllib

# Core Django, alphabetical
from django.db import models

# Third party dependencies, alphabetical
import requests
import sword2

# This project, alphabetical

# This module, alphabetical
from location import Location

LOGGER = logging.getLogger(__name__)


class DSpace(models.Model):
    """ Spaces found in the local filesystem of the storage service."""
    space = models.OneToOneField('Space', to_field='uuid')
    sd_iri = models.URLField(max_length=256, verbose_name="Service Document IRI",
        help_text='URL of the service document. E.g. http://demo.dspace.org/swordv2/servicedocument')
    user = models.CharField(max_length=64, help_text='DSpace username to authenticate as')
    password = models.CharField(max_length=64, help_text='DSpace password to authenticate with')

    sword_connection = None

    class Meta:
        verbose_name = "DSpace via SWORD2 API"
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
                keep_history=True,
                # http_impl=sword2.http_layer.UrlLib2Layer(),  # This causes the deposit receipt to return the wrong URLs
            )
            LOGGER.debug('Getting service document')
            self.sword_connection.get_service_document()

        return self.sword_connection

    def browse(self, path):
        pass

    def delete_path(self, delete_path):
        pass

    def move_to_storage_service(self, src_path, dest_path, dest_space):
        """ Moves src_path to dest_space.staging_path/dest_path. """
        pass

    def _split_package(self, input_path):
        """
        Splits the input package into objects and metadata & logs.

        :param str input_path: Path to the input AIP
        :return: List of packages to be stored
        """

        return [input_path]

    def move_from_storage_service(self, source_path, destination_path, package=None):
        LOGGER.info('source_path: %s, destination_path: %s, package: %s', source_path, destination_path, package)
        if package is None:
            LOGGER.warning('DSpace requires package param')
            return

        self._get_sword_connection()
        # Create item by depositing AtoM doc
        # TODO get DC info from METS?
        LOGGER.debug('Create SWORD2 entry')
        entry = sword2.Entry(
            title=os.path.basename(source_path),
            id='archivematica:id:42',  # TODO replace this
            author={'name': 'archivematica'},  # TODO replace this
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

        # Set bitstream permissions for bitstreams attached to handle
        parsed_url = urlparse.urlparse(self.sd_iri)
        dspace_url = urlparse.urlunparse((parsed_url.scheme, parsed_url.netloc, '', '', '', ''))
        url = dspace_url + '/rest/handle/' + handle
        headers = {'Accept': 'application/json'}
        params = {'expand': 'bitstreams'}
        response = requests.get(url, headers=headers, params=params)
        LOGGER.info('REST API handle mapping %s %s', response.status_code, response)
        LOGGER.info('Body %s', response.json())
        for bitstream in response.json()['bitstreams']:
            url = dspace_url + bitstream['link'] + '/policy'
            LOGGER.info('Bitstream policy URL %s', url)
            # # TODO what should a ResourcePolicy look like?
            # body = [{
            #     "action": "READ",
            #     "epersonId": -1,
            #     "groupId": 0,
            #     "resourceId": 47166,
            #     "resourceType": "bitstream",
            #     "rpDescription": None,
            #     "rpName": None,
            #     "rpType": "TYPE_INHERITED",
            #     "startDate": None,
            #     "endDate": None
            # }]

            # requests.post(url, headers=headers, data=body)
