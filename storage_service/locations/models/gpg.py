# stdlib, alphabetical
import datetime
import logging
import os
import tarfile

# Core Django, alphabetical
from django.conf import settings
from django.db import models
from django.utils.translation import ugettext_lazy as _

# Third party dependencies, alphabetical

# This project, alphabetical
from common import gpgutils, premis, utils

# This module, alphabetical
from .location import Location
from .package import Package
from . import space


LOGGER = logging.getLogger(__name__)


METS_BNS = "{" + utils.NSMAP["mets"] + "}"
PREMIS_BNS = "{" + utils.NSMAP["premis"] + "}"


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

    space = models.OneToOneField("Space", to_field="uuid", on_delete=models.CASCADE)

    # The ``key`` attribute of a GPG "space" is the fingerprint (string) of an
    # existing GPG private key that this SS has access to. Note that GPG keys
    # are not represented in the SS database. We rely on GPG for fetching and
    # creating them.
    key = models.CharField(
        max_length=256,
        verbose_name=_("GnuPG Private Key"),
        help_text=_(
            "The GnuPG private key that will be able to"
            " decrypt packages stored in this space."
        ),
    )

    class Meta:
        verbose_name = _("GPG encryption on Local Filesystem")
        app_label = _("locations")

    ALLOWED_LOCATION_PURPOSE = [
        Location.AIP_STORAGE,
        Location.BACKLOG,
        Location.REPLICATOR,
    ]

    def move_to_storage_service(self, src_path, dst_path, dst_space):
        """Moves package at GPG space (at path ``src_path``) to SS at path
        ``dst_path`` and decrypts it there.
        """
        LOGGER.info("GPG ``move_to_storage_service``")
        LOGGER.info("GPG move_to_storage_service encrypted src_path: %s", src_path)
        LOGGER.info("GPG move_to_storage_service encrypted dst_path: %s", dst_path)
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
                    _(
                        "Unable to move %(src_path)s; this file/dir does not exist;"
                        " nor is it in an encrypted directory." % {"src_path": src_path}
                    )
                )
            _gpg_decrypt(encr_path)
            try:
                if os.path.exists(src_path):
                    self.space.move_rsync(src_path, dst_path)
                else:
                    raise GPGException(
                        _(
                            "Unable to move %(src_path)s; this file/dir does not"
                            " exist, not even in encrypted directory"
                            " %(encr_path)s."
                            % {"src_path": src_path, "encr_path": encr_path}
                        )
                    )
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
        LOGGER.info("in move_from_storage_service of GPG")
        LOGGER.info("GPG move_from, src_path: %s", src_path)
        LOGGER.info("GPG move_from, dst_path: %s", dst_path)
        if not package:
            raise GPGException(_("GPG spaces can only contain packages"))
        # Every time this method is called, the package is encrypted with the
        # current GPG key of this space, which may differ from the key used to
        # encrypt the package the last time around.
        key_fingerprint = self.key
        self.space.create_local_directory(dst_path)
        self.space.move_rsync(src_path, dst_path, try_mv_local=True)
        try:
            __, encr_result = _gpg_encrypt(dst_path, key_fingerprint)
        except GPGException:
            # If we fail to encrypt, then we send it back to where it came from.
            self.space.move_rsync(dst_path, src_path, try_mv_local=True)
            raise
        # Update the GPG key fingerprint in db, if necessary.
        if package.encryption_key_fingerprint != key_fingerprint:
            package.encryption_key_fingerprint = key_fingerprint
            package.save()
        # If the package should have a pointer file, return an object
        # documenting the effects of storing the package, such that this
        # ``StorageEffects`` object can be used to update the pointer file
        # accordingly. Note: we cannot update the pointer file here because it
        # may not yet exist.
        # QUESTION: doesn't encryption change the size of the package? If so,
        # shouldn't this have consequences for the pointer file?
        # QUESTION: does encryption change the format?
        if package.should_have_pointer_file():

            def composition_level_updater(existing_composition_level):
                if existing_composition_level:
                    return str(int(existing_composition_level) + 1)
                return "1"

            inhibitors = (
                "inhibitors",
                ("inhibitor_type", "GPG"),
                ("inhibitor_target", "All content"),
            )
            encryption_event = premis.create_encryption_event(
                encr_result, key_fingerprint, _get_gpg_version()
            )
            return utils.StorageEffects(
                events=[encryption_event],
                composition_level_updater=composition_level_updater,
                inhibitors=[inhibitors],
            )

    def browse(self, path):
        """Returns browse results for a locally accessible *encrypted*
        filesystem. Based on ``Space.browse_local`` but has to deal with paths
        within encrypted directories (which are tarfiles).
        """
        if isinstance(path, str):
            path = path.encode("utf8")
        # Encrypted space only stores files, so strip trailing /.
        path = path.decode("utf8").rstrip("/")
        # Path may not exist if its a sub-path of an encrypted dir. Here we
        # look for a path ancestor that does exist.
        encr_path = _get_encrypted_path(path)
        if not encr_path:
            LOGGER.warning(
                "Unable to browse %s; this file/dir does not exist; nor is"
                " it in an encrypted directory.",
                path,
            )
            return {"directories": [], "entries": [], "properties": {}}
        # Decrypt and de-tar
        _gpg_decrypt(encr_path)
        key_fingerprint = _encr_path2key_fingerprint(encr_path)
        # After decryption, ``path`` should exist if it is valid.
        if not os.path.exists(path):
            LOGGER.warning("Path %s in %s does not exist.", path, encr_path)
            _gpg_encrypt(encr_path, key_fingerprint)
            return {"directories": [], "entries": [], "properties": {}}
        try:
            ret = space.path2browse_dict(path)
        finally:
            # No matter what happens, re-encrypt the decrypted package.
            _gpg_encrypt(encr_path, key_fingerprint)
        return ret

    def verify(self):
        """Verify that the space is accessible to the storage service."""
        # QUESTION: What is the purpose of this method? Investigation
        # shows that the ``NFS`` and ``Fedora`` spaces define and use it while
        # ``LocalFilesystem`` defines it but does not use it.
        verified = os.path.isdir(self.space.path)
        self.space.verified = verified
        self.space.last_verified = datetime.datetime.now()


def _gpg_encrypt(path, key_fingerprint):
    """Use GnuPG to encrypt the package at ``path`` using the GPG key
    matching the fingerprint ``key_fingerprint``. Returns the path to the
    encrypted file as well as a Python-GnuPG encryption result object with
    ``ok`` and ``status`` attributes, see
    https://pythonhosted.org/python-gnupg/.
    """
    tar_created = False
    if os.path.isdir(path):
        utils.create_tar(path)
        tar_created = True
    encr_path, result = gpgutils.gpg_encrypt_file(path, key_fingerprint)
    if os.path.isfile(encr_path) and result.ok:
        LOGGER.info("Successfully encrypted %s at %s", path, encr_path)
        os.remove(path)
        os.rename(encr_path, path)
        return path, result
    else:
        if tar_created:
            utils.extract_tar(path)
        fail_msg = _(
            "An error occured when attempting to encrypt" " %(path)s" % {"path": path}
        )
        LOGGER.error(fail_msg)
        raise GPGException(fail_msg)


def _db_engine():
    if "sqlite" in settings.DATABASES["default"]["ENGINE"]:
        return "sqlite"
    if "mysql" in settings.DATABASES["default"]["ENGINE"]:
        return "mysql"
    return "other"


def _encr_path2key_fingerprint(encr_path):
    """Given an encrypted path, return the fingerprint of the GPG key
    used to encrypt the package. Since it was already encrypted, its
    model must have a GPG fingerprint.
    """
    sql = (
        "SELECT * FROM locations_package WHERE %s LIKE CONCAT('%%',"
        " current_path, '%%')"
    )
    if _db_engine() == "sqlite":
        sql = (
            'SELECT * FROM locations_package WHERE %s LIKE "%" ||'
            ' current_path || "%"'
        )
    matches = list(Package.objects.raw(sql, [encr_path]))
    try:
        return matches[0].encryption_key_fingerprint
    except IndexError:
        fail_msg = f"Unable to find package matching encrypted path {encr_path}"
        LOGGER.error(fail_msg)
        raise GPGException(fail_msg)


def _parse_gpg_version(raw_gpg_version):
    return ".".join(str(i) for i in raw_gpg_version)


def _get_gpg_version():
    """Return the version of GPG installed as a string.

    ``gpgutils.gpg.version`` is a 3-item tuple of integers, e.g.:
    ``(1, 4, 16)`` for GnuPG v1.4.16.
    """
    return _parse_gpg_version(gpgutils.gpg().version)


def _gpg_decrypt(path):
    """Use GnuPG to decrypt the file at ``path`` and then delete the
    encrypted file.
    """
    if not os.path.isfile(path):
        fail_msg = _(f"Cannot decrypt file at {path}; no such file.")
        LOGGER.error(fail_msg)
        raise GPGException(fail_msg)
    decr_path = path + ".decrypted"
    decr_result = gpgutils.gpg_decrypt_file(path, decr_path)
    if decr_result.ok and os.path.isfile(decr_path):
        LOGGER.info("Successfully decrypted %s to %s.", path, decr_path)
        os.remove(path)
        os.rename(decr_path, path)
    else:
        fail_msg = _(
            "Failed to decrypt %(path)s. Reason: %(reason)s"
            % {"path": path, "reason": decr_result.status}
        )
        LOGGER.info(fail_msg)
        raise GPGException(fail_msg)
    # A tarfile without an extension is one that we created in this space
    # using an uncompressed AIP as input. We extract those here.
    if tarfile.is_tarfile(path) and os.path.splitext(path)[1] == "":
        LOGGER.info("%s is a tarfile so we are extracting it", path)
        utils.extract_tar(path)
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
        if (not encr_path) or (encr_path == "/"):
            encr_path = None
            break
    return encr_path
