# -*- coding: utf-8 -*-

"""Compression Management Functions.

Module for working with compression across the storage service, e.g. for
decompressing AIPs prior to reingest.
"""

import logging
import os

from lxml import etree


LOGGER = logging.getLogger(__name__)

# Compression options for packages
COMPRESSION_7Z_BZIP = '7z with bzip'
COMPRESSION_7Z_LZMA = '7z with lzma'
COMPRESSION_TAR = 'tar'
COMPRESSION_TAR_BZIP2 = 'tar bz2'
COMPRESSION_ALGORITHMS = (
    COMPRESSION_7Z_BZIP,
    COMPRESSION_7Z_LZMA,
    COMPRESSION_TAR,
    COMPRESSION_TAR_BZIP2,
)

NSMAP = {
    'mets': 'http://www.loc.gov/METS/',
    'premis': 'info:lc/xmlns/premis-v2',
}


def get_compression(pointer_path):
    """Return the compression algorithm used to compress the package, as
    documented in the pointer file at ``pointer_path``. Returns one of the
    constants in ``COMPRESSION_ALGORITHMS``.
    """
    if not pointer_path or not os.path.isfile(pointer_path):
        LOGGER.info("Cannot access pointer file: %s", pointer_path)
        return None  	# Unar is the fall-back without a pointer file.
    doc = etree.parse(pointer_path)
    puid = doc.findtext('.//premis:formatRegistryKey', namespaces=NSMAP)
    if puid == 'fmt/484':  # 7 Zip
        algo = doc.find('.//mets:transformFile',
                        namespaces=NSMAP).get('TRANSFORMALGORITHM')
        if algo == 'bzip2':
            return COMPRESSION_7Z_BZIP
        elif algo == 'lzma':
            return COMPRESSION_7Z_LZMA
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
    """Returns a decompression command (as a list), given ``compression``
    (one of ``COMPRESSION_ALGORITHMS``), the destination path
    ``extract_path`` and the path of the archive ``full_path``.
    """
    if compression in (COMPRESSION_7Z_BZIP, COMPRESSION_7Z_LZMA):
        return ['7z', 'x', '-bd', '-y', '-o{0}'.format(extract_path),
                full_path]
    elif compression == COMPRESSION_TAR_BZIP2:
        return ['/bin/tar', 'xvjf', full_path, '-C', extract_path]
    return ['unar', '-force-overwrite', '-o', extract_path, full_path]
