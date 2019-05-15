from StringIO import StringIO

import mock
import pytest

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
    "compression,expected_transforms",
    [
        (utils.COMPRESSION_7Z_BZIP, ["bzip2"]),
        (utils.COMPRESSION_7Z_LZMA, ["lzma"]),
        (utils.COMPRESSION_7Z_COPY, ["copy"]),
        (utils.COMPRESSION_TAR, ["tar"]),
        (utils.COMPRESSION_TAR_BZIP2, ["bzip2", "tar"]),
        (utils.COMPRESSION_TAR_GZIP, ["gzip", "tar"]),
    ],
)
def test_get_compression_transforms(compression, expected_transforms):
    transforms = utils.get_compression_transforms(compression, 1)

    assert len(transforms) == len(expected_transforms)
    for t1, t2 in zip(transforms, expected_transforms):
        assert t1.tag.endswith(
            "transformFile"
        ), "Incorrect tag {0} for transform".format(t1.tag)
        assert (
            t1.attrib["TRANSFORMALGORITHM"] == t2
        ), "Incorrect algorithm: {0} returned for {1}".format(
            t1.attrib["TRANSFORMALGORITHM"], compression
        )


@pytest.mark.parametrize(
    "compression,name,pronom,program",
    [
        (utils.COMPRESSION_7Z_BZIP, "7Zip format", utils.PRONOM_7Z, "7-Zip"),
        (utils.COMPRESSION_7Z_LZMA, "7Zip format", utils.PRONOM_7Z, "7-Zip"),
        (utils.COMPRESSION_7Z_COPY, "7Zip format", utils.PRONOM_7Z, "7-Zip"),
        (
            utils.COMPRESSION_TAR_BZIP2,
            "BZIP2 Compressed Archive",
            utils.PRONOM_BZIP2,
            "tar",
        ),
        (
            utils.COMPRESSION_TAR_GZIP,
            "GZIP Compressed Archive",
            utils.PRONOM_GZIP,
            "tar",
        ),
    ],
)
def test_get_format_info(compression, name, pronom, program):
    info = utils.get_format_info(compression)

    assert info["name"] == name
    assert info["registry_key"] == pronom
    assert info["program_name"] == program
