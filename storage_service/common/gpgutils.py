"""GPG Utils.

Contains utilities for interacting with gnupg, i.e., Python GPG. This is
functionality for listing and creating private/public GPG keys for encrypting
and decrypting things. It is in its own utility because this functionality is
needed by both the GPG space and the administration view which can be used to
manage (i.e., list, created, import, delete) GPG keys.

"""


# stdlib, alphabetical
import logging

# Third party dependencies, alphabetical
import gnupg
from django.apps import apps
from django.conf import settings
from django.utils.translation import ugettext as _

try:
    from pathlib import Path
except ImportError:
    from pathlib2 import Path

from .which import which


LOGGER = logging.getLogger(__name__)


# Defaults for the default AM SS GPG key
DFLT_KEY_TYPE = "RSA"
DFLT_KEY_LENGTH = 4096
DFLT_KEY_REAL_NAME = _("Archivematica Storage Service GPG Key")
DFLT_KEY_PASSPHRASE = ""


PASSPHRASED = "passphrased"
IMPORT_ERROR = "import error"
ENCR_WORKS = "yes"
ENCR_FAILS = "no"


class GPGBinaryPathError(Exception):
    """Raised when the GnuPG binary could not be found in the system path."""


class GPG:

    # List of binaries in order of preference. In distros like Ubuntu 18.04,
    # GnuPG v1 is only available via ``gpg1`` (package ``gnupg1``).
    PREFERRED_GNUPG_BINARIES = ["gpg1", "gpg"]

    def __init__(self):
        self._gpg = None

    def __call__(self):
        if not self._gpg:
            gnupghome = self._get_gnupg_home_path()
            self._ensure_gnupg_home_exists(gnupghome)
            self._gpg = gnupg.GPG(
                gnupghome=gnupghome, gpgbinary=self._get_gnupg_bin_path()
            )
        return self._gpg

    def _get_gnupg_home_path(self):
        """Find and return the home path for GnuPG to store its config."""
        gnupg_home_path = settings.GNUPG_HOME_PATH
        if not gnupg_home_path:
            Location = apps.get_model(app_label="locations", model_name="Location")
            ss_internal = Location.active.get(purpose=Location.STORAGE_SERVICE_INTERNAL)
            gnupg_home_path = ss_internal.full_path
        return gnupg_home_path

    def _get_gnupg_bin_path(self):
        """Find and return the path of the preferred GnuPG binary."""
        for item in self.PREFERRED_GNUPG_BINARIES:
            ret = which(item)
            if ret is not None:
                return ret
        raise GPGBinaryPathError(
            "GnuPG binary not found in the system path."
            " Preferred binary names: %s" % self.PREFERRED_GNUPG_BINARIES
        )

    @staticmethod
    def _ensure_gnupg_home_exists(gnupghome):
        """Ensure that GnuPG's home directory exists."""
        Path(gnupghome).mkdir(mode=0o700, parents=False, exist_ok=True)


gpg = GPG()


def get_gpg_key(fingerprint):
    """Return the GPG key with fingerprint ``fingerprint`` or None if there is
    no such key in the SS's GPG keyring.
    """
    key_map = gpg().list_keys(True).key_map  # ``True`` means return private keys
    return key_map.get(fingerprint)


def get_gpg_key_list():
    """Return a list of all GPG keys as dicts. If the Storage Service default
    key does not exist, we create it here before returning the list.
    """
    keys = gpg().list_keys(True)
    default_key = get_default_gpg_key(keys)
    if not default_key:
        generate_default_gpg_key()
        keys = gpg().list_keys(True)
    return keys


def get_default_gpg_key(keys):
    """Find the default AM Storage Service key in the existing set of GPG keys
    or return ``None``.
    """
    for key in keys:
        uids = key["uids"]
        for uid in uids:
            if uid.startswith(DFLT_KEY_REAL_NAME):
                return key
    return None


def generate_default_gpg_key():
    """Generate the default AM Storage Service key. Note that by supplying no
    expiration date, the key never expires. At present, this default key is
    generated the first time that ``get_gpg_key_list`` is called, which is
    typically when the "Encryption keys" link is clicked under the
    "Administration" tab. WARNING: if rng-tools is not installed or is not
    correctly configured, then GPG may take a long time to generate keys.
    """
    input_data = gpg().gen_key_input(
        key_type=DFLT_KEY_TYPE,
        key_length=DFLT_KEY_LENGTH,
        name_real=DFLT_KEY_REAL_NAME,
        passphrase=DFLT_KEY_PASSPHRASE,
    )
    LOGGER.info("Creating default AM SS key with name %s", DFLT_KEY_REAL_NAME)
    gpg().gen_key(input_data)
    LOGGER.info("Finished creating default AM SS key with name %s", DFLT_KEY_REAL_NAME)


def generate_gpg_key(name_real, name_email):
    """Generate a GPG key."""
    input_data = gpg().gen_key_input(
        key_type=DFLT_KEY_TYPE,
        key_length=DFLT_KEY_LENGTH,
        name_real=name_real,
        name_email=name_email,
        passphrase=DFLT_KEY_PASSPHRASE,
    )
    return gpg().gen_key(input_data)


def import_gpg_key(ascii_armor):
    """Import a GPG private key, given its ASCII armor string and return the
    imported key's fingerprint, if successful; if unsuccessful, return a string
    indicating why and delete any key created in the process.
    """
    import_result = gpg().import_keys(ascii_armor)
    if import_result.count == 1:
        fingerprint = import_result.fingerprints[0]
        it_works = encryption_works(fingerprint)
        if it_works == ENCR_WORKS:
            return fingerprint
        else:
            delete_gpg_key(fingerprint)
            if it_works == PASSPHRASED:
                return PASSPHRASED
        return IMPORT_ERROR
    return IMPORT_ERROR


def encryption_works(fingerprint):
    """Check whether we can encrypt and decrypt with the key with fingerprint
    ``fingerprint``. Return 'yes' if it does, 'no' if it doesn't and
    'passphrased' if it doesn't because a passphrase is required.
    """
    unencrypted_string = "secrets"
    encrypted_data = gpg().encrypt(unencrypted_string, fingerprint, always_trust=True)
    encrypted_string = str(encrypted_data)
    LOGGER.info("Checking encryption with key %s", fingerprint)
    LOGGER.info("encrypt ok: %s", encrypted_data.ok)
    LOGGER.info("encrypt status: %s", encrypted_data.status)
    LOGGER.info("encrypt stderr: %s", encrypted_data.stderr)
    if not encrypted_data.ok:
        return ENCR_FAILS  # unable to encrypt
    decrypted_data = gpg().decrypt(encrypted_string)
    LOGGER.info("Checking decryption with key %s", fingerprint)
    LOGGER.info("decrypt ok: %s", decrypted_data.ok)
    LOGGER.info("decrypt status: %s", decrypted_data.status)
    LOGGER.info("decrypt stderr: %s", decrypted_data.stderr)
    if decrypted_data.ok:
        return ENCR_WORKS
    else:
        # python-gnupg stopped reporting "need passphrase".
        if (
            decrypted_data.status == "need passphrase"
            or "NEED_PASSPHRASE" in decrypted_data.stderr
        ):
            return PASSPHRASED
        return ENCR_FAILS


def export_gpg_key(fingerprint):
    """Return the ASCII armor (string) representation of the private and public
    keys with fingerprint ``fingerprint``.
    """
    return gpg().export_keys(fingerprint), gpg().export_keys(fingerprint, True)


def delete_gpg_key(fingerprint):
    """Delete the GPG key with fingerprint ``fingerprint``.  """
    result = gpg().delete_keys(fingerprint, True)
    try:
        assert str(result) == "ok"
        return True
    except AssertionError:
        return False


def gpg_decrypt_file(path, decr_path):
    """Use GPG to decrypt the file at ``path`` and save the decrypted file to
    ``decr_path``.
    """
    with open(path, "rb") as stream:
        return gpg().decrypt_file(stream, output=decr_path)


def gpg_encrypt_file(path, recipient_fingerprint):
    """Use GPG to encrypt the file at ``path`` and make it decryptable only
    with the key with fingerprint ``recipient_fingerprint``. The encrypted file
    is given the .gpg extension and its path and the Python-GnuPG encryption
    result <gnupg.Crypt> object are returned.
    """
    encr_path = path + ".gpg"
    with open(path, "rb") as stream:
        result = gpg().encrypt_file(
            stream,
            [recipient_fingerprint],
            armor=False,
            always_trust=True,  # so we can use imported keys
            output=encr_path,
        )
    return encr_path, result
