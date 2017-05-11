from __future__ import absolute_import
# stdlib, alphabetical
import datetime
import logging
import os
import shutil
import subprocess
import tarfile
from uuid import uuid4

from lxml import etree

# Core Django, alphabetical
from django.db import models
from django.utils import timezone

# Third party dependencies, alphabetical
import gnupg

# This project, alphabetical
from common import utils
from common import gpgutils

# This module, alphabetical
from .location import Location
from .package import Package


LOGGER = logging.getLogger(__name__)


class GPGException(Exception):
    pass


class GPG(models.Model):
    """Space for storing things as files encrypted via GnuPG.
    When an AIP is moved to a GPG space, it is encrypted with a
    GPG-space-specific GPG public key and that encryption is documented in the
    AIP's pointer file. When the AIP is moved out of a GPG space (e.g., for
    re-ingest, download), it is decrypted. The intended use case is one wherein
    encrypted AIPs may be transfered to other storage locations that are not
    under the control of AM SS.

    Note: this space has does not (currently) implement the ``browse`` or
    ``delete_path`` methods.
    """

    # package.py looks up this class attribute to determine if a package is
    # encrypted.
    encrypted_space = True

    space = models.OneToOneField('Space', to_field='uuid')

    # The ``key`` attribute of a GPG "space" is the fingerprint (string) of an
    # existing GPG private key that this SS has access to. Note that GPG keys
    # are not represented in the SS database. We rely on GPG for fetching and
    # creating them.
    # TODO: the following configuration will trigger Django into creating
    # migrations that freeze deploy-specific GPG fingerprints in the migration,
    # which is undesirable. For now, I've just manually modified the
    # auto-created migration.
    keys = gpgutils.get_gpg_key_list()
    key_choices = [(key['fingerprint'], ', '.join(key['uids']))
                   for key in gpgutils.get_gpg_key_list()]
    system_key = gpgutils.get_default_gpg_key(keys)
    key = models.CharField(
        max_length=256,
        choices=key_choices,
        default=system_key['fingerprint'],
        verbose_name='GnuPG Private Key',
        help_text='The GnuPG private key that will be able to'
                  ' decrypt packages stored in this space.')

    class Meta:
        verbose_name = "GPG encryption on Local Filesystem"
        app_label = 'locations'

    ALLOWED_LOCATION_PURPOSE = [
        Location.AIP_STORAGE,
        Location.BACKLOG
    ]

    def move_to_storage_service(self, src_path, dst_path, dst_space):
        """Moves package at GPG space (at path ``src_path``) to SS at path
        ``dst_path`` and decrypts it there.
        """
        LOGGER.info('GPG ``move_to_storage_service``')
        LOGGER.info('GPG move_to_storage_service encrypted src_path: %s',
                    src_path)
        LOGGER.info('GPG move_to_storage_service encrypted dst_path: %s',
                    dst_path)
        self.space.create_local_directory(dst_path)
        # When the source path exists, we are moving the entire package to
        # somewhere on the storage service. In this case, we decrypt at the
        # destination.
        if os.path.exists(src_path):
            self.space.move_rsync(src_path, dst_path)
            _gpg_decrypt(dst_path)
        # When the source path does NOT exist, we are copying a single file or
        # directory from within an encrypted package, e.g., during SIP arrange.
        # Here we must decrypt, copy, and then re-encrypt. This seems like it
        # would be terribly inefficient when dealing with large transfers.
        else:
            encr_path = _get_encrypted_path(src_path)
            if not encr_path:
                raise GPGException(
                    'Unable to move %s; this file/dir does not exist; nor is'
                    ' it in an encrypted directory.', src_path)
            _gpg_decrypt(encr_path)
            try:
                if os.path.exists(src_path):
                    self.space.move_rsync(src_path, dst_path)
                else:
                    raise GPGException(
                        'Unable to move %s; this file/dir does not exist, not'
                        ' even in encrypted directory %s.', src_path, encr_path)
            finally:
                # Re-encrypt the decrypted package at source after copy, no
                # matter what happens.
                self._gpg_encrypt(encr_path)

    def move_from_storage_service(self, src_path, dst_path, package=None):
        """Move AIP in SS at path ``src_path`` to GPG space at ``dst_path``,
        encrypt it using the GPG Space's designated GPG ``key``, and update
        the AIP's pointer file accordingly.
        Note: we do *not* add the .gpg suffix to ``Package.current_path`` for
        the reason given in ``move_to_storage_service``.
        """
        LOGGER.info('in move_from_storage_service of GPG')
        LOGGER.info('GPG move_from, src_path: %s', src_path)
        LOGGER.info('GPG move_from, dst_path: %s', dst_path)
        if not package:
            raise GPGException('GPG spaces can only contain packages')
        self.space.create_local_directory(dst_path)
        self.space.move_rsync(src_path, dst_path, try_mv_local=True)
        try:
            _, encr_result = self._gpg_encrypt(dst_path)
        except GPGException:
            # If we fail to encrypt, then we send it back to where it came from.
            # TODO/QUESTION: Is this behaviour desirable?
            self.space.move_rsync(dst_path, src_path, try_mv_local=True)
            raise
        self._update_pointer_file(package, encr_result)

    def browse(self, path):
        """Returns browse results for a locally accessible *encrypted*
        filesystem. Based on ``Space.browse_local`` but has to deal with paths
        within encrypted directories (which are tarfiles).
        """
        if isinstance(path, unicode):
            path = str(path)
        # Encrypted space only stores files, so strip trailing /.
        path = path.rstrip('/')
        # Path may not exist if its a sub-path of an encrypted dir. Here we
        # look for a path ancestor that does exist.
        encr_path = _get_encrypted_path(path)
        if not encr_path:
            LOGGER.warning(
                'Unable to browse %s; this file/dir does not exist; nor is'
                ' it in an encrypted directory.', path)
            return {'directories': [], 'entries': [], 'properties': {}}
        # Decrypt and de-tar
        _gpg_decrypt(encr_path)
        # After decryption, ``path`` should exist if it is valid.
        if not os.path.exists(path):
            LOGGER.warning('Path %s in %s does not exist.', path, encr_path)
            self._gpg_encrypt(encr_path)
            return {'directories': [], 'entries': [], 'properties': {}}
        try:
            properties = {}
            entries = [name for name in os.listdir(path) if name[0] != '.']
            entries = sorted(entries, key=lambda s: s.lower())
            directories = []
            for name in entries:
                full_path = os.path.join(path, name)
                properties[name] = {'size': os.path.getsize(full_path)}
                if os.path.isdir(full_path) and os.access(full_path, os.R_OK):
                    directories.append(name)
                    properties[name]['object count'] = (
                        self.space.count_objects_in_directory(full_path))
        finally:
            # No matter what happens, re-encrypt the decrypted package.
            self._gpg_encrypt(encr_path)
        return {
            'directories': directories,
            'entries': entries,
            'properties': properties
        }

    def verify(self):
        """Verify that the space is accessible to the storage service. """
        # QUESTION: What is the purpose of this method? Investigation
        # shows that the ``NFS`` and ``Fedora`` spaces define and use it while
        # ``LocalFilesystem`` defines it but does not use it.
        verified = os.path.isdir(self.space.path)
        self.space.verified = verified
        self.space.last_verified = datetime.datetime.now()

    def _update_pointer_file(self, package, encr_result):
        """Update the package's (AIP's) pointer file in order to reflect the
        encryption event it has undergone.
        """
        # Update the pointer file to contain a record of the encryption.
        if (    package.pointer_file_path and
                package.package_type in (Package.AIP, Package.AIC)):
            pointer_absolute_path = package.full_pointer_file_path
            parser = etree.XMLParser(remove_blank_text=True)
            root = etree.parse(pointer_absolute_path, parser)
            metsBNS = "{" + utils.NSMAP['mets'] + "}"
            premisBNS = '{' + utils.NSMAP['premis'] + '}'

            # Set <premis:compositionLevel> to 2 and add <premis:inhibitors>
            for premis_object_el in root.findall('.//premis:object',
                                                 namespaces=utils.NSMAP):
                if premis_object_el.find(
                        'premis:objectIdentifier/premis:objectIdentifierValue',
                        namespaces=utils.NSMAP).text.strip() == package.uuid:
                    # Set <premis:compositionLevel> to 2
                    obj_char_el = premis_object_el.find(
                        'premis:objectCharacteristics', namespaces=utils.NSMAP)
                    compos_level_el = obj_char_el.find(
                        'premis:compositionLevel', namespaces=utils.NSMAP)
                    compos_level_el.text = '2'
                    # When encryption is applied, the objectCharacteristics
                    # block must include an inhibitors semantic unit.
                    inhibitor_el = etree.SubElement(
                        obj_char_el,
                        premisBNS + 'inhibitors')
                    etree.SubElement(
                        inhibitor_el,
                        premisBNS + 'inhibitorType').text = 'PGP'
                    etree.SubElement(
                        inhibitor_el,
                        premisBNS + 'inhibitorTarget').text = 'All content'

            file_el = root.find('.//mets:file', namespaces=utils.NSMAP)
            if file_el.get('ID', '').endswith(package.uuid):
                # Add a new <mets:transformFile> under the <mets:file> for the
                # AIP, one which indicates that a decryption transform is
                # needed.
                algorithm = 'gpg'
                etree.SubElement(
                    file_el,
                    metsBNS + "transformFile",
                    TRANSFORMORDER='1',
                    TRANSFORMTYPE='decryption',
                    TRANSFORMALGORITHM=algorithm,
                    TRANSFORMKEY=self.key
                )
                # Decompression <transformFile> must have its TRANSFORMORDER
                # attr changed to '2', because decryption is a precondition to
                # decompression.
                # TODO: does the logic here need to be more sophisticated? How
                # many <mets:transformFile> elements can there be?
                decompr_transform_el = file_el.find(
                    'mets:transformFile[@TRANSFORMTYPE="decompression"]',
                    namespaces=utils.NSMAP)
                if decompr_transform_el is not None:
                    decompr_transform_el.set('TRANSFORMORDER', '2')

            # Add a <PREMIS:EVENT> for the encryption event

            # TODO/QUESTION: in other contexts, the pipeline is responsible for
            # creating these things in the pointer file. The
            # createPointerFile.py client script, in particular, creates these
            # digiprovMD elements based on events and agents in the pipeline's
            # database. In this case, we are encrypting in the storage service
            # and creating PREMIS events in the pointer file that are *not*
            # also recorded in the database (SS's or AM's). Just pointing out
            # the discrepancy.
            amdsec = root.find('.//mets:amdSec', namespaces=utils.NSMAP)
            next_digiprov_md_id = _get_next_digiprov_md_id(root)
            digiprovMD = etree.Element(
                metsBNS + 'digiprovMD',
                ID=next_digiprov_md_id)
            mdWrap = etree.SubElement(
                digiprovMD,
                metsBNS + 'mdWrap',
                MDTYPE='PREMIS:EVENT')
            xmlData = etree.SubElement(mdWrap, metsBNS + 'xmlData')
            xmlData.append(_create_encr_event(root, encr_result))
            amdsec.append(digiprovMD)

            # Write the modified pointer file to disk.
            with open(pointer_absolute_path, 'w') as fileo:
                fileo.write(etree.tostring(root, pretty_print=True))
        else:
            LOGGER.warning('Unable to add encryption metadata to package %s'
                           ' since it has no pointer file; it must be an'
                           ' uncompressed package.', package.uuid)

    def _gpg_encrypt(self, path):
        """Use GnuPG to encrypt the package at ``path`` using this GPG Space's
        GPG key.
        """
        if os.path.isdir(path):
            _create_tar(path)
        encr_path, result = gpgutils.gpg_encrypt_file(path, self.key)
        if os.path.isfile(encr_path):
            LOGGER.info('Successfully encrypted %s at %s', path, encr_path)
            os.remove(path)
            os.rename(encr_path, path)
            return path, result
        else:
            fail_msg = ('An error occured when attempting to encrypt'
                        ' {}'.format(path))
            LOGGER.error(fail_msg)
            raise GPGException(fail_msg)


# This replaces non-unicode characters with a replacement character,
# and is primarily used for arbitrary strings (e.g. filenames, paths)
# that might not be valid unicode to begin with.
# NOTE: non-DRY from archivematicaCommon/archivematicaFunctions.py
def escape(string):
    if isinstance(string, str):
        string = string.decode('utf-8', errors='replace')
    return string


def _create_tar(path):
    """Create a tarfile from the directory at ``path`` and overwrite ``path``
    with that tarfile.
    """
    tarpath = '{}.tar'.format(path)
    changedir = os.path.dirname(tarpath)
    source = os.path.basename(path)
    cmd = ['tar', '-C', changedir, '-cf', tarpath, source]
    LOGGER.info('creating archive of %s at %s, relative to %s',
                source, tarpath, changedir)
    subprocess.check_output(cmd)
    fail_msg = 'Failed to create a tarfile at {} for dir at {}'.format(
        tarpath, path)
    if os.path.isfile(tarpath) and tarfile.is_tarfile(tarpath):
        shutil.rmtree(path)
        os.rename(tarpath, path)
    else:
        LOGGER.error(fail_msg)
        raise GPGException(fail_msg)
    try:
        assert tarfile.is_tarfile(path)
        assert not os.path.exists(tarpath)
    except AssertionError:
        LOGGER.error(fail_msg)
        raise GPGException(fail_msg)


def _extract_tar(tarpath):
    """Extract tarfile at ``path`` to a directory at ``path``."""
    newtarpath = '{}.tar'.format(tarpath)
    os.rename(tarpath, newtarpath)
    changedir = os.path.dirname(newtarpath)
    cmd = ['tar', '-xf', newtarpath, '-C', changedir]
    subprocess.check_output(cmd)
    if os.path.isdir(tarpath):
        os.remove(newtarpath)
    else:
        fail_msg = ('Failed to extract {} to a directory at the same'
                    ' location.'.format(tarpath))
        LOGGER.error(fail_msg)
        raise GPGException(fail_msg)


def _create_encr_event(root, encr_result):
    """Returns a PREMIS Event for the encryption."""
    # The following vars would typically come from an AM Events model.
    encr_event_type = 'encryption'
    # Note the UUID is created here with no other record besides the
    # pointer file.
    encr_event_uuid = str(uuid4())
    encr_event_datetime = timezone.now().isoformat()
    # First line of stdout from ``gpg --version`` is expected to be
    # something like 'gpg (GnuPG) 1.4.16'
    gpg_version = subprocess.check_output(
        ['gpg', '--version']).splitlines()[0].split()[-1]
    encr_event_detail = escape(
        'program=gpg (GnuPG); version={}; python-gnupg; version={}'.format(
            gpg_version, gnupg.__version__))
    # Maybe these should be defined in utils like they are in the
    # dashboard's namespaces.py...
    premisNS = utils.NSMAP['premis']
    premisBNS = '{' + premisNS + '}'
    xsiNS = utils.NSMAP['xsi']
    xsiBNS = '{' + xsiNS + '}'
    event = etree.Element(
        premisBNS + 'event', nsmap={'premis': premisNS})
    event.set(xsiBNS + 'schemaLocation',
              premisNS + ' http://www.loc.gov/standards/premis/'
                         'v2/premis-v2-2.xsd')
    event.set('version', '2.2')
    eventIdentifier = etree.SubElement(
        event,
        premisBNS + 'eventIdentifier')
    etree.SubElement(
        eventIdentifier,
        premisBNS + 'eventIdentifierType').text = 'UUID'
    etree.SubElement(
        eventIdentifier,
        premisBNS + 'eventIdentifierValue').text = encr_event_uuid
    etree.SubElement(
        event,
        premisBNS + 'eventType').text = encr_event_type
    etree.SubElement(
        event,
        premisBNS + 'eventDateTime').text = encr_event_datetime
    etree.SubElement(
        event,
        premisBNS + 'eventDetail').text = encr_event_detail
    eventOutcomeInformation = etree.SubElement(
        event,
        premisBNS + 'eventOutcomeInformation')
    etree.SubElement(
        eventOutcomeInformation,
        premisBNS + 'eventOutcome').text = '' # No eventOutcome text at present ...
    eventOutcomeDetail = etree.SubElement(
        eventOutcomeInformation,
        premisBNS + 'eventOutcomeDetail')
    # QUESTION: Python GnuPG gives GPG's stderr during encryption but not
    # it's stdout. Is the following sufficient?
    detail_note = 'Status="{}"; Standard Error="{}"'.format(
        encr_result.status.replace('"', r'\"'),
        encr_result.stderr.replace('"', r'\"').strip())
    etree.SubElement(
        eventOutcomeDetail,
        premisBNS + 'eventOutcomeDetailNote').text = escape(detail_note)
    # Copy the existing <premis:agentIdentifier> data to
    # <premis:linkingAgentIdentifier> elements in our encryption
    # <premis:event>
    for agent_id_el in root.findall(
            './/premis:agentIdentifier', namespaces=utils.NSMAP):
        agent_id_type = agent_id_el.find('premis:agentIdentifierType',
                                         namespaces=utils.NSMAP).text
        agent_id_value = agent_id_el.find('premis:agentIdentifierValue',
                                          namespaces=utils.NSMAP).text
        linkingAgentIdentifier = etree.SubElement(
            event,
            premisBNS + 'linkingAgentIdentifier')
        etree.SubElement(
            linkingAgentIdentifier,
            premisBNS + 'linkingAgentIdentifierType').text = agent_id_type
        etree.SubElement(
            linkingAgentIdentifier,
            premisBNS + 'linkingAgentIdentifierValue').text = agent_id_value
    return event


def _get_next_digiprov_md_id(root):
    """Return the next digiprovMD ID attribute; something like
    ``'digiprovMD_X'``, where X is an int.
    """
    ids = []
    for digiprov_md_el in root.findall(
            './/mets:digiprovMD', namespaces=utils.NSMAP):
        digiprov_md_id = int(digiprov_md_el.get('ID').replace(
            'digiprovMD_', ''))
        ids.append(digiprov_md_id)
    if ids:
        return 'digiprovMD_{}'.format(max(ids) + 1)
    return 'digiprovMD_1'


def _gpg_decrypt(path):
    """Use GnuPG to decrypt the file at ``path`` and then delete the
    encrypted file.
    """
    if not os.path.isfile(path):
        fail_msg = 'Cannot decrypt file at {}; no such file.'.format(path)
        LOGGER.error(fail_msg)
        raise GPGException(fail_msg)
    decr_path = path + '.decrypted'
    decr_result = gpgutils.gpg_decrypt_file(path, decr_path)
    if decr_result.ok and os.path.isfile(decr_path):
        LOGGER.info('Successfully decrypted %s to %s.', path, decr_path)
        os.remove(path)
        os.rename(decr_path, path)
    else:
        fail_msg = 'Failed to decrypt {}. Reason: {}'.format(
            path, decr_result.status)
        LOGGER.info(fail_msg)
        raise GPGException(fail_msg)
    # A tarfile without an extension is one that we created in this space
    # using an uncompressed AIP as input. We extract those here.
    if tarfile.is_tarfile(path) and os.path.splitext(path)[1] == '':
        LOGGER.info('%s is a tarfile so we are extracting it', path)
        _extract_tar(path)
    return path


def _get_encrypted_path(encr_path):
    """Attempt to return the existing file path that is ``encr_path`` or
    one of its ancestor paths. This is needed when we are asked to move a
    source path that may be located within an encrypted and compressed
    directory; in these cases, the source path itself will not exist so we
    are looking for an ancestor that is an encrypted file.
    """
    while not os.path.isfile(encr_path):
        encr_path = os.path.dirname(encr_path)
        if not encr_path:
            encr_path = None
            break
    return encr_path
