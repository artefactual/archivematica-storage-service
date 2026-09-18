from __future__ import annotations

import re
import shutil
import subprocess
import tarfile
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

import pytest

from archivematica.storage_service.common.compression import COMPRESSION_7Z_BZIP
from archivematica.storage_service.common.compression import COMPRESSION_7Z_COPY
from archivematica.storage_service.common.compression import COMPRESSION_7Z_LZMA
from archivematica.storage_service.common.compression import COMPRESSION_ALGORITHMS
from archivematica.storage_service.common.compression import COMPRESSION_TAR
from archivematica.storage_service.common.compression import COMPRESSION_TAR_BZIP2
from archivematica.storage_service.common.compression import COMPRESSION_TAR_GZIP
from archivematica.storage_service.common.compression import Archiver
from archivematica.storage_service.common.compression import CommandLineArchiver
from archivematica.storage_service.common.compression import CompressionError
from archivematica.storage_service.common.compression import archive_extension
from archivematica.storage_service.common.compression import (
    compression_for_premis_algorithm,
)
from archivematica.storage_service.common.compression import get_archiver
from archivematica.storage_service.common.compression import override_archiver

TOOLS = ("7z", "tar", "unar", "lsar")
MISSING_TOOLS = [tool for tool in TOOLS if shutil.which(tool) is None]
requires_tools = pytest.mark.skipif(
    bool(MISSING_TOOLS), reason=f"missing command line tools: {MISSING_TOOLS}"
)

PACKAGE_NAME = "package-2b7f4d6e-3c1a-4a2f-9f0e-0f8b7a6c5d4e"
PACKAGE_FILES = {
    "bagit.txt": "BagIt-Version: 0.97\n",
    "data/objects/hello.txt": "hello\n",
    "data/objects/nested/deep.txt": "deep\n",
}


@pytest.fixture
def package(tmp_path: Path) -> Path:
    """Return a small directory tree to archive."""
    root = tmp_path / "source" / PACKAGE_NAME
    for relative_path, content in PACKAGE_FILES.items():
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    return root


def files_under(directory: Path) -> dict[str, str]:
    return {
        path.relative_to(directory).as_posix(): path.read_text()
        for path in directory.rglob("*")
        if path.is_file()
    }


@pytest.fixture(params=["command_line", "fake"])
def archiver(request: pytest.FixtureRequest, fake_archiver: Archiver) -> Archiver:
    """Return each implementation in turn, so the fake obeys the same contract."""
    if request.param == "fake":
        return fake_archiver
    if MISSING_TOOLS:
        pytest.skip(f"missing command line tools: {MISSING_TOOLS}")
    return CommandLineArchiver()


def test_implementations_satisfy_the_protocol(archiver: Archiver) -> None:
    assert isinstance(archiver, Archiver)


@pytest.mark.parametrize("compression", COMPRESSION_ALGORITHMS)
def test_compress_names_the_archive_after_the_source(
    archiver: Archiver, package: Path, tmp_path: Path, compression: str
) -> None:
    archive = archiver.compress(package, tmp_path / "archives", compression)

    expected = tmp_path / "archives" / f"{PACKAGE_NAME}{archive_extension(compression)}"
    assert archive.path == expected
    assert archive.path.is_file()
    assert archive.event_detail.startswith("program=")


@pytest.mark.parametrize("compression", COMPRESSION_ALGORITHMS)
def test_extract_restores_the_source(
    archiver: Archiver, package: Path, tmp_path: Path, compression: str
) -> None:
    archive = archiver.compress(package, tmp_path / "archives", compression)

    extracted = archiver.extract(archive.path, tmp_path / "extracted", compression)

    assert extracted == tmp_path / "extracted" / PACKAGE_NAME
    assert files_under(extracted) == PACKAGE_FILES


@pytest.mark.parametrize("compression", COMPRESSION_ALGORITHMS)
def test_extract_returns_a_single_member(
    archiver: Archiver, package: Path, tmp_path: Path, compression: str
) -> None:
    archive = archiver.compress(package, tmp_path / "archives", compression)
    member = f"{PACKAGE_NAME}/data/objects/nested/deep.txt"

    extracted = archiver.extract(
        archive.path, tmp_path / "extracted", compression, member=member
    )

    assert extracted == tmp_path / "extracted" / member
    assert files_under(tmp_path / "extracted") == {member: "deep\n"}


@pytest.mark.parametrize(
    "compression", [COMPRESSION_TAR, COMPRESSION_7Z_BZIP], ids=["tar", "7z"]
)
@pytest.mark.parametrize(
    "member",
    [
        f"{PACKAGE_NAME}/data/objects/{'x' * 110}.txt",
        f"{PACKAGE_NAME}/data/objects/café.txt",
    ],
    ids=["long-name", "non-ascii-name"],
)
def test_extract_returns_a_member_named_in_a_pax_extended_header(
    archiver: Archiver, package: Path, tmp_path: Path, compression: str, member: str
) -> None:
    """PAX archives record such names in headers not every tool reads.

    A pointer file naming no known format sends the extraction to 7z
    whatever the archive is, so the tar archive is read with 7z as well.
    """
    (tmp_path / "source" / member).write_text("pax\n")
    archive = tmp_path / "archives" / f"{PACKAGE_NAME}.tar"
    archive.parent.mkdir()
    # The archiver writes the GNU format, so the archive is built directly.
    with tarfile.open(archive, "w", format=tarfile.PAX_FORMAT) as tar:
        tar.add(package, arcname=PACKAGE_NAME)

    extracted = archiver.extract(
        archive, tmp_path / "extracted", compression, member=member
    )

    assert extracted == tmp_path / "extracted" / member
    assert files_under(tmp_path / "extracted") == {member: "pax\n"}


@pytest.mark.parametrize("compression", COMPRESSION_ALGORITHMS)
@pytest.mark.parametrize(
    "name", ["line\u2028break.txt", "line\nbreak.txt"], ids=["separator", "newline"]
)
def test_extract_returns_a_member_named_with_a_line_break(
    archiver: Archiver, package: Path, tmp_path: Path, compression: str, name: str
) -> None:
    """The tools print such names differently from how they match them."""
    member = f"{PACKAGE_NAME}/data/objects/{name}"
    (tmp_path / "source" / member).write_text("break\n")
    archive = archiver.compress(package, tmp_path / "archives", compression)

    extracted = archiver.extract(
        archive.path, tmp_path / "extracted", compression, member=member
    )

    assert extracted == tmp_path / "extracted" / member
    assert files_under(tmp_path / "extracted") == {member: "break\n"}


@pytest.mark.parametrize("compression", COMPRESSION_ALGORITHMS)
def test_extract_fails_for_a_missing_member(
    archiver: Archiver, package: Path, tmp_path: Path, compression: str
) -> None:
    archive = archiver.compress(package, tmp_path / "archives", compression)

    # The tools disagree on how to report this: tar exits with an error,
    # 7z and unar exit successfully having extracted nothing.
    with pytest.raises(CompressionError):
        archiver.extract(
            archive.path,
            tmp_path / "extracted",
            compression,
            member=f"{PACKAGE_NAME}/missing.txt",
        )


@pytest.mark.parametrize("compression", COMPRESSION_ALGORITHMS)
def test_extract_returns_a_directory_member(
    archiver: Archiver, package: Path, tmp_path: Path, compression: str
) -> None:
    archive = archiver.compress(package, tmp_path / "archives", compression)
    member = f"{PACKAGE_NAME}/data/objects/nested/"

    extracted = archiver.extract(
        archive.path, tmp_path / "extracted", compression, member=member
    )

    assert extracted == tmp_path / "extracted" / PACKAGE_NAME / "data/objects/nested"
    assert files_under(tmp_path / "extracted") == {
        f"{PACKAGE_NAME}/data/objects/nested/deep.txt": "deep\n"
    }


@requires_tools
def test_command_line_extract_fails_for_a_directory_member_without_a_compression(
    package: Path, tmp_path: Path
) -> None:
    """Format detection runs unar, which does not extract directory members."""
    archive = CommandLineArchiver().compress(
        package, tmp_path / "archives", COMPRESSION_7Z_BZIP
    )

    with pytest.raises(CompressionError, match="was not extracted"):
        CommandLineArchiver().extract(
            archive.path, tmp_path / "extracted", None, member=f"{PACKAGE_NAME}/data/"
        )


@pytest.mark.parametrize("compression", [*COMPRESSION_ALGORITHMS, None])
def test_extract_fails_for_a_missing_member_in_a_reused_destination(
    archiver: Archiver, package: Path, tmp_path: Path, compression: str | None
) -> None:
    """A file already at the member's path must not pass for the extraction."""
    archive = archiver.compress(
        package, tmp_path / "archives", compression or COMPRESSION_7Z_BZIP
    )
    destination = tmp_path / "extracted"
    stale = destination / PACKAGE_NAME / "missing.txt"
    stale.parent.mkdir(parents=True)
    stale.write_text("stale")

    with pytest.raises(CompressionError):
        archiver.extract(
            archive.path, destination, compression, member=f"{PACKAGE_NAME}/missing.txt"
        )

    assert stale.read_text() == "stale"


def test_extract_detects_the_format_without_a_compression(
    archiver: Archiver, package: Path, tmp_path: Path
) -> None:
    archive = archiver.compress(package, tmp_path / "archives", COMPRESSION_TAR_GZIP)

    extracted = archiver.extract(archive.path, tmp_path / "extracted")

    assert files_under(extracted) == PACKAGE_FILES


@pytest.mark.parametrize("compression", COMPRESSION_ALGORITHMS)
def test_root_directory_is_the_source_name(
    archiver: Archiver, package: Path, tmp_path: Path, compression: str
) -> None:
    archive = archiver.compress(package, tmp_path / "archives", compression)

    assert archiver.root_directory(archive.path) == PACKAGE_NAME


@pytest.mark.parametrize("compression", [COMPRESSION_7Z_BZIP, COMPRESSION_TAR_GZIP])
def test_compress_names_an_archive_of_a_file_without_its_extension(
    archiver: Archiver, package: Path, tmp_path: Path, compression: str
) -> None:
    first = archiver.compress(package, tmp_path / "archives", compression)

    second = archiver.compress(first.path, tmp_path / "repackaged", COMPRESSION_TAR)

    assert second.path == tmp_path / "repackaged" / f"{PACKAGE_NAME}.tar"
    assert second.path.is_file()
    with pytest.raises(CompressionError, match="does not contain a directory"):
        archiver.root_directory(second.path)


def test_compress_rejects_an_unsupported_algorithm(
    archiver: Archiver, package: Path, tmp_path: Path
) -> None:
    with pytest.raises(ValueError, match="Unsupported compression: zip"):
        archiver.compress(package, tmp_path / "archives", "zip")


@pytest.mark.parametrize(
    ("algorithm", "compression"),
    [
        ("bzip2", COMPRESSION_7Z_BZIP),
        ("lzma", COMPRESSION_7Z_LZMA),
        ("copy", COMPRESSION_7Z_COPY),
        ("pbzip2", COMPRESSION_TAR_BZIP2),
        ("tar.gzip", COMPRESSION_TAR_GZIP),
    ],
)
def test_compression_for_premis_algorithm_reads_the_names_the_pipeline_sends(
    algorithm: str, compression: str
) -> None:
    assert compression_for_premis_algorithm(algorithm) == compression


def test_compression_for_premis_algorithm_rejects_an_unknown_name() -> None:
    with pytest.raises(ValueError, match="Unknown compression algorithm: zip"):
        compression_for_premis_algorithm("zip")


@pytest.mark.parametrize(
    "compression", [COMPRESSION_7Z_BZIP, COMPRESSION_7Z_LZMA, COMPRESSION_7Z_COPY]
)
def test_compression_for_premis_algorithm_reads_back_the_7z_names_written(
    package: Path, tmp_path: Path, compression: str
) -> None:
    """The 7z names this module writes in its own compression events read back
    to the compression they were made with.
    """

    def run(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        if command[:2] == ["7z", "a"]:
            Path(command[-2]).write_bytes(b"archive")
        return completed(command)

    archive = CommandLineArchiver(run=run).compress(package, tmp_path, compression)

    assert compression_for_premis_algorithm(archive.algorithm) == compression


# The command line implementation, with the real tools.


@requires_tools
@pytest.mark.parametrize(
    ("compression", "expected"),
    [
        (COMPRESSION_7Z_BZIP, "program=7z; algorithm=bzip2; version="),
        (COMPRESSION_7Z_LZMA, "program=7z; algorithm=lzma; version="),
        (COMPRESSION_7Z_COPY, "program=7z; algorithm=copy; version="),
        (COMPRESSION_TAR, "program=tar; algorithm=; version=tar"),
        (COMPRESSION_TAR_BZIP2, "program=tar; algorithm=-j; version=tar"),
        (COMPRESSION_TAR_GZIP, "program=tar; algorithm=-z; version=tar"),
    ],
)
def test_command_line_event_detail_reports_the_tool_and_its_version(
    package: Path, tmp_path: Path, compression: str, expected: str
) -> None:
    archive = CommandLineArchiver().compress(
        package, tmp_path / "archives", compression
    )

    assert archive.event_detail.startswith(expected)
    assert archive.version


@requires_tools
@pytest.mark.parametrize(
    ("compression", "tar_mode", "sevenzip_method"),
    [
        (COMPRESSION_7Z_BZIP, None, "BZip2"),
        (COMPRESSION_7Z_LZMA, None, "LZMA"),
        (COMPRESSION_7Z_COPY, None, "Copy"),
        (COMPRESSION_TAR, "r:", None),
        (COMPRESSION_TAR_BZIP2, "r:bz2", None),
        (COMPRESSION_TAR_GZIP, "r:gz", None),
    ],
)
def test_command_line_compress_writes_the_format_of_the_algorithm(
    package: Path,
    tmp_path: Path,
    compression: str,
    tar_mode: Literal["r:", "r:bz2", "r:gz"] | None,
    sevenzip_method: str | None,
) -> None:
    """The archive is read back by other means than the archiver's own table."""
    archive = CommandLineArchiver().compress(
        package, tmp_path / "archives", compression
    )

    if tar_mode is not None:
        with tarfile.open(archive.path, tar_mode) as tar:
            assert f"{PACKAGE_NAME}/bagit.txt" in tar.getnames()
    else:
        listing = subprocess.run(
            ["7z", "l", "-slt", str(archive.path)],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        assert re.search(rf"^Method = {sevenzip_method}", listing, re.MULTILINE)


# The command line implementation, with a stand-in for the tools.


def completed(
    command: Sequence[str], returncode: int = 0, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(list(command), returncode, stdout, stderr)


def touch_output(command: Sequence[str]) -> Path:
    """Create the archive a tar command would write, as a stand-in tool."""
    output = Path(command[command.index("-f") + 1])
    output.write_bytes(b"archive")
    return output


def test_command_line_compress_fails_when_the_tool_fails(
    package: Path, tmp_path: Path
) -> None:
    def run(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        return completed(command, returncode=1, stderr="No space left on device")

    with pytest.raises(
        CompressionError, match="7z exited with status 1: No space left on device"
    ):
        CommandLineArchiver(run=run).compress(package, tmp_path, COMPRESSION_7Z_BZIP)


def test_command_line_compress_removes_a_partial_archive_when_the_tool_fails(
    package: Path, tmp_path: Path
) -> None:
    def run(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        touch_output(command)
        return completed(command, returncode=2, stderr="Cannot stat: No such file")

    with pytest.raises(CompressionError, match="tar exited with status 2"):
        CommandLineArchiver(run=run).compress(package, tmp_path, COMPRESSION_TAR)

    assert [entry.name for entry in tmp_path.iterdir()] == ["source"]


def test_command_line_compress_keeps_an_existing_archive_when_the_tool_fails(
    package: Path, tmp_path: Path
) -> None:
    """Only what this call created may be removed on failure."""
    archive = tmp_path / f"{PACKAGE_NAME}.tar"
    archive.write_bytes(b"previous archive")

    def run(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        return completed(command, returncode=2, stderr="Cannot open: Permission denied")

    with pytest.raises(CompressionError, match="tar exited with status 2"):
        CommandLineArchiver(run=run).compress(package, tmp_path, COMPRESSION_TAR)

    assert archive.read_bytes() == b"previous archive"


def test_command_line_compress_keeps_an_existing_archive_when_the_tool_is_missing(
    package: Path, tmp_path: Path
) -> None:
    archive = tmp_path / f"{PACKAGE_NAME}.tar"
    archive.write_bytes(b"previous archive")

    def run(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError(2, "No such file or directory", command[0])

    with pytest.raises(CompressionError, match="Could not run tar"):
        CommandLineArchiver(run=run).compress(package, tmp_path, COMPRESSION_TAR)

    assert archive.read_bytes() == b"previous archive"


@requires_tools
def test_command_line_compress_replaces_a_read_only_archive(
    package: Path, tmp_path: Path
) -> None:
    """The archive is written aside and published, so the tool never opens the old one."""
    archive = tmp_path / f"{PACKAGE_NAME}.tar"
    archive.write_bytes(b"previous archive")
    archive.chmod(0o444)

    result = CommandLineArchiver().compress(package, tmp_path, COMPRESSION_TAR)

    assert result.path == archive
    assert (
        files_under(
            CommandLineArchiver().extract(archive, tmp_path / "check", COMPRESSION_TAR)
        )
        == PACKAGE_FILES
    )
    assert [
        entry.name for entry in tmp_path.iterdir() if entry.name.startswith(".")
    ] == []


def test_command_line_compress_runs_7z_with_the_flags_that_keep_the_timestamps(
    package: Path, tmp_path: Path
) -> None:
    """The command line is what PREMIS events describe, so it is pinned."""
    commands: list[list[str]] = []

    def run(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        commands.append(list(command))
        if command[:2] == ["7z", "a"]:
            Path(command[-2]).write_bytes(b"archive")
        return completed(command)

    CommandLineArchiver(run=run).compress(package, tmp_path, COMPRESSION_7Z_BZIP)

    (command,) = [command for command in commands if command[:2] == ["7z", "a"]]
    assert command[:10] == [
        "7z",
        "a",
        "-bd",
        "-t7z",
        "-y",
        "-m0=bzip2",
        "-mtc=on",
        "-mtm=on",
        "-mta=on",
        "-mmt=on",
    ]
    output, source = command[10:]
    assert Path(output).name == f"{PACKAGE_NAME}.7z"
    assert Path(output).parent.parent == tmp_path
    assert source == str(package)


def test_command_line_compress_fails_on_a_tool_warning(
    package: Path, tmp_path: Path
) -> None:
    """7z exits with status 1 when a file was left out: no archive is published."""

    def run(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        if command[:2] == ["7z", "a"]:
            Path(command[-2]).write_bytes(b"archive without a file")
            return completed(command, returncode=1, stderr="WARNING: Cannot open")
        return completed(command)

    with pytest.raises(CompressionError, match="7z exited with status 1"):
        CommandLineArchiver(run=run).compress(package, tmp_path, COMPRESSION_7Z_BZIP)

    assert [entry.name for entry in tmp_path.iterdir()] == ["source"]


def test_command_line_compress_fails_when_the_tool_is_missing(
    package: Path, tmp_path: Path
) -> None:
    def run(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError(2, "No such file or directory", command[0])

    with pytest.raises(CompressionError, match="Could not run tar"):
        CommandLineArchiver(run=run).compress(package, tmp_path, COMPRESSION_TAR)


def test_command_line_version_is_empty_when_the_probe_fails(
    package: Path, tmp_path: Path
) -> None:
    def run(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        if command == ["tar", "--version"]:
            return completed(command, returncode=1)
        touch_output(command)
        return completed(command)

    archive = CommandLineArchiver(run=run).compress(package, tmp_path, COMPRESSION_TAR)

    assert archive.version == ""
    assert archive.event_detail == "program=tar; algorithm=; version="


def test_command_line_logs_the_commands_it_runs(
    package: Path, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Operators rely on the exact command lines appearing in the logs."""
    listing = '{"lsarContents": [{"XADFileName": "pkg", "XADIsDirectory": 1}]}'
    commands: list[list[str]] = []

    def run(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        commands.append(list(command))
        if command[:2] == ["tar", "c"]:
            touch_output(command)
        return completed(command, stdout=listing)

    archiver = CommandLineArchiver(run=run)
    (tmp_path / "pkg").mkdir()
    with caplog.at_level(
        "INFO", logger="archivematica.storage_service.common.compression"
    ):
        archiver.compress(package, tmp_path, COMPRESSION_TAR)
        archiver.extract(tmp_path / "pkg.tar", tmp_path, COMPRESSION_TAR)

    # The archive is written aside and published, so the command names a
    # temporary path inside the destination directory.
    compress_command = commands[0]
    assert compress_command[:5] == ["tar", "c", "-C", str(package.parent), "-f"]
    assert Path(compress_command[5]).parent.parent == tmp_path
    assert compress_command[6:] == [PACKAGE_NAME]
    assert caplog.messages == [
        f"Compressing package with: {compress_command} to {tmp_path / PACKAGE_NAME}.tar",
        f"Extracting file with: ['tar', 'x', '-f', '{tmp_path / 'pkg.tar'}', "
        f"'-C', '{tmp_path}'] to {tmp_path / 'pkg'}",
    ]


def test_command_line_root_directory_fails_without_directories(tmp_path: Path) -> None:
    listing = '{"lsarContents": [{"XADFileName": "file.txt"}]}'

    def run(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        return completed(command, stdout=listing)

    with pytest.raises(CompressionError, match="does not contain a directory"):
        CommandLineArchiver(run=run).root_directory(tmp_path / "package.7z")


def test_command_line_root_directory_fails_on_an_unreadable_listing(
    tmp_path: Path,
) -> None:
    def run(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        return completed(command, stdout="not json")

    with pytest.raises(CompressionError, match="Could not list"):
        CommandLineArchiver(run=run).root_directory(tmp_path / "package.7z")


# Selecting the archiver in use.


def test_the_default_archiver_uses_the_command_line_tools() -> None:
    assert isinstance(get_archiver(), CommandLineArchiver)


def test_override_archiver_is_scoped(fake_archiver: Archiver) -> None:
    assert get_archiver() is fake_archiver

    with override_archiver(type(fake_archiver)()) as inner:
        assert get_archiver() is inner

    assert get_archiver() is fake_archiver
