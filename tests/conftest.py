"""Fixtures shared by the whole test suite."""

from __future__ import annotations

import base64
import tarfile
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from django.contrib.auth.models import User
from django.test import Client
from tastypie.models import ApiKey

from archivematica.storage_service.common.compression import Archive
from archivematica.storage_service.common.compression import CompressionError
from archivematica.storage_service.common.compression import archive_extension
from archivematica.storage_service.common.compression import archive_name
from archivematica.storage_service.common.compression import override_archiver
from archivematica.storage_service.locations import models
from tests.factories import EventFactory
from tests.factories import LocationFactory
from tests.factories import PackageFactory
from tests.factories import PipelineFactory
from tests.factories import SpaceFactory


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


# The following fixtures create the users and the clients that act as them.


@pytest.fixture
def user(django_user_model: type[User]) -> User:
    """A user without a role, who can only read."""
    return django_user_model.objects.create_user(
        username="demo", email="demo@example.com", password="Abc.Def.1234"
    )


@pytest.fixture
def logged_in_client(user: User) -> Client:
    """A test client of its own, logged in as the user."""
    client = Client()
    client.force_login(user)

    return client


@pytest.fixture
def api_user(django_user_model: type[User]) -> User:
    """The superuser of the API tests, whose password is "test"."""
    result = django_user_model.objects.create_user(
        username="test",
        password="test",
        email="test@test.com",
        is_superuser=True,
        is_staff=True,
    )
    ApiKey.objects.create(user=result, key="test")

    return result


@pytest.fixture
def nonadmin_user(django_user_model: type[User]) -> User:
    """A staff user without a role, whose password is "test"."""
    result = django_user_model.objects.create_user(
        username="nonadmin", password="test", email="test2@test.com", is_staff=True
    )
    ApiKey.objects.create(user=result, key="test")

    return result


def _basic_auth_header(username: str, password: str) -> str:
    credentials = f"{username}:{password}".encode()

    return "Basic " + base64.b64encode(credentials).decode("utf8")


@pytest.fixture
def api_client(api_user: User) -> Client:
    """A test client of its own, authenticated as the superuser through HTTP
    Basic.
    """
    client = Client()
    client.defaults["HTTP_AUTHORIZATION"] = _basic_auth_header(
        api_user.username, "test"
    )

    return client


@pytest.fixture
def nonadmin_api_client(nonadmin_user: User) -> Client:
    """A test client of its own, authenticated as the staff user without a role
    through HTTP Basic.
    """
    client = Client()
    client.defaults["HTTP_AUTHORIZATION"] = _basic_auth_header(
        nonadmin_user.username, "test"
    )

    return client


# The following fixtures provide the factories of the rows the tests create.


@pytest.fixture
def make_space(db: None) -> SpaceFactory:
    return SpaceFactory()


@pytest.fixture
def make_location(db: None) -> LocationFactory:
    return LocationFactory()


@pytest.fixture
def make_pipeline(db: None) -> PipelineFactory:
    return PipelineFactory()


@pytest.fixture
def make_package(db: None) -> PackageFactory:
    return PackageFactory()


@pytest.fixture
def make_event(db: None) -> EventFactory:
    return EventFactory()


# The following fixtures create the spaces, locations, pipelines and packages.


@pytest.fixture
def space(make_space: SpaceFactory, tmp_path: Path) -> models.Space:
    """A local filesystem space in the temporary directory, staging in its
    internal location as a default installation does.
    """
    space_dir = tmp_path / "space"
    staging_dir = space_dir / "internal"
    staging_dir.mkdir(parents=True)

    return make_space(path=str(space_dir), staging_path=str(staging_dir))


@pytest.fixture
def aip_storage_location(
    make_location: LocationFactory, space: models.Space
) -> models.Location:
    """The AIP storage location of the space, created on disk."""
    result = make_location(space, models.Location.AIP_STORAGE, relative_path="aips")
    Path(result.full_path).mkdir()

    return result


@pytest.fixture
def ss_internal_location(
    make_location: LocationFactory, space: models.Space
) -> models.Location:
    """The internal location of the Storage Service, the staging directory of
    the space.
    """
    return make_location(
        space, models.Location.STORAGE_SERVICE_INTERNAL, relative_path="internal"
    )


@pytest.fixture
def pipeline(make_pipeline: PipelineFactory) -> models.Pipeline:
    return make_pipeline(description="Pipeline")


@pytest.fixture
def package(
    make_package: PackageFactory, aip_storage_location: models.Location
) -> models.Package:
    """A compressed AIP stored in the AIP storage location."""
    return make_package(aip_storage_location, "working_bag.zip")


@pytest.fixture
def compressed_package(
    make_package: PackageFactory, aip_storage_location: models.Location
) -> models.Package:
    """A compressed AIP named after its UUID, as the pipeline stores them,
    whose archive exists, empty, in the location.
    """
    package_uuid = uuid.uuid4()
    result = make_package(
        aip_storage_location, f"compressedaip-{package_uuid}.7z", uuid=package_uuid
    )
    (Path(aip_storage_location.full_path) / result.current_path).touch()
    assert result.is_compressed

    return result


@pytest.fixture
def uncompressed_package(
    make_package: PackageFactory, aip_storage_location: models.Location
) -> models.Package:
    """An uncompressed AIP whose directory exists in the location, with the
    tag manifest of a bag.
    """
    package_uuid = uuid.uuid4()
    result = make_package(
        aip_storage_location, f"uncompressedaip-{package_uuid}", uuid=package_uuid
    )
    package_dir = Path(aip_storage_location.full_path) / result.current_path
    package_dir.mkdir()
    (package_dir / "tagmanifest-sha256.txt").touch()
    assert not result.is_compressed

    return result


@pytest.fixture
def deleted_package(
    make_package: PackageFactory, aip_storage_location: models.Location
) -> models.Package:
    return make_package(
        aip_storage_location, "deleted.7z", status=models.Package.DELETED
    )
