# stdlib, alphabetical
import errno
import logging
from lxml import etree
import math
import os
import shutil
import subprocess

# Core Django, alphabetical
from django.core.urlresolvers import reverse
from django.db import models

# Third party dependencies, alphabetical
import sword2

# This project, alphabetical
from common import utils

# This module, alphabetical
from location import Location
from package import Package

LOGGER = logging.getLogger(__name__)


class Lockssomatic(models.Model):
    """ Spaces that store their contents in LOCKSS, via LOCKSS-o-matic. """
    space = models.OneToOneField('Space', to_field='uuid')

    # staging location is Space.path
    au_size = models.BigIntegerField(verbose_name="AU Size", null=True, blank=True,
        help_text="Size in bytes of an Allocation Unit")
    sd_iri = models.URLField(max_length=256, verbose_name="Service Document IRI",
        help_text="URL of LOCKSS-o-matic service document IRI, eg. http://lockssomatic.example.org/api/sword/2.0/sd-iri")
    collection_iri = models.CharField(max_length=256, null=True, blank=True, verbose_name="Collection IRI",
        help_text="URL to post the packages to, eg. http://lockssomatic.example.org/api/sword/2.0/col-iri/12")
    content_provider_id = models.CharField(max_length=32,
        verbose_name='Content Provider ID',
        help_text='On-Behalf-Of value when communicating with LOCKSS-o-matic')
    external_domain = models.URLField(verbose_name='Externally available domain',
        help_text='Base URL for this server that LOCKSS will be able to access.  Probably the URL for the home page of the Storage Service.')
    checksum_type = models.CharField(max_length=64, null=True, blank=True, verbose_name='Checksum type', help_text='Checksum type to send to LOCKSS-o-matic for verification.  Eg. md5, sha1, sha256')
    keep_local = models.BooleanField(blank=True, default=True, verbose_name="Keep local copy?",
        help_text="If checked, keep a local copy even after the AIP is stored in the LOCKSS network.")

    class Meta:
        verbose_name = 'LOCKSS-o-matic'
        app_label = 'locations'

    ALLOWED_LOCATION_PURPOSE = [
        Location.AIP_STORAGE,
    ]

    # Uses the SWORD protocol to talk to LOM
    sword_connection = None
    # Parsed pointer file
    pointer_root = None

    def browse(self, path):
        LOGGER.warning('Lockssomatic does not support browsing')
        return {'directories': [], 'entries': []}

    def move_to_storage_service(self, source_path, destination_path, dest_space):
        """ Moves source_path to dest_space.staging_path/destination_path. """
        # Check if in SS internal, if not then fetch from LOM
        raise NotImplementedError('LOCKSS-o-matic has not implemented retrieval.')

    def move_from_storage_service(self, source_path, destination_path):
        """ Moves self.staging_path/source_path to destination_path. """
        self.space._create_local_directory(destination_path)
        return self.space._move_rsync(source_path, destination_path)

    def post_move_from_storage_service(self, staging_path, destination_path, package):
        # LOCKSS can only save packages in the storage service, since it needs
        # to track information on it over time
        if package is None:
            return
        # Post to Lockss-o-matic with the create resource atom entry
        LOGGER.info('Storing %s in LOCKSS', package.current_path)

        # Update Service Document, including maxUploadSize and Collection IRI
        # If SD cannot be updated, LOM probably down.  Terminate now, as
        # updating LOM can be repeated
        if not self.update_service_document():
            return
        # Split the files and record their locations.  If already split, just
        # returns list of output files
        output_files = self._split_package(package)

        # Create the atom entry XML
        entry, slug = self._create_resource(package, output_files)

        # Post to SWORD2 server
        receipt = self.sword_connection.create(col_iri=self.collection_iri, metadata_entry=entry, suggested_identifier=slug)
        try:
            state_iri = receipt.atom_statement_iri
            edit_iri = receipt.edit
        except AttributeError:
            # If something goes wrong with the parsing, receipt may not be a
            # sword.Deposit_Recipt (might be None, or sword.Error_Document) and
            # may not have the required attributes
            LOGGER.warning('Unable to contact LOCKSS for package %s', package.uuid)
        else:
            LOGGER.info("LOCKSS State IRI for %s: %s", package.uuid, state_iri)
            LOGGER.info("LOCKSS Edit IRI for %s: %s", package.uuid, edit_iri)

            if state_iri and edit_iri:
                misc = {'state_iri': state_iri, 'edit_iri': edit_iri, 'num_files': len(output_files)}
                package.misc_attributes.update(misc)

        package.save()

    def update_package_status(self, package):
        """
        Poll LOM for SWORD statement and update status from response.

        Query the state_iri for this package and parse it for the server states.
        If all are in agreement, add those URLs to the pointer file for each
        LOCKSS chunk.
        """
        status = package.status

        # Need to have state and edit IRI to talk to LOM
        if 'state_iri' not in package.misc_attributes or 'edit_iri' not in package.misc_attributes:
            self.post_move_from_storage_service(None, None, package)

        # After retry - verify that state & edit IRI exist now
        if 'state_iri' not in package.misc_attributes or 'edit_iri' not in package.misc_attributes:
            return (None, 'Unable to contact Lockss-o-matic')

        if not self.sword_connection and not self.update_service_document():
            return (None, 'Error contacting LOCKSS-o-matic.')

        # SWORD2 client has only experimental support for getting SWORD2
        # statements, so implementing the fetch and parse here. (March 2014)
        response = self.sword_connection.get_resource(package.misc_attributes['state_iri'], headers={'Accept': 'application/atom+xml;type=feed'})

        if response.code != 200:
            return (None, 'Error polling LOCKSS-o-matic for SWORD statement.')

        statement_root = etree.fromstring(response.content)

        # TODO Check that number of lom:content entries is same as number of chunks
        # TODO what to do if was quorum, and now not??

        # Package not safely stored, return immediately
        servers = statement_root.findall('.//lom:server', namespaces=utils.NSMAP)
        LOGGER.info('All states are agreement: %s', all(s.get('state') == 'agreement' for s in servers))
        if not all(s.get('state') == 'agreement' for s in servers):
            # TODO update pointer file for new failed status?
            return (status, 'LOCKSS servers not in agreement')

        status = Package.UPLOADED

        # Add LOCKSS URLs to each chunk
        if not self.pointer_root:
            self.pointer_root = etree.parse(package.full_pointer_file_path)
        files = self.pointer_root.findall(".//mets:fileSec/mets:fileGrp[@USE='LOCKSS chunk']/mets:file", namespaces=utils.NSMAP)
        # If not files, find AIP fileGrp (package unsplit)
        if not files:
            files = self.pointer_root.findall(".//mets:fileSec/mets:fileGrp[@USE='Archival Information Package']/mets:file", namespaces=utils.NSMAP)

        # Add new FLocat elements for each LOCKSS URL to each file element
        for index, file_e in enumerate(files):
            LOGGER.debug('file element: %s', etree.tostring(file_e, pretty_print=True))
            if len(files) == 1:
                lom_id = self._download_url(package.uuid)
            else:
                lom_id = self._download_url(package.uuid, index + 1)
            LOGGER.debug('LOM id: %s', lom_id)
            lom_servers = statement_root.find(".//lom:content[@id='{}']/lom:serverlist".format(lom_id), namespaces=utils.NSMAP)
            LOGGER.debug('lom_servers: %s', lom_servers)
            # Remove existing LOCKSS URLs, if they exist
            for old_url in file_e.findall("mets:FLocat[@LOCTYPE='URL']", namespaces=utils.NSMAP):
                file_e.remove(old_url)
            # Add URLs from SWORD statement
            for server in lom_servers:
                # TODO check that size and checksum are the same
                # TODO what to do if size & checksum different?
                LOGGER.debug('LOM URL: %s', server.get('src'))
                flocat = etree.SubElement(file_e, 'FLocat', LOCTYPE="URL")
                flocat.set('{' + utils.NSMAP['xlink'] + '}href', server.get('src'))

        # Delete local files
        # Note: This will tell LOCKSS to stop harvesting, even if the file was
        # not split, and will not be deleted locally
        lom_content = statement_root.findall('.//lom:content', namespaces=utils.NSMAP)
        delete_lom_ids = [e.get('id') for e in lom_content]
        error = self._delete_update_lom(package, delete_lom_ids)
        if error is None:
            self._delete_files()

        LOGGER.info('update_package_status: new status: %s', status)

        # Write out pointer file again
        with open(package.full_pointer_file_path, 'w') as f:
            f.write(etree.tostring(self.pointer_root, pretty_print=True))

        # Update value if different
        package.status = status
        package.save()
        return (status, error)

    def _delete_update_lom(self, package, delete_lom_ids):
        """
        Notifys LOM that AUs with `delete_lom_ids` will be deleted.

        Helper to update_package_status.
        """
        # Update LOM that local copies will be deleted
        entry = sword2.Entry(id='urn:uuid:{}'.format(package.uuid))
        entry.register_namespace('lom', utils.NSMAP['lom'])
        for lom_id in delete_lom_ids:
            if lom_id:
                etree.SubElement(entry.entry, '{' + utils.NSMAP['lom'] + '}content', recrawl='false').text = lom_id
        LOGGER.debug('edit entry: %s', entry)
        # SWORD2 client doesn't handle 202 respose correctly - implementing here
        # Correct function is self.sword_connection.update_metadata_for_resource
        headers = {
            'Content-Type': "application/atom+xml;type=entry",
            'Content-Length': str(len(str(entry))),
            'On-Behalf-Of': str(self.content_provider_id),
        }
        response, content = self.sword_connection.h.request(
            uri=package.misc_attributes['edit_iri'],
            method='PUT',
            headers=headers,
            payload=str(entry))

        # Return with error message if response not 200
        LOGGER.debug('response code: %s', response['status'])
        if response['status'] != 200:
            if response['status'] == 202:  # Accepted - pushing new config
                return 'Lockss-o-matic is updating the config to stop harvesting.  Please try again to delete local files.'
            if response['status'] == 204:  # No Content - no matching AIP
                return 'Package {} is not found in LOCKSS'.format(package.uuid)
            if response['status'] == 409:  # Conflict - Files in AU with recrawl
                return "There are files in the LOCKSS Archival Unit (AU) that do not have 'recrawl=false'."
            return 'Error {} when requesting LOCKSS stop harvesting deleted files.'.format(response['status'])
        return None

    def _delete_files(self):
        """
        Delete AIP local files once stored in LOCKSS from disk and pointer file.

        Helper to update_package_status.
        """
        # Get paths to delete
        if self.keep_local:
            # Get all LOCKSS chucks local path FLocats
            delete_elements = self.pointer_root.xpath(".//mets:fileGrp[@USE='LOCKSS chunk']/*/mets:FLocat[@LOCTYPE='OTHER' and @OTHERLOCTYPE='SYSTEM']", namespaces=utils.NSMAP)
        else:
            # Get all local path FLocats
            delete_elements = self.pointer_root.xpath(".//mets:FLocat[@LOCTYPE='OTHER' and @OTHERLOCTYPE='SYSTEM']", namespaces=utils.NSMAP)
        LOGGER.debug('delete_elements: %s', delete_elements)

        # Delete paths from delete_elements from disk, and remove from METS
        for element in delete_elements:
            path = element.get('{' + utils.NSMAP['xlink'] + '}href')
            LOGGER.debug('path to delete: %s', path)
            try:
                os.remove(path)
            except os.error as e:
                if e.errno != errno.ENOENT:
                    LOGGER.exception('Could not delete %s', path)
            element.getparent().remove(element)

        # Update pointer file
        # If delete_elements is false, then this function has probably already
        # been run, and we don't want to add another delete event
        if not self.keep_local and delete_elements:
            amdsec = self.pointer_root.find('mets:amdSec', namespaces=utils.NSMAP)
            # Add 'deletion' PREMIS:EVENT
            digiprov_id = 'digiprovMD_{}'.format(len(amdsec))
            digiprov_split = utils.mets_add_event(
                digiprov_id=digiprov_id,
                event_type='deletion',
                event_outcome_detail_note='AIP deleted from local storage',
            )
            LOGGER.info('PREMIS:EVENT division: %s', etree.tostring(digiprov_split, pretty_print=True))
            amdsec.append(digiprov_split)

            # Add PREMIS:AGENT for storage service
            digiprov_id = 'digiprovMD_{}'.format(len(amdsec))
            digiprov_agent = utils.mets_ss_agent(amdsec, digiprov_id)
            if digiprov_agent is not None:
                LOGGER.info('PREMIS:AGENT SS: %s', etree.tostring(digiprov_agent, pretty_print=True))
                amdsec.append(digiprov_agent)
            # If file was split
            if self.pointer_root.find(".//mets:fileGrp[@USE='LOCKSS chunk']", namespaces=utils.NSMAP) is not None:
                # Delete fileGrp USE="AIP"
                del_elem = self.pointer_root.find(".//mets:fileGrp[@USE='Archival Information Package']", namespaces=utils.NSMAP)
                del_elem.getparent().remove(del_elem)
                # Delete structMap div TYPE='Local copy'
                del_elem = self.pointer_root.find(".//mets:structMap/*/mets:div[@TYPE='Local copy']", namespaces=utils.NSMAP)
                del_elem.getparent().remove(del_elem)
        return None

    def update_service_document(self):
        """ Fetch the service document from self.sd_iri and updates based on that.

        Updates AU size and collection IRI.

        Returns True on success, False on error.  No updates performed on error."""
        try:
            self.sword_connection = sword2.Connection(self.sd_iri, download_service_document=True,
                on_behalf_of=self.content_provider_id)
        except Exception:  # TODO make this more specific
            LOGGER.exception("Error getting service document from SWORD server.")
            return False
        # AU size
        self.au_size = self.sword_connection.maxUploadSize * 1000  # Convert from kB

        # Collection IRI
        # Workspaces are a list of ('workspace name', [collections]) tuples
        # Currently only support one workspace, so take the first one
        try:
            self.collection_iri = self.sword_connection.workspaces[0][1][0].href
        except IndexError:
            LOGGER.warning("No collection IRI found in LOCKSS-o-matic service document.")
            return False

        # Checksum type - LOM specific tag
        root = self.sword_connection.sd.service_dom
        self.checksum_type = root.findtext('lom:uploadChecksumType', namespaces=utils.NSMAP)

        self.save()
        return True

    def _split_package(self, package):
        """
        Splits the package into chunks of size self.au_size. Returns list of paths to the chunks.

        If the package has already been split (and an event is in the pointer
        file), returns the list if file paths from the pointer file.

        Updates the pointer file with the new LOCKSS chunks, and adds 'division'
        event.
        """
        # Parse pointer file
        if not self.pointer_root:
            self.pointer_root = etree.parse(package.full_pointer_file_path)

        # Check if file is already split, and if so just return split files
        if self.pointer_root.xpath('.//premis:eventType[text()="division"]', namespaces=utils.NSMAP):
            chunks = self.pointer_root.findall(".//mets:div[@TYPE='Archival Information Package']/mets:div[@TYPE='LOCKSS chunk']", namespaces=utils.NSMAP)
            output_files = [c.find('mets:fptr', namespaces=utils.NSMAP).get('FILEID') for c in chunks]
            return output_files

        file_path = package.full_path
        expected_num_files = math.ceil(os.path.getsize(file_path) / float(self.au_size))
        LOGGER.debug('expected_num_files: %s', expected_num_files)

        # No split needed - just return the file path
        if expected_num_files <= 1:
            LOGGER.debug('Only one file expected, not splitting')
            output_files = [file_path]
            # No events or structMap changes needed
            LOGGER.info('LOCKSS: after splitting: %s', output_files)
            return output_files

        # Split file
        # Strip extension, add .tar-1 ('-1' to make rename script happy)
        output_path = os.path.splitext(file_path)[0] + '.tar-1'
        command = ['tar', '--create', '--multi-volume',
            '--tape-length', str(self.au_size),
            '--new-volume-script', 'common/tar_new_volume.sh',
            '-f', output_path, file_path]
        # TODO reserve space in quota for extra files
        LOGGER.info('LOCKSS split command: %s', command)
        try:
            subprocess.check_call(command)
        except Exception:
            LOGGER.exception("Split of %s failed with command %s", file_path, command)
            raise
        output_path = output_path[:-2]  # Remove '-1'
        dirname, basename = os.path.split(output_path)
        output_files = sorted([os.path.join(dirname, entry) for entry in os.listdir(dirname) if entry.startswith(basename)])

        # Update pointer file
        amdsec = self.pointer_root.find('mets:amdSec', namespaces=utils.NSMAP)

        # Add 'division' PREMIS:EVENT
        try:
            event_detail = subprocess.check_output(['tar', '--version'])
        except subprocess.CalledProcessError as e:
            event_detail = e.output or 'Error: getting tool info; probably GNU tar'
        digiprov_id = 'digiprovMD_{}'.format(len(amdsec))
        digiprov_split = utils.mets_add_event(
            digiprov_id=digiprov_id,
            event_type='division',
            event_detail=event_detail,
            event_outcome_detail_note='{} LOCKSS chunks created'.format(len(output_files)),
        )
        LOGGER.debug('PREMIS:EVENT division: %s', etree.tostring(digiprov_split, pretty_print=True))
        amdsec.append(digiprov_split)

        # Add PREMIS:AGENT for storage service
        digiprov_id = 'digiprovMD_{}'.format(len(amdsec))
        digiprov_agent = utils.mets_ss_agent(amdsec, digiprov_id)
        if digiprov_agent is not None:
            LOGGER.debug('PREMIS:AGENT SS: %s', etree.tostring(digiprov_agent, pretty_print=True))
            amdsec.append(digiprov_agent)

        # Update structMap & fileSec
        self.pointer_root.find('mets:structMap', namespaces=utils.NSMAP).set('TYPE', 'logical')
        aip_div = self.pointer_root.find("mets:structMap/mets:div[@TYPE='Archival Information Package']", namespaces=utils.NSMAP)
        filesec = self.pointer_root.find('mets:fileSec', namespaces=utils.NSMAP)
        filegrp = etree.SubElement(filesec, 'fileGrp', USE='LOCKSS chunk')

        # Move ftpr to Local copy div
        local_ftpr = aip_div.find('mets:fptr', namespaces=utils.NSMAP)
        if local_ftpr is not None:
            div = etree.SubElement(aip_div, 'div', TYPE='Local copy')
            div.append(local_ftpr)  # This moves local_fptr

        # Add each split chunk to structMap & fileSec
        for idx, out_path in enumerate(output_files):
            # Add div to structMap
            div = etree.SubElement(aip_div, 'div', TYPE='LOCKSS chunk', ORDER=str(idx + 1))
            etree.SubElement(div, 'fptr', FILEID=os.path.basename(out_path))
            # Get checksum and size for fileSec
            try:
                checksum = utils.generate_checksum(out_path, self.checksum_type)
            except ValueError:  # Invalid checksum type
                checksum = utils.generate_checksum(out_path, 'md5')
            checksum_name = checksum.name.upper().replace('SHA', 'SHA-')
            size = os.path.getsize(out_path)
            # Add file & FLocat to fileSec
            file_e = etree.SubElement(filegrp, 'file',
                ID=os.path.basename(out_path), SIZE=str(size),
                CHECKSUM=checksum.hexdigest(), CHECKSUMTYPE=checksum_name)
            flocat = etree.SubElement(file_e, 'FLocat', OTHERLOCTYPE="SYSTEM", LOCTYPE="OTHER")
            flocat.set('{' + utils.NSMAP['xlink'] + '}href', out_path)

        # Write out pointer file again
        with open(package.full_pointer_file_path, 'w') as f:
            f.write(etree.tostring(self.pointer_root, pretty_print=True))

        return output_files

    def _download_url(self, uuid, index=None):
        """
        Returns externally available download URL for a file.

        If index is None, returns URL for a file.  Otherwise, returns URL for a
        LOCKSS chunk with the given index.
        """
        if index is not None:  # Chunk of split file
            download_url = reverse('download_lockss', kwargs={'api_name': 'v1', 'resource_name': 'file', 'uuid': uuid, 'chunk_number': str(index)})
        else:  # Single file - not split
            download_url = reverse('download_request', kwargs={'api_name': 'v1', 'resource_name': 'file', 'uuid': uuid})
        # Prepend domain name
        download_url = self.external_domain + download_url
        return download_url

    def _create_resource(self, package, output_files):
        """ Given a package, create an Atom resource entry to send to LOCKSS.

        Parses metadata for the Atom entry from the METS file, uses
        LOCKSS-o-matic-specific tags to describe size and checksums.
        """

        # Parse METS to get information for atom entry
        relative_mets_path = os.path.join(
            os.path.splitext(os.path.basename(package.current_path))[0],
            "data",
            'METS.{}.xml'.format(package.uuid))
        (mets_path, temp_dir) = package.extract_file(relative_mets_path)
        mets = etree.parse(mets_path)
        # Delete temp dir if created
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

        # Parse out name and description if found
        slug = str(package.uuid)
        title = os.path.basename(package.current_path)
        summary = 'AIP generated by Archivematica with uuid {}'.format(package.uuid)
        dublincore = mets.find('mets:dmdSec/mets:mdWrap[@MDTYPE="DC"]/mets:xmlData/dcterms:dublincore', namespaces=utils.NSMAP)
        if dublincore is not None:
            title = dublincore.findtext('dcterms:title', namespaces=utils.NSMAP, default=title)
            slug = dublincore.findtext('dcterms:title', namespaces=utils.NSMAP, default=slug)
            summary = dublincore.findtext('dcterms:description', namespaces=utils.NSMAP, default=summary)
        # Parse out Agent for author
        authors = mets.xpath(".//mets:mdWrap[@MDTYPE='PREMIS:AGENT']//mets:agentType[text()='organization']/ancestor::mets:agent/*/mets:agentIdentifierValue", namespaces=utils.NSMAP)
        author = authors[0].text if authors else None

        # Create atom entry
        entry = sword2.Entry(
            title=title,
            id='urn:uuid:' + package.uuid,
            author={'name': author},
            summary=summary)

        # Add each chunk to the atom entry
        if not self.pointer_root:
            self.pointer_root = etree.parse(package.full_pointer_file_path)
        entry.register_namespace('lom', utils.NSMAP['lom'])
        for index, file_path in enumerate(output_files):
            # Get external URL
            if len(output_files) == 1:
                external_url = self._download_url(package.uuid)
            else:
                external_url = self._download_url(package.uuid, index + 1)

            # Get checksum and size from pointer file (or generate if not found)
            file_e = self.pointer_root.find(".//mets:fileGrp[@USE='LOCKSS chunk']/mets:file[@ID='{}']".format(os.path.basename(file_path)), namespaces=utils.NSMAP)
            if file_e is not None:
                checksum_name = file_e.get('CHECKSUMTYPE')
                checksum_value = file_e.get('CHECKSUM')
                size = int(file_e.get('SIZE'))
            else:
                # Not split, generate
                try:
                    checksum = utils.generate_checksum(file_path,
                        self.checksum_type)
                except ValueError:  # Invalid checksum type
                    checksum = utils.generate_checksum(file_path, 'md5')
                checksum_name = checksum.name.upper().replace('SHA', 'SHA-')
                checksum_value = checksum.hexdigest()
                size = os.path.getsize(file_path)

            # Convert size to kB
            size = str(math.ceil(size / 1000.0))

            # Add new content entry and values
            entry.add_field('lom_content', external_url)
            content_entry = entry.entry[-1]
            content_entry.set('size', size)
            content_entry.set('checksumType', checksum_name)
            content_entry.set('checksumValue', checksum_value)

        LOGGER.debug('LOCKSS atom entry: %s', entry)
        return entry, slug
