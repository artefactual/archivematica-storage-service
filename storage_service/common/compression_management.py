# -*- coding: utf-8 -*-

"""Compression Management Functions.

Module for working with compression across the storage service, e.g. for
decompressing AIPs prior to reingest.

Notes on unar:

    The command used to extract the compressed file at
    full_path was, previously, universally::

        $ unar -force-overwrite -o extract_path full_path

    The problem with this command is that unar treats __MACOSX .rsrc
    ("resource fork") files differently than 7z and tar do. 7z and
    tar convert these .rsrc files to ._-prefixed files. Similar
    behavior with unar can be achieved by passing `-k hidden`.

    However, while a command like::

        $ unar -force-overwrite -k hidden -o extract_path full_path

    preserves the .rsrc MACOSX files as ._-prefixed files, it does so
    differently than 7z/tar do: the resulting .-prefixed files have
    different sizes than those created via unar.

    Files with different sizes than those recorded in a bag will result
    in an invalid bag.
"""

import logging
import os
import subprocess

from lxml import etree


class PackageExtractException(Exception):
    """Exceptions related to extracting packages."""
    pass


LOGGER = logging.getLogger(__name__)

# Different compression options used for storing packages.
COMPRESSION_7Z_BZIP = '7z with bzip'
COMPRESSION_7Z_LZMA = '7z with lzma'
COMPRESSION_7Z_COPY = "7z with copy"
COMPRESSION_TAR = 'tar'
COMPRESSION_TAR_BZIP2 = 'tar bz2'
COMPRESSION_7Z_GENERIC = "7z generic"
COMPRESSION_ALGORITHMS = (
    COMPRESSION_7Z_GENERIC,
    COMPRESSION_7Z_BZIP,
    COMPRESSION_7Z_LZMA,
    COMPRESSION_TAR,
    COMPRESSION_TAR_BZIP2,
)

mime_map = {
    "application/x-7z-compressed": COMPRESSION_7Z_GENERIC,
    "application/x-tar": COMPRESSION_TAR,
    "application/x-bzip2": COMPRESSION_TAR_BZIP2,
}

# XML namespace entries.
NSMAP = {
    'mets': 'http://www.loc.gov/METS/',
    'premis': 'info:lc/xmlns/premis-v2',
}


def get_compression(pointer_path, package_location=None):
    """Return the compression algorithm used to compress the package, as
    documented in the pointer file at ``pointer_path``. Returns one of the
    constants in ``COMPRESSION_ALGORITHMS``.
    """
    if not pointer_path or not os.path.isfile(pointer_path):
        LOGGER.info("Cannot access pointer file: %s", pointer_path)
        return fallback_identification(package_location)
    doc = etree.parse(pointer_path)
    puid = doc.findtext('.//premis:formatRegistryKey', namespaces=NSMAP)
    if puid == 'fmt/484':  # 7 Zip
        algo = doc.find('.//mets:transformFile',
                        namespaces=NSMAP).get('TRANSFORMALGORITHM')
        if algo == 'bzip2':
            return COMPRESSION_7Z_BZIP
        elif algo == 'lzma':
            return COMPRESSION_7Z_LZMA
        elif algo == 'copy':
            return COMPRESSION_7Z_COPY
        else:
            LOGGER.warning('Unable to determine reingested compression'
                           ' algorithm, defaulting to bzip2.')
            return COMPRESSION_7Z_BZIP
    elif puid == 'x-fmt/268':  # Bzipped (probably tar)
        return COMPRESSION_TAR_BZIP2
    else:
        LOGGER.warning('Unable to determine reingested file format,'
                       ' defaulting recompression algorithm to bzip2.')
        return COMPRESSION_7Z_BZIP


def get_decompr_cmd(compression, extract_path, full_path):
    """Get Decompression Command.

    Returns a decompression command as a list, given a compression algorithm
    found in COMPRESSION_ALGORITHMS.
    """
    if compression in \
            (
                COMPRESSION_7Z_BZIP,
                COMPRESSION_7Z_LZMA,
                COMPRESSION_7Z_COPY,
                COMPRESSION_7Z_GENERIC
            ):
        return ['7z', 'x', '-bd', '-y', '-o{0}'.format(extract_path),
                full_path]
    elif compression == COMPRESSION_TAR_BZIP2:
        return ['/bin/tar', 'xvjf', full_path, '-C', extract_path]
    return ['unar', '-force-overwrite', '-o', extract_path, full_path]


def extract_files(
        pointer_file_path, extract_path, full_path,
        output_path, relative_path):
    """Extract files from a compressed package."""
    command = get_decompr_cmd(
        get_compression(pointer_file_path, full_path), extract_path, full_path)
    if relative_path:
        command.append(relative_path)
    LOGGER.info('Extracting file with: %s to %s', command, output_path)
    try:
        subprocess.check_output(command)
    except subprocess.CalledProcessError as err:
        err_str = "Extract: returned non-zero exit status {}"\
            .format(err.returncode)
        LOGGER.error(err_str)
        LOGGER.error(err.output)
        raise PackageExtractException(err_str)
    # Not every extraction tool responds the same, some will error when nothing
    # is extracted, some will not, so test the response on its merit, i.e.
    # if a file or path exists at the extract_path.
    path_to_test = extract_path
    if relative_path:
        path_to_test = os.path.join(path_to_test, relative_path)
    if not os.path.exists(path_to_test):
        err_str = "Extraction error: no files extracted"
        LOGGER.error(err_str)
        raise PackageExtractException(err_str)


def _return_compression(file_output):
    """Split the $file command output and return the compression type."""
    try:
        mime_type = file_output.rsplit(":")[1].strip()
    except IndexError:
        return None
    return mime_map.get(mime_type, None)


def fallback_identification(package_location):
    """Attempt to identify our package using Linux's $file utility."""
    file_cmd = ['file', "-F", ":", "--mime-type", package_location]
    try:
        file_output = subprocess.check_output(file_cmd)
    except subprocess.CalledProcessError as err:
        err_str = "Identify compression: returned non-zero exit status {}"\
            .format(err.returncode)
        LOGGER.error(err_str)
        return None
    return _return_compression(file_output)
