"""GPG Utils.

Contains utilities for interacting with gnupg, i.e., Python GPG. This is
functionality for listing and creating private/public GPG keys for encrypting
and decrypting things. It is in its own utility because this functionality is
needed by both the GPG space and the administration view which can be used to
manage (i.e., list, created, import, delete) GPG keys.

"""

from __future__ import absolute_import
# stdlib, alphabetical
import logging

# Third party dependencies, alphabetical
import gnupg


LOGGER = logging.getLogger(__name__)


# WARNING: by not providing a gnupghome kw param to ``GPG`` here we are
# deferring to gnupg to determine where the .gnupg/ dir will be. On a default
# vagrant/ansible deploy, the .gnupg/ dir will be at
# /var/lib/archivematica/.gnupg/
gpg = gnupg.GPG()


# Defaults for the default AM SS GPG key
DFLT_KEY_TYPE = 'RSA'
DFLT_KEY_LENGTH = 4096
DFLT_KEY_REAL_NAME = 'Archivematica Storage Service GPG Key'
DFLT_KEY_PASSPHRASE = ''


def get_gpg_key(fingerprint):
    """Return the GPG key with fingerprint ``fingerprint`` or None if there is
    no such key in the SS's GPG keyring.
    """
    key_map = gpg.list_keys(True).key_map  # ``True`` means return private keys
    return key_map.get(fingerprint)


def get_gpg_key_list():
    """Return a list of all GPG keys as dicts. If the Storage Service default
    key does not exist, we create it here before returning the list.
    """
    keys = gpg.list_keys(True)
    default_key = get_default_gpg_key(keys)
    if not default_key:
        generate_default_gpg_key()
        keys = gpg.list_keys(True)
    return keys


def get_default_gpg_key(keys):
    """Find the default AM Storage Service key in the existing set of GPG keys
    or return ``None``.
    """
    for key in keys:
        uids = key['uids']
        for uid in uids:
            if uid.startswith(DFLT_KEY_REAL_NAME):
                return key
    return None


def generate_default_gpg_key():
    """Generate the default AM Storage Service key. Note that by supplying no
    expiration date, the key never expires.
    Warning: generating this key for the first time can take several minutes.
    At present, this default key is generated the first time that
    ``get_gpg_key_list`` is called, which is typically when the "Encryption
    keys" link is clicked under the "Administration" tab. Waiting on a long
    request like this is not a very good user experience. It may be desirable
    to do this in a separate thread and poll for completion, or install
    rng-tools, or else at least warn the user that this will take a long time,
    or use a smaller key size. The same considerations apply for
    ``generate_gpg_key``. TODO/QUESTION ^.
    """
    input_data = gpg.gen_key_input(
        key_type=DFLT_KEY_TYPE,
        key_length=DFLT_KEY_LENGTH,
        name_real=DFLT_KEY_REAL_NAME,
        passphrase=DFLT_KEY_PASSPHRASE
    )
    LOGGER.info('Creating default AM SS key with name %s', DFLT_KEY_REAL_NAME)
    gpg.gen_key(input_data)
    LOGGER.info('Finished creating default AM SS key with name %s',
                DFLT_KEY_REAL_NAME)


def generate_gpg_key(name_real, name_email):
    """Generate a GPG key."""
    input_data = gpg.gen_key_input(
        key_type=DFLT_KEY_TYPE,
        key_length=DFLT_KEY_LENGTH,
        name_real=name_real,
        name_email=name_email,
        passphrase=DFLT_KEY_PASSPHRASE
    )
    return gpg.gen_key(input_data)


def import_gpg_key(ascii_armor):
    """Import a GPG private key, given its ASCII armor string and return the
    imported key's fingerprint, if successful.
    """
    import_result = gpg.import_keys(ascii_armor)
    if import_result.count == 1:
        return import_result.fingerprints[0]
    return None


def export_gpg_key(fingerprint):
    """Return the ASCII armor (string) representation of the private and public
    keys with fingerprint ``fingerprint``.
    """
    return gpg.export_keys(fingerprint), gpg.export_keys(fingerprint, True)


def delete_gpg_key(fingerprint):
    """Delete the GPG key with fingerprint ``fingerprint``.  """
    result = gpg.delete_keys(fingerprint, True)
    LOGGER.debug('result of calling gpg.delete_keys(%s)', fingerprint)
    LOGGER.debug(str(result))
    try:
        assert str(result) == 'ok'
        return True
    except AssertionError:
        return False


def gpg_decrypt_file(path, decr_path):
    """Use GPG to decrypt the file at ``path`` and save the decrypted file to
    ``decr_path``.
    """
    with open(path, 'rb') as stream:
        return gpg.decrypt_file(stream, output=decr_path)


def gpg_encrypt_file(path, recipient_fingerprint):
    """Use GPG to encrypt the file at ``path`` and make it decryptable only
    with the key with fingerprint ``recipient_fingerprint``. The encrypted file
    is given the .gpg extension and its path and the Python-GnuPG encryption
    result <gnupg.Crypt> object are returned.
    """
    encr_path = path + '.gpg'
    with open(path, 'rb') as stream:
        result = gpg.encrypt_file(
            stream,
            [recipient_fingerprint],
            armor=False,
            output=encr_path)
    return encr_path, result
