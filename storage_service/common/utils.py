import ast
import datetime
import hashlib
import logging
import mimetypes
import os
import re
import shutil
import subprocess
import tarfile
import uuid
from collections import namedtuple

import scandir
from administration import models
from django import http
from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import ugettext as _
from lxml import etree
from lxml.builder import ElementMaker

from storage_service import __version__ as ss_version

LOGGER = logging.getLogger(__name__)

NSMAP = {
    "atom": "http://www.w3.org/2005/Atom",  # Atom Syndication Format
    "app": "http://www.w3.org/2007/app",  # Atom Publishing Protocol
    "dc": "http://purl.org/dc/elements/1.1/",
    "dcterms": "http://purl.org/dc/terms/",
    "lom": "http://lockssomatic.info/SWORD2",
    "mets": "http://www.loc.gov/METS/",
    "premis": "info:lc/xmlns/premis-v2",
    "premis3": "http://www.loc.gov/premis/v3",
    "sword": "http://purl.org/net/sword/terms/",
    "xlink": "http://www.w3.org/1999/xlink",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
}

# Compression options for packages, the list is not yet comprehensive, and
# future work could bring much of this into its own module.
COMPRESSION_7Z_BZIP = "7z with bzip"
COMPRESSION_7Z_LZMA = "7z with lzma"
COMPRESSION_7Z_COPY = "7z without compression"
COMPRESSION_TAR = "tar"
COMPRESSION_TAR_BZIP2 = "tar bz2"
COMPRESSION_TAR_GZIP = "tar gz"
COMPRESSION_ALGORITHMS = (
    COMPRESSION_7Z_BZIP,
    COMPRESSION_7Z_LZMA,
    COMPRESSION_7Z_COPY,
    COMPRESSION_TAR,
    COMPRESSION_TAR_BZIP2,
    COMPRESSION_TAR_GZIP,
)

PRONOM_7Z = "fmt/484"
PRONOM_BZIP2 = "x-fmt/268"
PRONOM_GZIP = "x-fmt/266"

COMPRESS_ALGO_7Z_COPY = "copy"
COMPRESS_ALGO_LZMA = "lzma"
COMPRESS_ALGO_BZIP2 = "bzip2"
COMPRESS_ALGO_TAR = "tar"
COMPRESS_ALGO_GZIP = "gzip"

COMPRESS_EXTENSION_7Z = ".7z"
COMPRESS_EXTENSION_BZIP2 = ".bz2"
COMPRESS_EXTENSION_GZIP = ".gz"
COMPRESS_EXTENSION_ZIP = ".zip"

COMPRESS_EXTENSIONS = (
    COMPRESS_EXTENSION_7Z,
    COMPRESS_EXTENSION_BZIP2,
    COMPRESS_EXTENSION_GZIP,
    COMPRESS_EXTENSION_ZIP,
)

TAR_EXTENSION = ".tar"

PACKAGE_EXTENSIONS = (TAR_EXTENSION,) + COMPRESS_EXTENSIONS

COMPRESS_PROGRAM_7Z = "7-Zip"
COMPRESS_PROGRAM_TAR = "tar"

PREFIX_NS = {k: "{" + v + "}" for k, v in NSMAP.items()}

DECOMPRESS_TRANSFORM_TYPE = "decompression"

# ########## SETTINGS ############


def get_all_settings():
    """Returns a dict of 'setting_name': value with all of the settings."""
    settings = dict(models.Settings.objects.all().values_list("name", "value"))
    for setting, value in settings.items():
        try:
            settings[setting] = ast.literal_eval(value)
        except (SyntaxError, ValueError):
            pass  # Not all the settings are Python literals
    return settings


def get_setting(setting, default=None):
    """Returns the value of 'setting' from models.Settings, 'default' if not found."""
    try:
        setting = models.Settings.objects.get(name=setting)
    except models.Settings.DoesNotExist:
        return_value = default
    else:
        return_value = ast.literal_eval(setting.value)
    return return_value


def set_setting(setting, value=None):
    """Sets 'setting' to 'value' in models.Settings.

    'value' must be an object that can be recreated by calling literal_eval on
    its string representation.  Strings are automatically esacped."""
    # Since we call literal_eval on settings when we extract them, we need to
    # put quotes around strings so they remain strings
    if isinstance(value, str):
        value = f"'{value}'"
    setting, _ = models.Settings.objects.get_or_create(name=setting)
    setting.value = value
    setting.save()


# ########## DEPENDENCIES ############


def dependent_objects(object_):
    """Returns all the objects that rely on 'object_'."""
    related_objects = [
        f
        for f in object_._meta.get_fields()
        if (f.one_to_many or f.one_to_one) and f.auto_created
    ]
    links = [rel.get_accessor_name() for rel in related_objects]
    dependent_objects = []
    for link in links:
        try:
            linked_objects = getattr(object_, link).all()
        except (AttributeError, ObjectDoesNotExist):
            # This is probably a OneToOneField, and should be handled differently
            # Or the relation has no entries
            continue
        for linked_object in linked_objects:
            dependent_objects.append(
                {"model": linked_object._meta.verbose_name, "value": linked_object}
            )
    return dependent_objects


# ########## DOWNLOADING ############


def download_file_stream(filepath, temp_dir=None):
    """
    Returns `filepath` as a HttpResponse stream.

    Deletes temp_dir once stream created if it exists.
    """
    # If not found, return 404
    if not os.path.exists(filepath):
        return http.HttpResponseNotFound(_("File not found"))

    filename = os.path.basename(filepath)

    # Open file in binary mode
    response = http.FileResponse(open(filepath, "rb"))

    response["Content-type"] = get_mimetype(filename)
    response["Content-Disposition"] = 'attachment; filename="' + filename + '"'
    response["Content-Length"] = os.path.getsize(filepath)

    # Delete temp dir if created
    if temp_dir and os.path.exists(temp_dir):
        shutil.rmtree(temp_dir, ignore_errors=True)

    return response


# ########## XML & POINTER FILE ############


def _storage_service_agent():
    return "Archivematica Storage Service-%s" % ss_version


def mets_add_event(amdsec, event_type, event_detail="", event_outcome_detail_note=""):
    """
    Adds a PREMIS:EVENT and associated PREMIS:AGENT to the provided amdSec.
    """
    # Add PREMIS:EVENT
    digiprov_id = f"digiprovMD_{len(amdsec)}"
    event = mets_event(
        digiprov_id=digiprov_id,
        event_type=event_type,
        event_detail=event_detail,
        event_outcome_detail_note=event_outcome_detail_note,
    )
    LOGGER.debug(
        "PREMIS:EVENT %s: %s", event_type, etree.tostring(event, pretty_print=True)
    )
    amdsec.append(event)

    # Add PREMIS:AGENT for storage service
    digiprov_id = f"digiprovMD_{len(amdsec)}"
    digiprov_agent = mets_ss_agent(amdsec, digiprov_id)
    if digiprov_agent is not None:
        LOGGER.debug(
            "PREMIS:AGENT SS: %s", etree.tostring(digiprov_agent, pretty_print=True)
        )
        amdsec.append(digiprov_agent)


def mets_event(
    digiprov_id,
    event_type,
    event_detail="",
    event_outcome_detail_note="",
    agent_type="storage service",
    agent_value=None,
):
    """
    Create and return a PREMIS:EVENT.
    """
    now = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    if agent_value is None:
        agent_value = _storage_service_agent()
    # New E with namespace for PREMIS
    EP = ElementMaker(namespace=NSMAP["premis"], nsmap={"premis": NSMAP["premis"]})
    EM = ElementMaker(namespace=NSMAP["mets"], nsmap={"mets": NSMAP["mets"]})
    premis_event = EP.event(
        EP.eventIdentifier(
            EP.eventIdentifierType("UUID"), EP.eventIdentifierValue(str(uuid.uuid4()))
        ),
        EP.eventType(event_type),
        EP.eventDateTime(now),
        EP.eventDetail(event_detail),
        EP.eventOutcomeInformation(
            EP.eventOutcome(),
            EP.eventOutcomeDetail(EP.eventOutcomeDetailNote(event_outcome_detail_note)),
        ),
        EP.linkingAgentIdentifier(
            EP.linkingAgentIdentifierType(agent_type),
            EP.linkingAgentIdentifierValue(agent_value),
        ),
        version="2.2",
    )
    premis_event.set(
        "{" + NSMAP["xsi"] + "}schemaLocation",
        "info:lc/xmlns/premis-v2 http://www.loc.gov/standards/premis/v2/premis-v2-2.xsd",
    )

    # digiprovMD to wrap PREMIS event
    digiprov_event = EM.digiprovMD(
        EM.mdWrap(EM.xmlData(premis_event), MDTYPE="PREMIS:EVENT"), ID=digiprov_id
    )
    return digiprov_event


def mets_ss_agent(xml, digiprov_id, agent_value=None, agent_type="storage service"):
    """
    Create and return a PREMIS:AGENT for the SS, if not found in `xml`.
    """
    if agent_value is None:
        agent_value = _storage_service_agent()
    existing_agent = xml.xpath(
        ".//mets:agentIdentifier[mets:agentIdentifierType='{}' and mets:agentIdentifierValue='{}']".format(
            agent_type, agent_value
        ),
        namespaces=NSMAP,
    )
    if existing_agent:
        return None
    EP = ElementMaker(namespace=NSMAP["premis"], nsmap={"premis": NSMAP["premis"]})
    EM = ElementMaker(namespace=NSMAP["mets"], nsmap={"mets": NSMAP["mets"]})
    digiprov_agent = EM.digiprovMD(
        EM.mdWrap(
            EM.xmlData(
                EP.agent(
                    EP.agentIdentifier(
                        EP.agentIdentifierType(agent_type),
                        EP.agentIdentifierValue(agent_value),
                    ),
                    EP.agentName("Archivematica Storage Service"),
                    EP.agentType("software"),
                )
            ),
            MDTYPE="PREMIS:AGENT",
        ),
        ID=digiprov_id,
    )
    return digiprov_agent


def get_compression(pointer_path):
    """Return the compression algorithm used to compress the package, as
    documented in the pointer file at ``pointer_path``.

    :param pointer_path: path to xml pointer file
    :returns: one of the constants in ``COMPRESSION_ALGORITHMS``.
    """
    doc = etree.parse(pointer_path)

    puid = doc.findtext(".//premis:formatRegistryKey", namespaces=NSMAP)
    if puid is None:
        # Try the PREMIS3 namespace as the pointer file may be newer.
        puid = doc.findtext(".//premis3:formatRegistryKey", namespaces=NSMAP)
    if puid == PRONOM_7Z:  # 7 Zip
        algo = doc.find(".//mets:transformFile", namespaces=NSMAP).get(
            "TRANSFORMALGORITHM"
        )
        if algo == COMPRESS_ALGO_BZIP2:
            return COMPRESSION_7Z_BZIP
        elif algo == COMPRESS_ALGO_LZMA:
            return COMPRESSION_7Z_LZMA
        elif algo == COMPRESS_ALGO_7Z_COPY:
            return COMPRESSION_7Z_COPY
        else:
            LOGGER.warning(
                "Unable to determine reingested compression"
                " algorithm, defaulting to bzip2."
            )
            return COMPRESSION_7Z_BZIP
    elif puid == PRONOM_BZIP2:  # Bzipped (probably tar)
        return COMPRESSION_TAR_BZIP2
    elif puid == PRONOM_GZIP:
        return COMPRESSION_TAR_GZIP
    else:
        LOGGER.warning(
            "Unable to determine reingested file format,"
            " defaulting recompression algorithm to bzip2."
        )
        return COMPRESSION_7Z_BZIP


def get_compress_command(compression, extract_path, basename, full_path):
    """Return command for compressing the package

    :param compression: one of the constants in ``COMPRESSION_ALGORITHMS``.
    :param extract_path: target path for the compressed file
    :param basename: base name of the file (without extension)
    :param full_path: Path of source files
    :returns: (command, compressed_filename) where
        `command` is the compression command (as a list of strings)
        `compressed_filename` is the full path to the compressed file
    """
    if compression in (COMPRESSION_TAR, COMPRESSION_TAR_BZIP2, COMPRESSION_TAR_GZIP):
        compressed_filename = os.path.join(extract_path, basename + TAR_EXTENSION)
        relative_path = os.path.dirname(full_path)
        algo = ""
        if compression == COMPRESSION_TAR_BZIP2:
            algo = "-j"  # Compress with bzip2
            compressed_filename += ".bz2"
        elif compression == COMPRESSION_TAR_GZIP:
            algo = "-z"  # Compress with gzip
            compressed_filename += ".gz"
        command = [
            "tar",
            "c",  # Create tar
            algo,  # Optional compression flag
            "-C",
            relative_path,  # Work in this directory
            "-f",
            compressed_filename,  # Output file
            os.path.basename(full_path),  # Relative path to source files
        ]
    elif compression in (COMPRESSION_7Z_BZIP, COMPRESSION_7Z_LZMA, COMPRESSION_7Z_COPY):
        compressed_filename = os.path.join(extract_path, basename + ".7z")
        if compression == COMPRESSION_7Z_BZIP:
            algo = COMPRESS_ALGO_BZIP2
        elif compression == COMPRESSION_7Z_LZMA:
            algo = COMPRESS_ALGO_LZMA
        elif compression == COMPRESSION_7Z_COPY:
            algo = COMPRESS_ALGO_7Z_COPY
        command = [
            "7z",
            "a",  # Add
            "-bd",  # Disable percentage indicator
            "-t7z",  # Type of archive
            "-y",  # Assume Yes on all queries
            "-m0=" + algo,  # Compression method
            "-mtc=on",
            "-mtm=on",
            "-mta=on",  # Keep timestamps (create, mod, access)
            "-mmt=on",  # Multithreaded
            compressed_filename,  # Destination
            full_path,  # Source
        ]

    else:
        raise NotImplementedError(
            _("Algorithm %(algorithm)s not implemented") % {"algorithm": compression}
        )

    command = list(_f for _f in command if _f)
    return (command, compressed_filename)


def get_compressed_package_checksum(pointer_path):
    """Return the checksum (and algorithm) for a compressed package as
    documented in the pointer file at ``pointer_path``.

    :param pointer_path: path to xml pointer file
    :returns: tuple(str: checksum, str: checksum_algorithm)`.
    """
    doc = etree.parse(pointer_path)

    checksum = doc.findtext(".//premis:messageDigest", namespaces=NSMAP)
    if checksum is None:
        # Try the PREMIS3 namespace as the pointer file may be newer.
        checksum = doc.findtext(".//premis3:messageDigest", namespaces=NSMAP)
    checksum_algorithm = doc.findtext(
        ".//premis:messageDigestAlgorithm", namespaces=NSMAP
    )
    if checksum_algorithm is None:
        checksum_algorithm = doc.findtext(
            ".//premis3:messageDigestAlgorithm", namespaces=NSMAP
        )

    return (checksum, checksum_algorithm)


def get_tool_info_command(compression):
    """Return command for outputting compression tool details

    :param compression: one of the constants in ``COMPRESSION_ALGORITHMS``.
    :returns: command in string format
    """
    if compression in (COMPRESSION_TAR, COMPRESSION_TAR_BZIP2, COMPRESSION_TAR_GZIP):
        algo = {COMPRESSION_TAR_BZIP2: "-j", COMPRESSION_TAR_GZIP: "-z"}.get(
            compression, ""
        )

        tool_info_command = (
            'echo program="tar"\\; '
            'algorithm="{}"\\; '
            'version="`tar --version | grep tar`"'.format(algo)
        )
    elif compression in (COMPRESSION_7Z_BZIP, COMPRESSION_7Z_LZMA, COMPRESSION_7Z_COPY):
        algo = {
            COMPRESSION_7Z_BZIP: COMPRESS_ALGO_BZIP2,
            COMPRESSION_7Z_LZMA: COMPRESS_ALGO_LZMA,
            COMPRESSION_7Z_COPY: COMPRESS_ALGO_7Z_COPY,
        }.get(compression, "")
        tool_info_command = (
            "#!/bin/bash\n"
            'echo program="7z"\\; '
            'algorithm="{}"\\; '
            'version="`7z | grep Version`"'.format(algo)
        )
    else:
        raise NotImplementedError(
            _("Algorithm %(algorithm)s not implemented") % {"algorithm": compression}
        )

    return tool_info_command


def get_7z_version():
    return [
        line
        for line in subprocess.check_output("7z").splitlines()
        if b"Version" in line
    ][0].decode("utf8")


def get_tar_version():
    return subprocess.check_output(["tar", "--version"]).splitlines()[0].decode("utf8")


def get_compression_event_detail(compression):
    """Return details of compression

    :param compression: one of the constants in ``COMPRESSION_ALGORITHMS``.
    :returns: compression details in string format
    """
    if compression in (COMPRESSION_7Z_BZIP, COMPRESSION_7Z_LZMA, COMPRESSION_7Z_COPY):
        try:
            version = get_7z_version()
            event_detail = f'program="7z"; version="{version}"'
        except (subprocess.CalledProcessError, Exception):
            event_detail = 'program="7z"'
    elif compression in (COMPRESSION_TAR_BZIP2, COMPRESSION_TAR, COMPRESSION_TAR_GZIP):
        try:
            version = get_tar_version()
            event_detail = f'program="tar"; version="{version}"'
        except (subprocess.CalledProcessError, Exception):
            event_detail = 'program="tar"'
    else:
        LOGGER.warning(
            "Unknown compression algorithm, cannot correctly update pointer file"
        )
        event_detail = _("Unknown compression")

    return event_detail


def set_compression_transforms(aip, compression, transform_order):
    """Set transform files based on the compression mechanism.

    Return information for compressing the package

    :param aip: metsrw FSEntry representing the AIP
    :param compression: one of the constants in ``COMPRESSION_ALGORITHMS``.
    :param transform_order: initial order for the transforms
    :returns: (version, extension, program_name) where
        `version` is the version of the program to compress the AIP
        `extension` is the file extension of the compressed AIP
        `program_name` is the name of the program to compress the AIP
    """
    if compression in (COMPRESSION_7Z_BZIP, COMPRESSION_7Z_LZMA, COMPRESSION_7Z_COPY):
        if compression == COMPRESSION_7Z_BZIP:
            algo = COMPRESS_ALGO_BZIP2
        elif compression == COMPRESSION_7Z_LZMA:
            algo = COMPRESS_ALGO_LZMA
        elif compression == COMPRESSION_7Z_COPY:
            algo = COMPRESS_ALGO_7Z_COPY
        aip.transform_files.append(
            {
                "algorithm": algo,
                "order": str(transform_order),
                "type": DECOMPRESS_TRANSFORM_TYPE,
            }
        )
        version = get_7z_version()
        extension = COMPRESS_EXTENSION_7Z
        program_name = "7-Zip"

    elif compression in (COMPRESSION_TAR_BZIP2, COMPRESSION_TAR):
        if compression == COMPRESSION_TAR_BZIP2:
            aip.transform_files.append(
                {
                    "algorithm": COMPRESS_ALGO_BZIP2,
                    "order": str(transform_order),
                    "type": DECOMPRESS_TRANSFORM_TYPE,
                }
            )
            transform_order += 1

        aip.transform_files.append(
            {
                "algorithm": COMPRESS_ALGO_TAR,
                "order": str(transform_order),
                "type": DECOMPRESS_TRANSFORM_TYPE,
            }
        )
        version = get_tar_version()
        extension = COMPRESS_EXTENSION_BZIP2
        program_name = "tar"

    elif compression == COMPRESSION_TAR_GZIP:
        aip.transform_files.append(
            {
                "algorithm": COMPRESS_ALGO_GZIP,
                "order": str(transform_order),
                "type": DECOMPRESS_TRANSFORM_TYPE,
            }
        )
        transform_order += 1
        aip.transform_files.append(
            {
                "algorithm": COMPRESS_ALGO_TAR,
                "order": str(transform_order),
                "type": DECOMPRESS_TRANSFORM_TYPE,
            }
        )
        version = get_tar_version()
        extension = COMPRESS_EXTENSION_GZIP
        program_name = "tar"

    else:
        raise ValueError("Unknown compression algorithm")

    return version, extension, program_name


# ########### TAR Packaging ############


class TARException(Exception):
    pass


def create_tar(path, extension=False):
    """Create a tarfile from the directory at ``path`` and overwrite
    ``path`` with that tarfile.

    :param path: Path to directory or file to tar (str)
    :param extension: Flag indicating whether to add .tar extension (bool)
    """
    path = path.rstrip("/")
    tarpath = f"{path}{TAR_EXTENSION}"
    changedir = os.path.dirname(tarpath)
    source = os.path.basename(path)
    cmd = ["tar", "-C", changedir, "-cf", tarpath, source]
    LOGGER.info(
        "creating archive of %s at %s, relative to %s", source, tarpath, changedir
    )
    fail_msg = "Failed to create a tarfile at {tarpath} for dir at {path}".format(
        tarpath=tarpath, path=path
    )
    try:
        subprocess.check_output(cmd)
    except (OSError, subprocess.CalledProcessError):
        raise TARException(fail_msg)

    # Providing the TAR is successfully created then remove the original.
    if os.path.isfile(tarpath) and tarfile.is_tarfile(tarpath):
        try:
            shutil.rmtree(path)
        except OSError:
            # Remove a file-path as We're likely packaging a file, e.g. 7z.
            os.remove(path)
        if not extension:
            os.rename(tarpath, path)
    else:
        raise TARException(fail_msg)

    if not tarfile.is_tarfile(tarpath if extension else path):
        raise TARException(fail_msg)

    if os.path.exists(path if extension else tarpath):
        raise TARException(fail_msg)


def extract_tar(tarpath):
    """Extract tarfile at ``path`` to a directory at ``path``.

    :param tarpath: Path to tarfile to extract (str)
    """
    newtarpath = tarpath
    newtarpath = f"{tarpath}{TAR_EXTENSION}"
    os.rename(tarpath, newtarpath)
    changedir = os.path.dirname(newtarpath)
    cmd = ["tar", "-xf", newtarpath, "-C", changedir]
    try:
        subprocess.check_output(cmd)
    except (OSError, subprocess.CalledProcessError) as err:
        fail_msg = _(
            "Failed to extract %(tarpath)s: %(error)s"
            % {"tarpath": tarpath, "error": err}
        )
        os.rename(newtarpath, tarpath)
        raise TARException(fail_msg)
    os.remove(newtarpath)


# ########### OTHER ############


def generate_checksum(file_path, checksum_type="md5"):
    """
    Returns checksum object for `file_path` using `checksum_type`.

    If `file_path` is a directory (i.e. an uncompressed package), return the
    checksum of the Bag tag-manifest file. This allows us to later validate
    that this is the correct AIP.

    If checksum_type is not a valid checksum, ValueError raised by hashlib.
    """
    checksum = hashlib.new(checksum_type)

    if os.path.isdir(file_path):
        file_path = find_tagmanifest(file_path)

    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(128 * checksum.block_size), b""):
            checksum.update(chunk)
    return checksum


def find_tagmanifest(file_path):
    """Return the path to a Bag's tagmanifest file.

    If there are multiple, return the first of sha512, sha256, or md5,
    respecting the BagIt spec's preference for sha512 or sha256, respectively.
    """
    if not os.path.isdir(file_path):
        return

    bag_files = os.listdir(file_path)
    tagmanifest_files = [
        "tagmanifest-sha512.txt",
        "tagmanifest-sha256.txt",
        "tagmanifest-md5.txt",
    ]

    for tagmanifest in tagmanifest_files:
        if tagmanifest in bag_files:
            return os.path.join(file_path, tagmanifest)


def uuid_to_path(uuid):
    """Converts a UUID into a path.

    Every 4 alphanumeric characters of the UUID become a folder name."""
    uuid = uuid.replace("-", "")
    path = [uuid[i : i + 4] for i in range(0, len(uuid), 4)]
    path = os.path.join(*path)
    LOGGER.debug("path %s", path)
    return path


def removedirs(relative_path, base=None):
    """Removes leaf directory of relative_path and all empty directories in
    relative_path, but nothing from base.

    Cribbed from the implementation of os.removedirs.

    :param relative_path: quad-dir structure,
        e.g. aa9a/f3b1/32ae/4f3e/8841/0539/568c/43f2 (path-string)
    :param base: root location of quad-dir structure,
        e.g. /var/archivematica/storage_service (path-string, (optional))
    """
    if not base:
        return os.removedirs(relative_path)
    try:
        os.rmdir(os.path.join(base, relative_path))
    except os.error:
        pass
    head, tail = os.path.split(relative_path)
    if not tail:
        head, tail = os.path.split(head)
    while head and tail:
        try:
            os.rmdir(os.path.join(base, head))
        except os.error:
            break
        head, tail = os.path.split(head)


def strip_quad_dirs_from_path(dest_path):
    """Return dest_path with UUID quad directories removed.

    Ensure that paths to uncompressed packages terminate in a trailing slash.
    """
    UUID4_QUAD = re.compile(r"[0-9a-f]{4}\Z", re.I)
    dest_path = dest_path.rstrip("/")
    output_path, package_name = os.path.split(dest_path)
    for quad_dir in range(8):
        head, tail = os.path.split(output_path)
        if not re.match(UUID4_QUAD, tail):
            continue
        output_path = head
    output_path = os.path.join(output_path, package_name)
    for extension in PACKAGE_EXTENSIONS:
        if output_path.endswith(extension):
            return output_path
    return os.path.join(output_path, "")


StorageEffects = namedtuple(
    "StorageEffects", ["events", "composition_level_updater", "inhibitors"]
)


def recalculate_size(rein_aip_internal_path):
    """Recalculate the size of a re-ingested AIP typically: it may have changed
    because of changed preservation derivatives or because of a metadata-only
    reingest. If the AIP is a directory, then calculate the size recursively.
    """
    if os.path.isdir(rein_aip_internal_path):
        size = 0
        for dirpath, ___, filenames in scandir.walk(rein_aip_internal_path):
            for filename in filenames:
                file_path = os.path.join(dirpath, filename)
                size += os.path.getsize(file_path)
    else:
        size = os.path.getsize(rein_aip_internal_path)
    return size


def package_is_file(path):
    """Rudimentary test to identify whether a path describes that of a file,
    or a directory. As paths are usually abstract, i.e. stored in the database,
    we can't (usually) simply test whether the object is a file on disk.
    """
    for ext in PACKAGE_EXTENSIONS:
        if path.endswith(ext):
            return True
    return False


def get_mimetype(path):
    """Returns a file's mimetype based on its extension.
    Returns None if unable to determine the mimetype.
    """
    return mimetypes.guess_type(path)[0]
