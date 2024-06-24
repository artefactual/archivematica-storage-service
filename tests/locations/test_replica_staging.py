import os
import pathlib
import tempfile
import uuid

import pytest
from django.test import TestCase
from locations import models
from metsrw.plugins import premisrw

from . import TempDirMixin

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"


class TestOfflineReplicaStaging(TempDirMixin, TestCase):
    fixture_files = ["base.json", "replica_staging.json"]
    fixtures = [FIXTURES_DIR / f for f in fixture_files]

    def setUp(self):
        super().setUp()
        self.replica = models.Package.objects.get(id=1)
        self.replica.current_location.space.staging_path = str(self.tmpdir)
        self.replica.current_location.space.save()

        space = models.Space.objects.get(id=1)
        space.path = str(self.tmpdir)
        space.save()

        location = models.Location.objects.get(id=5)
        ss_internal_dir = tempfile.mkdtemp(dir=str(self.tmpdir), prefix="int")
        ss_int_relpath = os.path.relpath(ss_internal_dir, str(self.tmpdir))
        location.relative_path = ss_int_relpath
        location.save()

    def test_delete(self):
        """Test that package in Space isn't deleted."""
        success, err = self.replica.delete_from_storage()
        assert success is False
        assert isinstance(err, NotImplementedError)

    def test_check_fixity(self):
        """Test that fixity check raises NotImplementedError."""
        with self.assertRaises(NotImplementedError):
            self.replica.check_fixity()

    def test_browse(self):
        """Test that browse raises NotImplementedError."""
        with self.assertRaises(NotImplementedError):
            self.replica.current_location.space.browse("/test/path")

    def test_move_to_storage_service(self):
        """Test that move_to_storage_service raises NotImplementedError."""
        with self.assertRaises(NotImplementedError):
            self.replica.current_location.space.move_to_storage_service(
                "/test/path", "/dev/null", self.replica.current_location.space
            )


@pytest.fixture
def fs_space(db, tmp_path):
    space_dir = tmp_path / "fs-space"
    space_dir.mkdir()

    result = models.Space.objects.create(
        access_protocol=models.Space.LOCAL_FILESYSTEM,
        path=space_dir,
        staging_path=space_dir,
    )
    models.LocalFilesystem.objects.create(space=result)

    return result


@pytest.fixture
def offline_space(db, tmp_path):
    space_dir = tmp_path / "offline-space"
    space_dir.mkdir()

    return models.Space.objects.create(
        access_protocol=models.Space.OFFLINE_REPLICA_STAGING,
        path=space_dir,
        staging_path=space_dir,
    )


@pytest.fixture
def offline_replica_staging_space(db, offline_space):
    return models.OfflineReplicaStaging.objects.create(space=offline_space)


@pytest.fixture
def aip_storage_location(db, fs_space):
    result = models.Location.objects.create(
        description="AIPs",
        space=fs_space,
        relative_path="aips",
        purpose=models.Location.AIP_STORAGE,
    )
    pathlib.Path(result.full_path).mkdir()

    return result


@pytest.fixture
def ss_internal_location(db, fs_space):
    result = models.Location.objects.create(
        space=fs_space,
        relative_path="internal",
        purpose=models.Location.STORAGE_SERVICE_INTERNAL,
    )
    pathlib.Path(result.full_path).mkdir()

    return result


@pytest.fixture
def replicator_location(
    db, offline_space, offline_replica_staging_space, aip_storage_location
):
    result = models.Location.objects.create(
        description="Replicas",
        space=offline_space,
        relative_path="replicas",
        purpose=models.Location.REPLICATOR,
    )
    pathlib.Path(result.full_path).mkdir()
    aip_storage_location.replicators.add(result)

    return result


def _create_compressed_package(aip_storage_location, base_name):
    package_uuid = uuid.uuid4()
    package_current_path = f"{base_name}-{package_uuid}.7z"
    (pathlib.Path(aip_storage_location.full_path) / package_current_path).touch()

    result = models.Package.objects.create(
        uuid=package_uuid,
        current_location=aip_storage_location,
        current_path=package_current_path,
        package_type=models.Package.AIP,
    )
    assert result.is_compressed

    return result


@pytest.fixture
def compressed_package(db, aip_storage_location):
    return _create_compressed_package(aip_storage_location, "small-compressed-bag")


@pytest.fixture
def compressed_package_with_dotted_name(db, aip_storage_location):
    return _create_compressed_package(aip_storage_location, "small.compressed.bag")


def _create_uncompressed_package(aip_storage_location, base_name):
    package_uuid = uuid.uuid4()
    package_current_path = f"{base_name}-{package_uuid}"
    package_dir = pathlib.Path(aip_storage_location.full_path) / package_current_path
    package_dir.mkdir()

    # Add tag manifest to fake a valid bag.
    (package_dir / "tagmanifest-sha256.txt").touch()

    result = models.Package.objects.create(
        uuid=package_uuid,
        current_location=aip_storage_location,
        current_path=package_current_path,
        package_type=models.Package.AIP,
    )
    assert not result.is_compressed

    return result


@pytest.fixture
def uncompressed_package(db, aip_storage_location):
    return _create_uncompressed_package(aip_storage_location, "small-uncompressed-bag")


@pytest.fixture
def uncompressed_package_with_dotted_name(db, aip_storage_location):
    return _create_uncompressed_package(aip_storage_location, "small.uncompressed.bag")


PREMIS_COMPRESSION_EVENT_DATA = (
    "event",
    premisrw.PREMIS_META,
    (
        "event_identifier",
        ("event_identifier_type", "UUID"),
        ("event_identifier_value", "4711f4eb-8903-4e58-85da-4827e6530d0b"),
    ),
    ("event_type", "compression"),
    ("event_date_time", "2017-08-15T00:30:55"),
    (
        "event_detail",
        (
            "program=7z; "
            "version=p7zip Version 9.20 "
            "(locale=en_US.UTF-8,Utf16=on,HugeFiles=on,2 CPUs); "
            "algorithm=bzip2"
        ),
    ),
    (
        "event_outcome_information",
        (
            "event_outcome_detail",
            (
                "event_outcome_detail_note",
                'Standard Output="..."; Standard Error=""',
            ),
        ),
    ),
    (
        "linking_agent_identifier",
        ("linking_agent_identifier_type", "foobar"),
        ("linking_agent_identifier_value", "foobar"),
    ),
)

PREMIS_AGENT_DATA = (
    "agent",
    premisrw.PREMIS_3_0_META,
    (
        "agent_identifier",
        ("agent_identifier_type", "foobar"),
        ("agent_identifier_value", "foobar"),
    ),
    ("agent_name", "foobar"),
    ("agent_type", "foobar"),
)


@pytest.mark.parametrize(
    "package_fixture,premis_events,premis_agents",
    [
        (
            "compressed_package",
            [PREMIS_COMPRESSION_EVENT_DATA],
            [PREMIS_AGENT_DATA],
        ),
        (
            "compressed_package_with_dotted_name",
            [PREMIS_COMPRESSION_EVENT_DATA],
            [PREMIS_AGENT_DATA],
        ),
        ("uncompressed_package", None, None),
        ("uncompressed_package_with_dotted_name", None, None),
    ],
    ids=[
        "compressed_package",
        "compressed_package_with_dotted_name",
        "uncompressed_package",
        "uncompressed_package_with_dotted_name",
    ],
)
def test_package_is_replicated_to_offline_space(
    request,
    ss_internal_location,
    aip_storage_location,
    replicator_location,
    package_fixture,
    premis_events,
    premis_agents,
):
    package = request.getfixturevalue(package_fixture)
    package.store_aip(
        origin_location=aip_storage_location,
        origin_path=package.current_path,
        premis_events=premis_events,
        premis_agents=premis_agents,
    )

    assert models.Package.objects.count() == 2

    assert models.Package.objects.filter(replicated_package__isnull=False).count() == 1
    replica = models.Package.objects.get(replicated_package__isnull=False)
    assert package.uuid == replica.replicated_package.uuid
