"""Fixtures shared by the whole test suite."""

from __future__ import annotations

import tarfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from archivematica.storage_service.common.compression import Archive
from archivematica.storage_service.common.compression import CompressionError
from archivematica.storage_service.common.compression import archive_extension
from archivematica.storage_service.common.compression import archive_name
from archivematica.storage_service.common.compression import override_archiver


def _extract(tar: tarfile.TarFile, path: Path, members: list[tarfile.TarInfo]) -> None:
    if hasattr(tarfile, "data_filter"):
        tar.extractall(path, members, filter="data")
    else:  # Python < 3.12 without the security backport.
        tar.extractall(path, members)


class FakeArchiver:
    """Archiver stand-in that writes plain tar files with Python's tarfile.

    It honours the names and extensions of the requested algorithm but never
    compresses, so tests of the code above the archiver run without the
    command line tools.
    """

    def compress(
        self, source: Path, destination_dir: Path, compression: str
    ) -> Archive:
        destination_dir.mkdir(parents=True, exist_ok=True)
        path = (
            destination_dir / f"{archive_name(source)}{archive_extension(compression)}"
        )
        with tarfile.open(path, "w") as tar:
            tar.add(source, arcname=source.name)
        return Archive(
            path=path,
            program="fake",
            version="",
            algorithm=compression,
            stdout="",
            stderr="",
        )

    def extract(
        self,
        archive: Path,
        destination_dir: Path,
        compression: str | None = None,
        member: str | None = None,
    ) -> Path:
        destination_dir.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive) as tar:
            if member is None:
                _extract(tar, destination_dir, tar.getmembers())
                return destination_dir / self.root_directory(archive)
            wanted = member.rstrip("/")
            infos = [
                info
                for info in tar.getmembers()
                if info.name == wanted or info.name.startswith(f"{wanted}/")
            ]
            if not infos:
                raise CompressionError(f"{member} was not extracted from {archive}")
            _extract(tar, destination_dir, infos)
        return destination_dir / member

    def root_directory(self, archive: Path) -> str:
        with tarfile.open(archive) as tar:
            directories = [info.name for info in tar.getmembers() if info.isdir()]
        if not directories:
            raise CompressionError(f"{archive} does not contain a directory")
        return min(directories, key=len)


@pytest.fixture
def fake_archiver() -> Iterator[FakeArchiver]:
    """Make a fake archiver the one in use for the test and return it."""
    archiver = FakeArchiver()
    with override_archiver(archiver):
        yield archiver
