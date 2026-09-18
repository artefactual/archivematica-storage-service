"""Compression and extraction of packages.

The Storage Service stores packages either as directories or as archives.
This module owns the creation and reading of those archives behind the
:class:`Archiver` protocol, so that the rest of the service never deals with
compression tools directly, and so that tests can substitute a stand-in
through :func:`override_archiver`.
"""

from __future__ import annotations

import contextlib
import json
import logging
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from collections.abc import Iterator
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from typing import runtime_checkable

LOGGER = logging.getLogger(__name__)

# Identifiers of the supported algorithms. The values match the ones used
# throughout the service, in pointer file parsing and in the API.
COMPRESSION_7Z_BZIP = "7z with bzip"
COMPRESSION_7Z_LZMA = "7z with lzma"
COMPRESSION_7Z_COPY = "7z without compression"
COMPRESSION_TAR = "tar"
COMPRESSION_TAR_BZIP2 = "tar bz2"
COMPRESSION_TAR_GZIP = "tar gz"
COMPRESSION_ALGORITHMS: tuple[str, ...] = (
    COMPRESSION_7Z_BZIP,
    COMPRESSION_7Z_LZMA,
    COMPRESSION_7Z_COPY,
    COMPRESSION_TAR,
    COMPRESSION_TAR_BZIP2,
    COMPRESSION_TAR_GZIP,
)


class CompressionError(Exception):
    """A compression tool failed or produced an unexpected result."""


@dataclass(frozen=True)
class _Format:
    """How a compression maps to a command line tool.

    ``premis_event_detail_algorithm`` is the ``algorithm`` value of the PREMIS
    compression event detail, kept as existing pointer files record it.
    """

    program: str
    extension: str
    options: tuple[str, ...]
    premis_event_detail_algorithm: str


_FORMATS: dict[str, _Format] = {
    COMPRESSION_7Z_BZIP: _Format("7z", ".7z", ("-m0=bzip2",), "bzip2"),
    COMPRESSION_7Z_LZMA: _Format("7z", ".7z", ("-m0=lzma",), "lzma"),
    COMPRESSION_7Z_COPY: _Format("7z", ".7z", ("-m0=copy",), "copy"),
    COMPRESSION_TAR: _Format("tar", ".tar", (), ""),
    COMPRESSION_TAR_BZIP2: _Format("tar", ".tar.bz2", ("-j",), "-j"),
    COMPRESSION_TAR_GZIP: _Format("tar", ".tar.gz", ("-z",), "-z"),
}


def _format(compression: str) -> _Format:
    if compression not in _FORMATS:
        raise ValueError(f"Unsupported compression: {compression}")
    return _FORMATS[compression]


def archive_extension(compression: str) -> str:
    """Return the file extension of archives made with ``compression``."""
    return _format(compression).extension


def archive_name(source: Path) -> str:
    """Return the name, without extension, of an archive made from ``source``.

    A directory keeps its name. A file, such as an archive being repackaged,
    loses its archive extension, or its last suffix if the extension is not
    a known one.
    """
    if not source.is_file():
        return source.name
    for extension in sorted({f.extension for f in _FORMATS.values()}, key=len):
        if source.name.endswith(extension):
            return source.name[: -len(extension)]
    return source.stem


_COMPRESSION_BY_PREMIS_ALGORITHM: dict[str, str] = {
    "bzip2": COMPRESSION_7Z_BZIP,
    "lzma": COMPRESSION_7Z_LZMA,
    "copy": COMPRESSION_7Z_COPY,
    "pbzip2": COMPRESSION_TAR_BZIP2,
    "tar.gzip": COMPRESSION_TAR_GZIP,
}


def compression_for_premis_algorithm(algorithm: str) -> str:
    """Return the compression that ``algorithm`` stands for, as named in a
    PREMIS compression event of the pipeline.

    Raises ``ValueError`` for an unknown name.
    """
    if algorithm not in _COMPRESSION_BY_PREMIS_ALGORITHM:
        raise ValueError(f"Unknown compression algorithm: {algorithm}")
    return _COMPRESSION_BY_PREMIS_ALGORITHM[algorithm]


@dataclass(frozen=True)
class Archive:
    """An archive created by :meth:`Archiver.compress`."""

    path: Path
    program: str
    version: str
    algorithm: str
    stdout: str
    stderr: str

    @property
    def event_detail(self) -> str:
        """Return the description of the tool for PREMIS compression events."""
        return f"program={self.program}; algorithm={self.algorithm}; version={self.version}"


@runtime_checkable
class Archiver(Protocol):
    """Creates and reads package archives."""

    def compress(
        self, source: Path, destination_dir: Path, compression: str
    ) -> Archive:
        """Archive ``source``, a directory or a file, into ``destination_dir``.

        The archive is named after ``source`` with the extension of
        ``compression`` and contains ``source`` at its root. Raises
        ``ValueError`` for an unsupported ``compression`` and
        :class:`CompressionError` when the archive cannot be created.
        """
        ...

    def extract(
        self,
        archive: Path,
        destination_dir: Path,
        compression: str | None = None,
        member: str | None = None,
    ) -> Path:
        """Extract ``archive``, or only ``member``, into ``destination_dir``.

        ``compression`` selects the tool; without it the format is detected.
        Returns the path of the extracted root directory, or of ``member``.
        Raises :class:`CompressionError` when ``member`` is not in the
        archive or nothing was extracted.
        """
        ...

    def root_directory(self, archive: Path) -> str:
        """Return the name of the directory at the root of ``archive``.

        Raises :class:`CompressionError` if the archive holds no directory.
        """
        ...


CommandRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


def run_command(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    """Run ``command`` capturing its output, without raising on failure."""
    return subprocess.run(list(command), capture_output=True, text=True, check=False)


class CommandLineArchiver:
    """Archiver that runs the archive tools as command lines.

    ``run`` executes the commands; tests inject a stand-in to simulate
    failures without the tools.
    """

    def __init__(self, run: CommandRunner = run_command) -> None:
        self._run = run

    def compress(
        self, source: Path, destination_dir: Path, compression: str
    ) -> Archive:
        fmt = _format(compression)
        destination_dir.mkdir(parents=True, exist_ok=True)
        path = destination_dir / f"{archive_name(source)}{fmt.extension}"
        source = source.absolute()
        # The archive is written in a directory of its own and published once
        # complete, so a failure never touches an archive already at ``path``.
        staging = Path(tempfile.mkdtemp(prefix=".compress-", dir=destination_dir))
        output = staging / path.name
        if fmt.program == "7z":
            command = [
                "7z",
                "a",
                "-bd",  # Disable the progress indicator.
                "-t7z",
                "-y",
                *fmt.options,
                "-mtc=on",  # Keep the creation, modification and access times.
                "-mtm=on",
                "-mta=on",
                "-mmt=on",  # Use several threads.
                str(output),
                str(source),
            ]
        else:
            command = [
                "tar",
                "c",
                *fmt.options,
                "-C",
                str(source.parent),
                "-f",
                str(output),
                source.name,
            ]
        LOGGER.info("Compressing package with: %s to %s", command, path)
        try:
            result = self._checked(command)
            try:
                output.replace(path)
            except OSError as err:
                raise CompressionError(f"Could not write {path}: {err}") from err
        finally:
            # Whatever the tool left behind, complete or not, is ours.
            shutil.rmtree(staging, ignore_errors=True)
        LOGGER.debug("Compress package RC: %s", result.returncode)
        return Archive(
            path=path,
            program=fmt.program,
            version=self._version(fmt.program),
            algorithm=fmt.premis_event_detail_algorithm,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    def extract(
        self,
        archive: Path,
        destination_dir: Path,
        compression: str | None = None,
        member: str | None = None,
    ) -> Path:
        destination_dir.mkdir(parents=True, exist_ok=True)
        if compression is None:
            command = ["unar", "-force-overwrite", "-o", str(destination_dir)]
            command.append(str(archive))
        elif _format(compression).program == "7z":
            command = ["7z", "x", "-bd", "-y", f"-o{destination_dir}", str(archive)]
        else:
            command = [
                "tar",
                "x",
                *_format(compression).options,
                "-f",
                str(archive),
                "-C",
                str(destination_dir),
            ]
        if member is not None:
            # 7z and unar succeed without extracting anything for a member that
            # is not in the archive, and the destination may hold older files,
            # so the archive is listed first, by the tool that extracts it.
            # tar fails by itself when a member is missing.
            program = command[0]
            if program != "tar" and not self._contains(archive, member, program):
                raise CompressionError(f"{member} is not in {archive}")
            command.append(member)
        extracted = destination_dir / (member or self.root_directory(archive))
        LOGGER.info("Extracting file with: %s to %s", command, extracted)
        result = self._checked(command)
        LOGGER.debug("Extract file RC: %s", result.returncode)
        # 7z and unar do not fail when a member is missing, so check the result.
        if not extracted.exists():
            what = member or "the root directory"
            raise CompressionError(f"{what} was not extracted from {archive}")
        return extracted

    def root_directory(self, archive: Path) -> str:
        directories = [
            name for name, is_directory in self._entries(archive) if is_directory
        ]
        if not directories:
            raise CompressionError(f"{archive} does not contain a directory")
        # The root is the shortest directory name, e.g. "foo" before "foo/bar".
        return min(directories, key=len)

    def _contains(self, archive: Path, member: str, program: str) -> bool:
        """Return whether ``member``, a file or a directory, is in ``archive``.

        ``program``, ``7z`` or ``unar``, is the tool that will extract it and
        answers: lsar, which unar shares its reading with, does not see the
        names in the extended headers of PAX archives, and 7z does.
        """
        if program == "7z":
            # 7z lists what it would extract for ``member``, which spares
            # comparing names it cannot print, such as ones with line breaks.
            command = ["7z", "l", "-ba", "-slt", str(archive), member]
            listing = self._checked(command).stdout
            return any(line.startswith("Path = ") for line in listing.split("\n"))
        wanted = member.rstrip("/")
        return any(
            name == wanted or name.startswith(f"{wanted}/")
            for name, _is_directory in self._entries(archive)
        )

    def _entries(self, archive: Path) -> list[tuple[str, bool]]:
        """Return the names of the entries of ``archive`` and whether they are directories."""
        listing = self._checked(["lsar", "-ja", str(archive)]).stdout
        try:
            entries = json.loads(listing)["lsarContents"]
            return [
                (str(entry["XADFileName"]), bool(entry.get("XADIsDirectory")))
                for entry in entries
            ]
        except (ValueError, KeyError, TypeError) as err:
            raise CompressionError(f"Could not list {archive}: {err}") from err

    def _checked(self, command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        """Run ``command`` and fail on any non-zero status.

        The warning statuses of the tools count as failures: 7z exits with
        status 1 when a file could not be archived, and an archive missing a
        file is not a package to store.
        """
        try:
            result = self._run(command)
        except OSError as err:
            raise CompressionError(f"Could not run {command[0]}: {err}") from err
        if result.returncode != 0:
            raise CompressionError(
                f"{command[0]} exited with status {result.returncode}: "
                f"{result.stderr.strip()}"
            )
        return result

    def _version(self, program: str) -> str:
        """Return the version banner of ``program``, or an empty string."""
        try:
            if program == "7z":
                lines = self._checked(["7z"]).stdout.splitlines()
                if lines[2].startswith("p7zip Version"):
                    # p7zip 16.02 prints the version on its own line.
                    return lines[2]
                # 7-Zip 23.01 prints the copyright and architecture lines.
                return "".join(lines[1:3])
            return self._checked(["tar", "--version"]).stdout.splitlines()[0]
        except (CompressionError, IndexError) as err:
            LOGGER.debug("Could not determine the version of %s: %s", program, err)
            return ""


_archiver: Archiver = CommandLineArchiver()


def get_archiver() -> Archiver:
    """Return the archiver in use."""
    return _archiver


@contextlib.contextmanager
def override_archiver(archiver: Archiver) -> Iterator[Archiver]:
    """Use ``archiver`` within the context, then restore the previous one."""
    global _archiver
    previous = _archiver
    _archiver = archiver
    try:
        yield archiver
    finally:
        _archiver = previous
