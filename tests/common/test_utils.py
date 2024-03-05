import os
import pathlib
import shutil
import subprocess
import tarfile
from collections import namedtuple
from io import StringIO
from unittest import mock

import pytest
from common import utils
from metsrw import FSEntry

TEST_DIR = os.path.dirname(os.path.realpath(__file__))
FIXTURES_DIR = os.path.join(TEST_DIR, "fixtures")

# Until further work is done to bring compression into its own module we can
# use these constants for this test, but we can do better.
PROG_VERS_7Z = "7z"
PROG_VERS_TAR = "tar"

# Specifically string types for the tuple we create.
COMPRESS_ORDER_ONE = "1"
COMPRESS_ORDER_TWO = "2"

ExTarCase = namedtuple("ExTarCase", "path isdir raises expected")
CrTarCase = namedtuple("CrTarCase", "path isfile istar raises expected extension")


@pytest.mark.parametrize(
    "pronom,algorithm,compression",
    [
        (utils.PRONOM_7Z, utils.COMPRESS_ALGO_BZIP2, utils.COMPRESSION_7Z_BZIP),
        (utils.PRONOM_7Z, utils.COMPRESS_ALGO_LZMA, utils.COMPRESSION_7Z_LZMA),
        (utils.PRONOM_7Z, utils.COMPRESS_ALGO_7Z_COPY, utils.COMPRESSION_7Z_COPY),
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
    ), "Incorrect compression command: {} returned for compression input {}".format(
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
    ), "Incorrect tool info: {} returned for compression input {}".format(
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
    # subprocess.check_output returns bytes in python3
    mock_subprocess.return_value = cmd_output.encode("utf8")
    detail = utils.get_compression_event_detail(compression)

    assert (
        detail == expected_detail
    ), "Incorrect detail: {} returned for compression input {}".format(
        detail, compression
    )


@pytest.mark.parametrize(
    "compression, version,extension,program_name,transform",
    [
        (
            utils.COMPRESSION_7Z_BZIP,
            PROG_VERS_7Z,
            utils.COMPRESS_EXTENSION_7Z,
            utils.COMPRESS_PROGRAM_7Z,
            [
                {
                    "type": utils.DECOMPRESS_TRANSFORM_TYPE,
                    "order": COMPRESS_ORDER_ONE,
                    "algorithm": utils.COMPRESS_ALGO_BZIP2,
                }
            ],
        ),
        (
            utils.COMPRESSION_7Z_LZMA,
            PROG_VERS_7Z,
            utils.COMPRESS_EXTENSION_7Z,
            utils.COMPRESS_PROGRAM_7Z,
            [
                {
                    "type": utils.DECOMPRESS_TRANSFORM_TYPE,
                    "order": COMPRESS_ORDER_ONE,
                    "algorithm": utils.COMPRESS_ALGO_LZMA,
                }
            ],
        ),
        (
            utils.COMPRESSION_7Z_COPY,
            PROG_VERS_7Z,
            utils.COMPRESS_EXTENSION_7Z,
            utils.COMPRESS_PROGRAM_7Z,
            [
                {
                    "type": utils.DECOMPRESS_TRANSFORM_TYPE,
                    "order": COMPRESS_ORDER_ONE,
                    "algorithm": utils.COMPRESS_ALGO_7Z_COPY,
                }
            ],
        ),
        (
            utils.COMPRESSION_TAR_BZIP2,
            PROG_VERS_TAR,
            utils.COMPRESS_EXTENSION_BZIP2,
            utils.COMPRESS_PROGRAM_TAR,
            [
                {
                    "type": utils.DECOMPRESS_TRANSFORM_TYPE,
                    "order": COMPRESS_ORDER_ONE,
                    "algorithm": utils.COMPRESS_ALGO_BZIP2,
                },
                {
                    "type": utils.DECOMPRESS_TRANSFORM_TYPE,
                    "order": COMPRESS_ORDER_TWO,
                    "algorithm": utils.COMPRESS_ALGO_TAR,
                },
            ],
        ),
        (
            utils.COMPRESSION_TAR_GZIP,
            PROG_VERS_TAR,
            utils.COMPRESS_EXTENSION_GZIP,
            utils.COMPRESS_PROGRAM_TAR,
            [
                {
                    "type": utils.DECOMPRESS_TRANSFORM_TYPE,
                    "order": COMPRESS_ORDER_ONE,
                    "algorithm": utils.COMPRESS_ALGO_GZIP,
                },
                {
                    "type": utils.DECOMPRESS_TRANSFORM_TYPE,
                    "order": COMPRESS_ORDER_TWO,
                    "algorithm": utils.COMPRESS_ALGO_TAR,
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
    vers, ext, prog_name = utils.set_compression_transforms(fsentry, compression, 1)
    assert version in vers
    assert ext == extension
    assert program_name in prog_name
    assert fsentry.transform_files == transform


@pytest.mark.parametrize(
    "package_path,is_file",
    [
        (
            "8ac0/d76b/b01e/47b1/8ca8/0fe8/0edb/e7b9/repl2-8ac0d76b-b01e-47b1-8ca8-0fe80edbe7b9.7z",
            True,
        ),
        (
            "cee5/a604/93d8/4253/a666/2f73/a19c/f835/repl13-cee5a604-93d8-4253-a666-2f73a19cf835.tar.gz",
            True,
        ),
        (
            "0eb3/ae66/2e7c/4982/bc85/23aa/697a/7dec/repl12-0eb3ae66-2e7c-4982-bc85-23aa697a7dec",
            False,
        ),
        (
            "ab9c/d802/7c7b/4377/8742/4685/d09b/6d75/repl11-ab9cd802-7c7b-4377-8742-4685d09b6d75.tar.bz2",
            True,
        ),
    ],
)
def test_package_is_file(package_path, is_file):
    """Ensure that we return is_file accurately for the types of path we will
    see in the storage service.
    """
    assert utils.package_is_file(package_path) == is_file


@pytest.mark.parametrize(
    "path, will_be_dir, sp_raises, expected",
    [
        ExTarCase(path="/a/b/c", isdir=True, raises=False, expected="success"),
        ExTarCase(path="/a/b/d", isdir=False, raises=True, expected="fail"),
        ExTarCase(path="/a/b/c", isdir=True, raises=True, expected="fail"),
    ],
)
def test_extract_tar(mocker, path, will_be_dir, sp_raises, expected):
    if sp_raises:
        mocker.patch.object(subprocess, "check_output", side_effect=OSError("gotcha!"))
    else:
        mocker.patch.object(subprocess, "check_output")
    mocker.patch.object(pathlib.Path, "rename")
    mocker.patch.object(pathlib.Path, "unlink")
    if will_be_dir:
        mocker.patch.object(pathlib.Path, "is_dir", return_value=True)
    else:
        mocker.patch.object(pathlib.Path, "is_dir", return_value=False)
    path = pathlib.Path(path)
    tarpath_ext = path.with_suffix(".tar")
    dirname = tarpath_ext.parent
    if expected == "success":
        ret = utils.extract_tar(path)
        assert ret is None
        tarpath_ext.unlink.assert_called_once()
    else:
        with pytest.raises(utils.TARException) as excinfo:
            ret = utils.extract_tar(path)
        assert f"Failed to extract {path}: gotcha!" == str(excinfo.value)
        tarpath_ext.rename.assert_any_call(path)
        assert not pathlib.Path.unlink.called
    path.rename.assert_any_call(tarpath_ext)
    subprocess.check_output.assert_called_once_with(
        ["tar", "-xf", tarpath_ext, "-C", dirname]
    )


@pytest.mark.parametrize(
    "path, will_be_file, will_be_tar, sp_raises, expected, extension",
    [
        CrTarCase(
            path="/a/b/c",
            isfile=True,
            istar=True,
            raises=False,
            expected="success",
            extension=False,
        ),
        CrTarCase(
            path="/a/b/c/",
            isfile=True,
            istar=True,
            raises=False,
            expected="success",
            extension=False,
        ),
        CrTarCase(
            path="/a/b/c",
            isfile=True,
            istar=False,
            raises=False,
            expected="fail",
            extension=False,
        ),
        CrTarCase(
            path="/a/b/c",
            isfile=False,
            istar=True,
            raises=False,
            expected="fail",
            extension=False,
        ),
        CrTarCase(
            path="/a/b/c",
            isfile=False,
            istar=False,
            raises=True,
            expected="fail",
            extension=False,
        ),
        CrTarCase(
            path="/a/b/c",
            isfile=True,
            istar=True,
            raises=False,
            expected="success",
            extension=True,
        ),
        CrTarCase(
            path="/a/b/c/",
            isfile=True,
            istar=True,
            raises=False,
            expected="success",
            extension=True,
        ),
    ],
)
def test_create_tar(
    mocker, path, will_be_file, will_be_tar, sp_raises, expected, extension
):
    if sp_raises:
        mocker.patch.object(subprocess, "check_output", side_effect=OSError("gotcha!"))
    else:
        mocker.patch.object(subprocess, "check_output")
    mocker.patch.object(pathlib.Path, "is_file", return_value=will_be_file)
    mocker.patch.object(tarfile, "is_tarfile", return_value=will_be_tar)
    mocker.patch.object(pathlib.Path, "rename")
    mocker.patch.object(shutil, "rmtree")
    fixed_path = pathlib.Path(path)
    tarpath = fixed_path.with_suffix(".tar")
    if expected == "success":
        ret = utils.create_tar(path)
        shutil.rmtree.assert_called_once_with(fixed_path)
        tarpath.rename.assert_called_once_with(fixed_path)
        tarfile.is_tarfile.assert_any_call(fixed_path)
        assert ret is None
    else:
        with pytest.raises(utils.TARException) as excinfo:
            ret = utils.create_tar(path, extension=extension)
        assert "Failed to create a tarfile at {} for dir at {}".format(
            tarpath, fixed_path
        ) == str(excinfo.value)
        assert not shutil.rmtree.called
        assert not pathlib.Path.rename.called
    if not sp_raises:
        tarpath.is_file.assert_called_once()
        if will_be_file:
            tarfile.is_tarfile.assert_any_call(tarpath)
        if extension:
            assert tarpath.suffix == utils.TAR_EXTENSION


@pytest.mark.parametrize(
    "input_path, expected_path",
    [
        # Ensure UUID quad dirs are removed.
        (
            "/var/archivematica/sharedDirectory/www/offlineReplicas/d8a4/d502/30b7/4902/b545/9c87/8242/f96c/uncompressed-test-d8a4d502-30b7-4902-b545-9c878242f96c",
            "/var/archivematica/sharedDirectory/www/offlineReplicas/uncompressed-test-d8a4d502-30b7-4902-b545-9c878242f96c/",
        ),
        (
            "/var/archivematica/sharedDirectory/www/offlineReplicas/d8a4/d502/30b7/4902/b545/9c87/8242/f96c/uncompressed-test-d8a4d502-30b7-4902-b545-9c878242f96c/",
            "/var/archivematica/sharedDirectory/www/offlineReplicas/uncompressed-test-d8a4d502-30b7-4902-b545-9c878242f96c/",
        ),
        (
            "/var/archivematica/sharedDirectory/www/offlineReplicas/2965/2761/a5b2/4da9/9af8/ffb4/bc06/2439/compressed-replica-29652761-a5b2-4da9-9af8-ffb4bc062439.7z",
            "/var/archivematica/sharedDirectory/www/offlineReplicas/compressed-replica-29652761-a5b2-4da9-9af8-ffb4bc062439.7z",
        ),
        # Ensure other directories are not removed.
        (
            "/var/archivematica/sharedDirectory/www/offlineReplicas/test-file.tar",
            "/var/archivematica/sharedDirectory/www/offlineReplicas/test-file.tar",
        ),
        (
            "/var/archivematica/sharedDirectory/www/offlineReplicas/test/package.tar.gz",
            "/var/archivematica/sharedDirectory/www/offlineReplicas/test/package.tar.gz",
        ),
        # Ensure directories terminate in slash, even if path contains dots.
        (
            "/var/archivematica/sharedDirectory/www/offlineReplicas/d8a4/d502/30b7/4902/b545/9c87/8242/f96c/uncompressed.test.1-d8a4d502-30b7-4902-b545-9c878242f96c",
            "/var/archivematica/sharedDirectory/www/offlineReplicas/uncompressed.test.1-d8a4d502-30b7-4902-b545-9c878242f96c/",
        ),
    ],
)
def test_strip_quad_dirs_from_path(input_path, expected_path):
    assert utils.strip_quad_dirs_from_path(input_path) == expected_path


@pytest.mark.parametrize(
    "dir_listing, tagmanifest_file",
    [
        # Includes tagmanifest-md5.txt.
        (["bag-info.txt", "data", "tagmanifest-md5.txt"], "tagmanifest-md5.txt"),
        # Includes tagmanifest-sha256.txt.
        (["bag-info.txt", "tagmanifest-sha256.txt", "data"], "tagmanifest-sha256.txt"),
        # Does not include tagmanifest.
        (["bag-info.txt", "data"], None),
        # Includes multiple tagmanifests.
        (
            ["tagmanifest-sha256.txt", "tagmanifest-sha512.txt", "tagmanifest-md5.txt"],
            "tagmanifest-sha512.txt",
        ),
        (["tagmanifest-sha256.txt", "tagmanifest-md5.txt"], "tagmanifest-sha256.txt"),
        (["tagmanifest-md5.txt"], "tagmanifest-md5.txt"),
    ],
)
def test_find_tagmanifest(mocker, tmp_path, dir_listing, tagmanifest_file):
    aip_path = tmp_path / "aip"
    aip_path.mkdir()
    mock_files = [aip_path / file_ for file_ in dir_listing]
    mocker.patch.object(pathlib.Path, "iterdir", return_value=mock_files)

    if tagmanifest_file is None:
        assert utils.find_tagmanifest(aip_path) is None
    else:
        assert utils.find_tagmanifest(aip_path) == aip_path / tagmanifest_file

    file_path = aip_path / "file.txt"
    file_path.write_text("test data")
    assert utils.find_tagmanifest(file_path) is None


def test_generate_checksum_uncompressed_aip(mocker, tmp_path):
    aip_path = tmp_path / "aip"
    aip_path.mkdir()
    tagmanifest = aip_path / "tagmanifest-md5.txt"
    tagmanifest.write_text("some test data")

    mocker.patch.object(pathlib.Path, "is_dir", return_value=True)
    find_tag_manifest = mocker.patch(
        "common.utils.find_tagmanifest", return_value=tagmanifest
    )

    utils.generate_checksum(aip_path)
    find_tag_manifest.assert_called_once()
    find_tag_manifest.assert_called_with(aip_path)


def test_get_compressed_package_checksum():
    premis_2_xml = (
        '<?xml version="1.0"?>'
        '<mets:mets xmlns:mets="http://www.loc.gov/METS/" xmlns:premis="info:lc/xmlns/premis-v2">'
        "<premis:fixity>"
        "  <premis:messageDigestAlgorithm>sha256</premis:messageDigestAlgorithm>"
        "  <premis:messageDigest>c2924159fcbbeadf8d7f3962b43ec1bf301e1b4f12dd28a8b89ec819f3714747</premis:messageDigest>"
        "</premis:fixity>"
        "</mets:mets>"
    )
    assert utils.get_compressed_package_checksum(StringIO(premis_2_xml)) == (
        "c2924159fcbbeadf8d7f3962b43ec1bf301e1b4f12dd28a8b89ec819f3714747",
        "sha256",
    )

    # Test PREMIS 3 from fixture.
    assert utils.get_compressed_package_checksum(
        os.path.join(FIXTURES_DIR, "premis_3_pointer.xml")
    ) == ("c2924159fcbbeadf8d7f3962b43ec1bf301e1b4f12dd28a8b89ec819f3714747", "sha256")


def test_get_mimetype():
    assert utils.get_mimetype("video.mp4") == "video/mp4"
    assert utils.get_mimetype("C:\\Windows\\Path\\windowsfile.xml") == "application/xml"
    assert utils.get_mimetype("/var/lib/file.txt") == "text/plain"
    assert utils.get_mimetype("undetermined") is None
