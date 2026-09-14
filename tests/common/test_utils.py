import os
import pathlib
import re
import tarfile
from collections.abc import Callable
from io import StringIO
from unittest import mock

import pytest
from metsrw import FSEntry

from archivematica.storage_service.common import utils

TEST_DIR = pathlib.Path(__file__).resolve().parent
FIXTURES_DIR = TEST_DIR / "fixtures"

# Until further work is done to bring compression into its own module we can
# use these regular expression patterns for this test, but we can do better.
PROG_VERS_7Z = r"(p7zip|7-Zip)"
PROG_VERS_TAR = r"tar"

# Specifically string types for the tuple we create.
COMPRESS_ORDER_ONE = "1"
COMPRESS_ORDER_TWO = "2"


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

    assert utils.get_compression(StringIO(xml)) == compression, (
        f"Incorrect compression value: {compression} returned for XML (pointer file) input"
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
    assert " ".join(cmd) == command, (
        f"Incorrect compression command: {cmd} returned for compression input {compression}"
    )


@pytest.mark.parametrize(
    "compression,expected_program,expected_algorithm",
    [
        (utils.COMPRESSION_7Z_BZIP, "7z", utils.COMPRESS_ALGO_BZIP2),
        (
            utils.COMPRESSION_7Z_LZMA,
            "7z",
            utils.COMPRESS_ALGO_LZMA,
        ),
        (
            utils.COMPRESSION_7Z_COPY,
            "7z",
            utils.COMPRESS_ALGO_7Z_COPY,
        ),
        (
            utils.COMPRESSION_TAR,
            "tar",
            "",
        ),
        (
            utils.COMPRESSION_TAR_GZIP,
            "tar",
            "-z",
        ),
        (
            utils.COMPRESSION_TAR_BZIP2,
            "tar",
            "-j",
        ),
    ],
)
@mock.patch("subprocess.check_output")
def test_get_tool_info(check_output, compression, expected_program, expected_algorithm):
    if expected_program == "7z":
        expected_version = "p7zip Version 16.02"
        command_output = b"\n".join(
            [
                b"",
                b"7-Zip [64] 16.02 : Copyright (c) 1999-2016 Igor Pavlov : 2016-05-21",
                expected_version.encode(),
            ]
        )
    elif expected_program == "tar":
        expected_version = "tar (GNU tar) 1.35"
        command_output = b"\n".join(
            [
                expected_version.encode(),
                b"Copyright (C) 2023 Free Software Foundation, Inc.",
            ]
        )
    else:
        raise AssertionError(f"unexpected program {expected_program}")
    check_output.return_value = command_output
    expected_output = f"program={expected_program}; algorithm={expected_algorithm}; version={expected_version}"

    output = utils.get_tool_info(compression)

    assert output == expected_output, (
        f"Incorrect tool info: {output} returned for compression input {compression}"
    )


def test_get_tool_info_fails_if_compression_algorithm_is_not_implemented():
    with pytest.raises(
        NotImplementedError, match="Algorithm unknown and random not implemented"
    ):
        utils.get_tool_info("unknown and random")


@pytest.mark.parametrize(
    "compression,cmd_output,expected_detail",
    [
        (
            utils.COMPRESSION_7Z_BZIP,
            "\n7z command\np7zip Version 3.0\nsomething else",
            'program="7z"; version="p7zip Version 3.0"',
        ),
        (
            utils.COMPRESSION_7Z_BZIP,
            "\n7-Zip 23.01 (x64)\n 64-bit locale=C.UTF-8\nsomething else",
            'program="7z"; version="7-Zip 23.01 (x64) 64-bit locale=C.UTF-8"',
        ),
        (
            utils.COMPRESSION_7Z_LZMA,
            "\n7z command\np7zip Version 3.0\nsomething else",
            'program="7z"; version="p7zip Version 3.0"',
        ),
        (
            utils.COMPRESSION_7Z_LZMA,
            "\n7-Zip 23.01 (x64)\n 64-bit locale=C.UTF-8\nsomething else",
            'program="7z"; version="7-Zip 23.01 (x64) 64-bit locale=C.UTF-8"',
        ),
        (
            utils.COMPRESSION_7Z_COPY,
            "\n7z command\np7zip Version 3.0\nsomething else",
            'program="7z"; version="p7zip Version 3.0"',
        ),
        (
            utils.COMPRESSION_7Z_COPY,
            "\n7-Zip 23.01 (x64)\n 64-bit locale=C.UTF-8\nsomething else",
            'program="7z"; version="7-Zip 23.01 (x64) 64-bit locale=C.UTF-8"',
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
    check_output, compression, cmd_output, expected_detail
):
    # subprocess.check_output returns bytes in python3
    check_output.return_value = cmd_output.encode("utf8")
    detail = utils.get_compression_event_detail(compression)

    assert detail == expected_detail, (
        f"Incorrect detail: {detail} returned for compression input {compression}"
    )


@pytest.mark.parametrize(
    "compression,version,extension,program_name,transform",
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
    assert re.search(version, vers) is not None
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


def _files_under(directory: pathlib.Path) -> dict[str, str]:
    return {
        path.relative_to(directory).as_posix(): path.read_text()
        for path in directory.rglob("*")
        if path.is_file()
    }


@pytest.fixture
def package_dir(tmp_path: pathlib.Path) -> pathlib.Path:
    """Return a small directory tree, like an AIP about to be encrypted."""
    directory = tmp_path / "package"
    (directory / "data" / "objects").mkdir(parents=True)
    (directory / "bagit.txt").write_text("BagIt-Version: 0.97\n")
    (directory / "data" / "objects" / "hello.txt").write_text("hello\n")
    return directory


def test_create_tar_replaces_a_directory_with_a_tarfile(
    package_dir: pathlib.Path,
) -> None:
    utils.create_tar(package_dir)

    assert package_dir.is_file()
    assert tarfile.is_tarfile(package_dir)
    assert not package_dir.with_name("package.tar").exists()
    with tarfile.open(package_dir) as tar:
        assert sorted(tar.getnames()) == [
            "package",
            "package/bagit.txt",
            "package/data",
            "package/data/objects",
            "package/data/objects/hello.txt",
        ]


def test_create_tar_keeps_the_extension_when_asked(package_dir: pathlib.Path) -> None:
    utils.create_tar(package_dir, extension=True)

    tarpath = package_dir.with_name("package.tar")
    assert tarfile.is_tarfile(tarpath)
    assert not package_dir.exists()


def test_create_tar_packages_a_file(tmp_path: pathlib.Path) -> None:
    archive = tmp_path / "package.7z"
    archive.write_bytes(b"compressed package")

    utils.create_tar(archive, extension=True)

    tarpath = tmp_path / "package.7z.tar"
    assert tarfile.is_tarfile(tarpath)
    assert not archive.exists()
    with tarfile.open(tarpath) as tar:
        assert tar.getnames() == ["package.7z"]


def test_create_tar_fails_when_the_path_does_not_exist(
    tmp_path: pathlib.Path,
) -> None:
    missing = tmp_path / "missing"

    with pytest.raises(
        utils.TARException,
        match=f"Failed to create a tarfile at {missing}.tar for dir at {missing}",
    ):
        utils.create_tar(missing)

    assert not missing.with_name("missing.tar").exists()


def test_create_tar_keeps_an_existing_tarfile_when_the_tool_fails(
    tmp_path: pathlib.Path,
) -> None:
    """Only what this call created may be removed on failure."""
    missing = tmp_path / "missing"
    existing = tmp_path / "missing.tar"
    existing.write_bytes(b"previous archive")

    with pytest.raises(utils.TARException):
        utils.create_tar(missing)

    assert existing.read_bytes() == b"previous archive"


@pytest.fixture
def fake_tar(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> Callable[[str], None]:
    """Return a function that puts a stand-in ``tar`` running a shell script first on the path."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")

    def install(script: str) -> None:
        tool = bin_dir / "tar"
        tool.write_text(f"#!/bin/sh\n{script}\n")
        tool.chmod(0o755)

    return install


def test_create_tar_fails_when_the_tool_writes_no_tarfile(
    package_dir: pathlib.Path, fake_tar: Callable[[str], None]
) -> None:
    """The source is kept unless the tarfile that replaces it is there."""
    before = _files_under(package_dir)
    fake_tar("exit 0")

    with pytest.raises(utils.TARException):
        utils.create_tar(package_dir)

    assert _files_under(package_dir) == before
    assert sorted(entry.name for entry in package_dir.parent.iterdir()) == [
        "bin",
        "package",
    ]


def test_create_tar_fails_when_the_tool_writes_an_invalid_tarfile(
    package_dir: pathlib.Path, fake_tar: Callable[[str], None]
) -> None:
    before = _files_under(package_dir)
    # The output path follows the -cf option: tar -C <dir> -cf <output> <source>.
    fake_tar('echo "not a tarfile" > "$4"')

    with pytest.raises(utils.TARException):
        utils.create_tar(package_dir)

    assert _files_under(package_dir) == before
    assert sorted(entry.name for entry in package_dir.parent.iterdir()) == [
        "bin",
        "package",
    ]


def test_create_tar_fails_when_the_parent_directory_is_not_writable(
    tmp_path: pathlib.Path,
) -> None:
    """Every failure to create the tarfile is reported the same way."""
    if os.geteuid() == 0:
        pytest.skip("permissions are not enforced for root")
    store = tmp_path / "store"
    package = store / "package"
    package.mkdir(parents=True)
    (package / "bagit.txt").write_text("BagIt-Version: 0.97\n")
    before = _files_under(package)
    store.chmod(0o555)

    try:
        with pytest.raises(utils.TARException):
            utils.create_tar(package)
    finally:
        store.chmod(0o755)

    assert _files_under(package) == before
    assert sorted(entry.name for entry in store.iterdir()) == ["package"]


def test_extract_tar_restores_the_directory(package_dir: pathlib.Path) -> None:
    expected = _files_under(package_dir)
    utils.create_tar(package_dir)

    utils.extract_tar(package_dir)

    assert package_dir.is_dir()
    assert _files_under(package_dir) == expected
    assert not package_dir.with_name("package.tar").exists()


def test_extract_tar_restores_a_file(tmp_path: pathlib.Path) -> None:
    archive = tmp_path / "package.7z"
    archive.write_bytes(b"compressed package")
    utils.create_tar(archive, extension=True)

    utils.extract_tar(tmp_path / "package.7z.tar")

    assert archive.read_bytes() == b"compressed package"
    assert not (tmp_path / "package.7z.tar").exists()


def test_extract_tar_fails_and_restores_the_name(tmp_path: pathlib.Path) -> None:
    broken = tmp_path / "broken"
    broken.write_bytes(b"not a tarfile")

    with pytest.raises(utils.TARException, match=f"Failed to extract {broken}: "):
        utils.extract_tar(broken)

    assert broken.read_bytes() == b"not a tarfile"
    assert not broken.with_name("broken.tar").exists()


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
@mock.patch("pathlib.Path.iterdir")
def test_find_tagmanifest(iterdir, tmp_path, dir_listing, tagmanifest_file):
    aip_path = tmp_path / "aip"
    aip_path.mkdir()
    mock_files = [aip_path / file_ for file_ in dir_listing]
    iterdir.return_value = mock_files

    if tagmanifest_file is None:
        assert utils.find_tagmanifest(aip_path) is None
    else:
        assert utils.find_tagmanifest(aip_path) == aip_path / tagmanifest_file

    file_path = aip_path / "file.txt"
    file_path.write_text("test data")
    assert utils.find_tagmanifest(file_path) is None


@mock.patch("archivematica.storage_service.common.utils.find_tagmanifest")
@mock.patch("pathlib.Path.is_dir", return_value=True)
def test_generate_checksum_uncompressed_aip(is_dir, find_tag_manifest, tmp_path):
    aip_path = tmp_path / "aip"
    aip_path.mkdir()
    tagmanifest = aip_path / "tagmanifest-md5.txt"
    tagmanifest.write_text("some test data")

    find_tag_manifest.return_value = tagmanifest

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
        str(FIXTURES_DIR / "premis_3_pointer.xml")
    ) == ("c2924159fcbbeadf8d7f3962b43ec1bf301e1b4f12dd28a8b89ec819f3714747", "sha256")


def test_get_mimetype():
    assert utils.get_mimetype("video.mp4") == "video/mp4"
    assert utils.get_mimetype("C:\\Windows\\Path\\windowsfile.xml") == "application/xml"
    assert utils.get_mimetype("/var/lib/file.txt") == "text/plain"
    assert utils.get_mimetype("undetermined") is None
