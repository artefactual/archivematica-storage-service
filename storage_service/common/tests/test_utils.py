from StringIO import StringIO

import mock
import pytest

from metsrw import FSEntry

from common import utils


@pytest.mark.parametrize(
    "pronom,algorithm,compression",
    [
        (utils.PRONOM_7Z, "bzip2", utils.COMPRESSION_7Z_BZIP),
        (utils.PRONOM_7Z, "lzma", utils.COMPRESSION_7Z_LZMA),
        (utils.PRONOM_7Z, "copy", utils.COMPRESSION_7Z_COPY),
        (utils.PRONOM_7Z, "unknown algo", utils.COMPRESSION_7Z_BZIP),
        (utils.PRONOM_BZIP2, "", utils.COMPRESSION_TAR_BZIP2),
        (utils.PRONOM_GZIP, "", utils.COMPRESSION_TAR_GZIP),
        ("unknown pronom", "", utils.COMPRESSION_7Z_BZIP),
    ],
)
def test_get_compression(pronom, algorithm, compression):
    xml = (
        '<?xml version="1.0"?>'
        '<mets:mets xmlns:mets="http://www.loc.gov/METS/" xmlns:premis="info:lc/xmlns/premis-v2">'
        " <premis:formatRegistryKey>%s</premis:formatRegistryKey>"
        ' <mets:transformFile TRANSFORMALGORITHM="%s"></mets:transformFile>'
        "</mets:mets>"
    ) % (pronom, algorithm)

    assert (
        utils.get_compression(StringIO(xml)) == compression
    ), "Incorrect compression value: {} returned for XML (pointer file) input".format(
        compression
    )


@pytest.mark.parametrize(
    "compression,command",
    [
        (
            utils.COMPRESSION_7Z_BZIP,
            "7z a -bd -t7z -y -m0=bzip2 -mtc=on -mtm=on -mta=on -mmt=on /extract/filename.7z /full/path",
        ),
        (
            utils.COMPRESSION_7Z_LZMA,
            "7z a -bd -t7z -y -m0=lzma -mtc=on -mtm=on -mta=on -mmt=on /extract/filename.7z /full/path",
        ),
        (
            utils.COMPRESSION_7Z_COPY,
            "7z a -bd -t7z -y -m0=copy -mtc=on -mtm=on -mta=on -mmt=on /extract/filename.7z /full/path",
        ),
        (utils.COMPRESSION_TAR, "tar c -C /full -f /extract/filename.tar path"),
        (
            utils.COMPRESSION_TAR_GZIP,
            "tar c -z -C /full -f /extract/filename.tar.gz path",
        ),
        (
            utils.COMPRESSION_TAR_BZIP2,
            "tar c -j -C /full -f /extract/filename.tar.bz2 path",
        ),
    ],
)
def test_get_compress_command(compression, command):
    cmd, _ = utils.get_compress_command(
        compression, "/extract/", "filename", "/full/path"
    )
    assert (
        " ".join(cmd) == command
    ), "Incorrect compression command: {0} returned for compression input {1}".format(
        cmd, compression
    )


@pytest.mark.parametrize(
    "compression,command",
    [
        (
            utils.COMPRESSION_7Z_BZIP,
            '#!/bin/bash\necho program="7z"\\; algorithm="bzip2"\\; version="`7z | grep Version`"',
        ),
        (
            utils.COMPRESSION_7Z_LZMA,
            '#!/bin/bash\necho program="7z"\\; algorithm="lzma"\\; version="`7z | grep Version`"',
        ),
        (
            utils.COMPRESSION_7Z_COPY,
            '#!/bin/bash\necho program="7z"\\; algorithm="copy"\\; version="`7z | grep Version`"',
        ),
        (
            utils.COMPRESSION_TAR,
            'echo program="tar"\\; algorithm=""\\; version="`tar --version | grep tar`"',
        ),
        (
            utils.COMPRESSION_TAR_GZIP,
            'echo program="tar"\\; algorithm="-z"\\; version="`tar --version | grep tar`"',
        ),
        (
            utils.COMPRESSION_TAR_BZIP2,
            'echo program="tar"\\; algorithm="-j"\\; version="`tar --version | grep tar`"',
        ),
    ],
)
def test_get_tool_info_command(compression, command):
    cmd = utils.get_tool_info_command(compression)
    assert (
        cmd == command
    ), "Incorrect tool info: {0} returned for compression input {1}".format(
        cmd, compression
    )


@pytest.mark.parametrize(
    "compression,cmd_output,expected_detail",
    [
        (
            utils.COMPRESSION_7Z_BZIP,
            "7z command\nVersion 3.0\nsomething else",
            'program="7z"; version="Version 3.0"',
        ),
        (
            utils.COMPRESSION_7Z_LZMA,
            "7z command\nVersion 3.0\nsomething else",
            'program="7z"; version="Version 3.0"',
        ),
        (
            utils.COMPRESSION_7Z_COPY,
            "7z command\nVersion 3.0\nsomething else",
            'program="7z"; version="Version 3.0"',
        ),
        (
            utils.COMPRESSION_TAR,
            "tar version 2.0",
            'program="tar"; version="tar version 2.0"',
        ),
        (
            utils.COMPRESSION_TAR_GZIP,
            "tar version 2.0",
            'program="tar"; version="tar version 2.0"',
        ),
        (
            utils.COMPRESSION_TAR_BZIP2,
            "tar version 2.0",
            'program="tar"; version="tar version 2.0"',
        ),
    ],
)
@mock.patch("subprocess.check_output")
def test_get_compression_event_detail(
    mock_subprocess, compression, cmd_output, expected_detail
):
    mock_subprocess.return_value = cmd_output
    detail = utils.get_compression_event_detail(compression)

    assert (
        detail == expected_detail
    ), "Incorrect detail: {0} returned for compression input {1}".format(
        detail, compression
    )


@pytest.mark.parametrize(
    "compression, version,extension,program_name,transform",
    [
        (
            utils.COMPRESSION_7Z_BZIP,
            "7z",
            ".7z",
            "7-Zip",
            [
                {
                    "type": utils.DECOMPRESS_TRANSFORM_TYPE,
                    "order": "1",
                    "algorithm": "bzip2",
                }
            ],
        ),
        (
            utils.COMPRESSION_7Z_LZMA,
            "7z",
            ".7z",
            "7-Zip",
            [
                {
                    "type": utils.DECOMPRESS_TRANSFORM_TYPE,
                    "order": "1",
                    "algorithm": "lzma",
                }
            ],
        ),
        (
            utils.COMPRESSION_7Z_COPY,
            "7z",
            ".7z",
            "7-Zip",
            [
                {
                    "type": utils.DECOMPRESS_TRANSFORM_TYPE,
                    "order": "1",
                    "algorithm": "copy",
                }
            ],
        ),
        (
            utils.COMPRESSION_TAR_BZIP2,
            "tar",
            ".bz2",
            "tar",
            [
                {
                    "type": utils.DECOMPRESS_TRANSFORM_TYPE,
                    "order": "1",
                    "algorithm": "bzip2",
                },
                {
                    "type": utils.DECOMPRESS_TRANSFORM_TYPE,
                    "order": "2",
                    "algorithm": "tar",
                },
            ],
        ),
        (
            utils.COMPRESSION_TAR_GZIP,
            "tar",
            ".gz",
            "tar",
            [
                {
                    "type": utils.DECOMPRESS_TRANSFORM_TYPE,
                    "order": "1",
                    "algorithm": "gzip",
                },
                {
                    "type": utils.DECOMPRESS_TRANSFORM_TYPE,
                    "order": "2",
                    "algorithm": "tar",
                },
            ],
        ),
    ],
)
def test_get_format_info(compression, version, extension, program_name, transform):
    """Ensure that the format information we write per compression is
    consistent.
    """
    fsentry = FSEntry()
    vers, ext, prog_name = utils.get_compression_transforms(fsentry, compression, 1)
    assert version in vers
    assert ext == extension
    assert program_name in prog_name
    assert fsentry.transform_files == transform
