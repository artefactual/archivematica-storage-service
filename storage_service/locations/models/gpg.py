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
from django.utils.translation import ugettext as _, ugettext_lazy as _l
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


METS_BNS = '{' + utils.NSMAP['mets'] + '}'
PREMIS_BNS = '{' + utils.NSMAP['premis'] + '}'


class GPGException(Exception):
    pass



class GPG(models.Model):
    """Space for storing packages as files encrypted via GnuPG.
    When an AIP is moved to a GPG space, it is encrypted with a
    GPG-space-specific GPG public key and that encryption is documented in the
    AIP's pointer file. When the AIP is moved out of a GPG space (e.g., for
    re-ingest, download), it is decrypted. The intended use case is one wherein
    encrypted AIPs may be transfered to other storage locations that are not
    under the control of AM SS.

    Encryption policy:
    - only package models are encrypted (i.e., not individual files)
    - once encrypted, a package records its encryption key's fingerprint in the
      db (and in the pointer file for encrypted compressed AIPs)
    - re-encryption always uses the original GPG key (not the current key of
      the space)
    - re-encryption with a different key must be explicit (although this is not
      implemented yet; TODO (?))

    Note: this space has does not (currently) implement the ``delete_path``
    method.
    """

    # package.py looks up this class attribute to determine if a package is
    # encrypted.
    encrypted_space = True

    space = models.OneToOneField('Space', to_field='uuid')

    # The ``key`` attribute of a GPG "space" is the fingerprint (string) of an
    # existing GPG private key that this SS has access to. Note that GPG keys
    # are not represented in the SS database. We rely on GPG for fetching and
    # creating them.
    key = models.CharField(
        max_length=256,
        verbose_name=_l('GnuPG Private Key'),
        help_text=_l('The GnuPG private key that will be able to'
                     ' decrypt packages stored in this space.'))

    class Meta:
        verbose_name = _l("GPG encryption on Local Filesystem")
        app_label = _l('locations')

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
                raise GPGException(_(
                    'Unable to move %(src_path)s; this file/dir does not exist;'
                    ' nor is it in an encrypted directory.' %
                    {'src_path': src_path}))
            _gpg_decrypt(encr_path)
            try:
                if os.path.exists(src_path):
                    self.space.move_rsync(src_path, dst_path)
                else:
                    raise GPGException(_(
                        'Unable to move %(src_path)s; this file/dir does not'
                        ' exist, not even in encrypted directory'
                        ' %(encr_path)s.' %
                        {'src_path': src_path, 'encr_path': encr_path}))
            finally:
                # Re-encrypt the decrypted package at source after copy, no
                # matter what happens.
                _gpg_encrypt(encr_path, _encr_path2key_fingerprint(encr_path))

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
            raise GPGException(_('GPG spaces can only contain packages'))
        # Keep using the package's current GPG key, if it exists. Otherwise,
        # use this GPG space's key.
        key_fingerprint = package.encryption_key_fingerprint
        if not key_fingerprint:
            key_fingerprint = self.key
        self.space.create_local_directory(dst_path)
        self.space.move_rsync(src_path, dst_path, try_mv_local=True)
        try:
            __, encr_result = _gpg_encrypt(dst_path, key_fingerprint)
        except GPGException:
            # If we fail to encrypt, then we send it back to where it came from.
            # TODO/QUESTION: Is this behaviour desirable?
            self.space.move_rsync(dst_path, src_path, try_mv_local=True)
            raise
        # Update metadata related to the encryption of the package, both in the
        # package's pointer file and in the db (necessary for pointer-file-less
        # packages).
        _update_package_metadata(package, encr_result, key_fingerprint)

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
        key_fingerprint = _encr_path2key_fingerprint(encr_path)
        # After decryption, ``path`` should exist if it is valid.
        if not os.path.exists(path):
            LOGGER.warning('Path %s in %s does not exist.', path, encr_path)
            _gpg_encrypt(encr_path, key_fingerprint)
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
            _gpg_encrypt(encr_path, key_fingerprint)
        return {
            'directories': directories,
            'entries': entries,
            'properties': properties
        }

    def verify(self):
        """Verify that the space is accessible to the storage service."""
        # QUESTION: What is the purpose of this method? Investigation
        # shows that the ``NFS`` and ``Fedora`` spaces define and use it while
        # ``LocalFilesystem`` defines it but does not use it.
        verified = os.path.isdir(self.space.path)
        self.space.verified = verified
        self.space.last_verified = datetime.datetime.now()


def _update_package_metadata(package, encr_result, key_fingerprint):
    """Update the package's metadata (i.e., pointer file and db record) to
    reflect the encryption event it has undergone.
    """
    # Update model in db, if necessary.
    if package.encryption_key_fingerprint != key_fingerprint:
        package.encryption_key_fingerprint = key_fingerprint
        package.save()
    # Update the pointer file to contain a record of the encryption.
    if (package.pointer_file_path and
            package.package_type in (Package.AIP, Package.AIC)):
        _update_pointer_file(package, encr_result, key_fingerprint)


def _update_pointer_file(package, encr_result, key_fingerprint):
    """Update the package's (i.e., AIP or AIC's) pointer file in order to
    reflect the encryption event it has undergone.
    """
    pointer_absolute_path = package.full_pointer_file_path
    root = etree.parse(pointer_absolute_path,
                       etree.XMLParser(remove_blank_text=True))
    root = _set_premis_compos_lvl_inhibitors(root, package)
    root = _set_mets_transform_file(root, package, key_fingerprint)
    root = _set_premis_encryption_event(root, encr_result)
    with open(pointer_absolute_path, 'w') as fileo:
        fileo.write(etree.tostring(root, pretty_print=True))


def _gpg_encrypt(path, key_fingerprint):
    """Use GnuPG to encrypt the package at ``path`` using the GPG key
    matching the fingerprint ``key_fingerprint``. Returns the path to the
    encrypted file as well as a Python-GnuPG encryption result object with
    ``ok`` and ``status`` attributes, see
    https://pythonhosted.org/python-gnupg/.
    """
    if os.path.isdir(path):
        _create_tar(path)
    encr_path, result = gpgutils.gpg_encrypt_file(path, key_fingerprint)
    if os.path.isfile(encr_path):
        LOGGER.info('Successfully encrypted %s at %s', path, encr_path)
        os.remove(path)
        os.rename(encr_path, path)
        return path, result
    else:
        fail_msg = _('An error occured when attempting to encrypt'
                     ' %(path)s' % {'path': path})
        LOGGER.error(fail_msg)
        raise GPGException(fail_msg)


def _encr_path2key_fingerprint(encr_path):
    """Given an encrypted path, return the fingerprint of the GPG key
    used to encrypt the package. Since it was already encrypted, its
    model must have a GPG fingerprint.
    """
    return Package.objects.get(
        current_path__endswith(encr_path)).encryption_key_fingerprint


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
    fail_msg = _(
        'Failed to create a tarfile at %(tarpath)s for dir at %(path)s' %
        {'tarpath': tarpath, 'path': path})
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
        fail_msg = _('Failed to extract %(tarpath)s to a directory at the same'
                     ' location.' % {'tarpath': tarpath})
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
    xsiNS = utils.NSMAP['xsi']
    xsiBNS = '{' + xsiNS + '}'
    event = etree.Element(
        PREMIS_BNS + 'event', nsmap={'premis': premisNS})
    event.set(xsiBNS + 'schemaLocation',
              premisNS + ' http://www.loc.gov/standards/premis/'
                         'v2/premis-v2-2.xsd')
    event.set('version', '2.2')
    eventIdentifier = etree.SubElement(
        event,
        PREMIS_BNS + 'eventIdentifier')
    etree.SubElement(
        eventIdentifier,
        PREMIS_BNS + 'eventIdentifierType').text = 'UUID'
    etree.SubElement(
        eventIdentifier,
        PREMIS_BNS + 'eventIdentifierValue').text = encr_event_uuid
    etree.SubElement(
        event,
        PREMIS_BNS + 'eventType').text = encr_event_type
    etree.SubElement(
        event,
        PREMIS_BNS + 'eventDateTime').text = encr_event_datetime
    etree.SubElement(
        event,
        PREMIS_BNS + 'eventDetail').text = encr_event_detail
    eventOutcomeInformation = etree.SubElement(
        event,
        PREMIS_BNS + 'eventOutcomeInformation')
    etree.SubElement(
        eventOutcomeInformation,
        PREMIS_BNS + 'eventOutcome').text = ''  # No eventOutcome text at present ...
    eventOutcomeDetail = etree.SubElement(
        eventOutcomeInformation,
        PREMIS_BNS + 'eventOutcomeDetail')
    # QUESTION: Python GnuPG gives GPG's stderr during encryption but not
    # it's stdout. Is the following sufficient?
    detail_note = 'Status="{}"; Standard Error="{}"'.format(
        encr_result.status.replace('"', r'\"'),
        encr_result.stderr.replace('"', r'\"').strip())
    etree.SubElement(
        eventOutcomeDetail,
        PREMIS_BNS + 'eventOutcomeDetailNote').text = escape(detail_note)
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
            PREMIS_BNS + 'linkingAgentIdentifier')
        etree.SubElement(
            linkingAgentIdentifier,
            PREMIS_BNS + 'linkingAgentIdentifierType').text = agent_id_type
        etree.SubElement(
            linkingAgentIdentifier,
            PREMIS_BNS + 'linkingAgentIdentifierValue').text = agent_id_value
    return event


def _set_premis_compos_lvl_inhibitors(root, package):
    """Set PREMIS compositionLevel and inhibitors tags to reflect GPG
    encryption.
    """
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
                PREMIS_BNS + 'inhibitors')
            etree.SubElement(
                inhibitor_el,
                PREMIS_BNS + 'inhibitorType').text = 'GPG'
            etree.SubElement(
                inhibitor_el,
                PREMIS_BNS + 'inhibitorTarget').text = 'All content'
    return root


def _set_mets_transform_file(root, package, key_fingerprint):
    """Set/update METS transformFile tags to reflect GPG encryption."""
    file_el = root.find('.//mets:file', namespaces=utils.NSMAP)
    if file_el.get('ID', '').endswith(package.uuid):
        # Add a new <mets:transformFile> under the <mets:file> for the
        # AIP, one which indicates that a decryption transform is
        # needed.
        algorithm = 'gpg'
        etree.SubElement(
            file_el,
            METS_BNS + "transformFile",
            TRANSFORMORDER='1',
            TRANSFORMTYPE='decryption',
            TRANSFORMALGORITHM=algorithm,
            TRANSFORMKEY=key_fingerprint
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
    return root


def _set_premis_encryption_event(root, encr_result):
    """Add a <PREMIS:EVENT> for the encryption event to the pointer file
    ``root``.

    TODO/QUESTION: in other contexts, the pipeline is responsible for
    creating these things in the pointer file. The
    createPointerFile.py client script, in particular, creates these
    digiprovMD elements based on events and agents in the pipeline's
    database. In this case, we are encrypting in the storage service
    and creating PREMIS events in the pointer file that are *not*
    also recorded in the database (SS's or AM's). Just pointing out
    the discrepancy.
    """
    amdsec = root.find('.//mets:amdSec', namespaces=utils.NSMAP)
    next_digiprov_md_id = _get_next_digiprov_md_id(root)
    digiprovMD = etree.Element(METS_BNS + 'digiprovMD', ID=next_digiprov_md_id)
    mdWrap = etree.SubElement(
        digiprovMD,
        METS_BNS + 'mdWrap',
        MDTYPE='PREMIS:EVENT')
    xmlData = etree.SubElement(mdWrap, METS_BNS + 'xmlData')
    xmlData.append(_create_encr_event(root, encr_result))
    amdsec.append(digiprovMD)
    return root


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
        fail_msg = _('Cannot decrypt file at %(path)s; no such file.' %
                     {'path': path})
        LOGGER.error(fail_msg)
        raise GPGException(fail_msg)
    decr_path = path + '.decrypted'
    decr_result = gpgutils.gpg_decrypt_file(path, decr_path)
    if decr_result.ok and os.path.isfile(decr_path):
        LOGGER.info('Successfully decrypted %s to %s.', path, decr_path)
        os.remove(path)
        os.rename(decr_path, path)
    else:
        fail_msg = _('Failed to decrypt %(path)s. Reason: %(reason)s' %
                     {'path': path, 'reason': decr_result.status})
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
