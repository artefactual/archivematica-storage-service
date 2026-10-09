import pathlib
import uuid

import pytest
from metsrw.plugins import premisrw

from archivematica.storage_service.locations import models
from archivematica.storage_service.locations.models.replica_staging import (
    OfflineReplicaStaging,
)
from tests.factories import LocationFactory
from tests.factories import PackageFactory
from tests.factories import SpaceFactory


@pytest.fixture
def replica(
    make_space: SpaceFactory,
    make_location: LocationFactory,
    make_package: PackageFactory,
    default_space: models.Space,
    default_ss_internal: models.Location,
    tmp_path: pathlib.Path,
) -> models.Package:
    """A package of an offline replica staging space, with the spaces and
    the internal location of the Storage Service in the temporary directory.
    """
    space = make_space(
        uuid=uuid.UUID("eb4348c7-5ec9-432d-b451-93214860aae2"),
        access_protocol=models.Space.OFFLINE_REPLICA_STAGING,
        path="/archivematica",
        staging_path=str(tmp_path),
    )
    OfflineReplicaStaging.objects.create(space=space)
    location = make_location(
        space,
        models.Location.REPLICATOR,
        uuid=uuid.UUID("ac3dc2d0-8422-4067-bb25-dd3cc1c54c2c"),
        relative_path="offlinestaging",
        description="offline replica staging",
    )

    default_space.path = str(tmp_path)
    default_space.save()

    ss_internal_dir = tmp_path / "internal"
    ss_internal_dir.mkdir()
    default_ss_internal.relative_path = str(ss_internal_dir.relative_to(tmp_path))
    default_ss_internal.save()

    return make_package(
        location,
        "locations/fixtures/small_compressed_bag.zip",
        uuid=uuid.UUID("216a6d25-d705-4d00-86c3-02f51c66a0c0"),
        status="Uploaded",
    )


def test_delete(replica: models.Package) -> None:
    """Test that package in Space isn't deleted."""
    success, err = replica.delete_from_storage()
    assert success is False
    assert err == "Write-Only Offline Staging does not implement deletion"


def test_check_fixity(replica: models.Package) -> None:
    """Test that fixity check raises NotImplementedError."""
    with pytest.raises(NotImplementedError):
        replica.check_fixity()


def test_browse(replica: models.Package) -> None:
    """Test that browse raises NotImplementedError."""
    with pytest.raises(NotImplementedError):
        replica.current_location.space.browse("/test/path")


def test_move_to_storage_service(replica: models.Package) -> None:
    """Test that move_to_storage_service raises NotImplementedError."""
    with pytest.raises(NotImplementedError):
        replica.current_location.space.move_to_storage_service(
            "/test/path", "/dev/null", replica.current_location.space
        )


@pytest.fixture
def offline_space(make_space: SpaceFactory, tmp_path: pathlib.Path) -> models.Space:
    """An offline replica staging space in the temporary directory."""
    space_dir = tmp_path / "offline-space"
    space_dir.mkdir()

    return make_space(
        access_protocol=models.Space.OFFLINE_REPLICA_STAGING,
        path=str(space_dir),
        staging_path=str(space_dir),
    )


@pytest.fixture
def offline_replica_staging_space(offline_space: models.Space) -> OfflineReplicaStaging:
    return OfflineReplicaStaging.objects.create(space=offline_space)


@pytest.fixture
def replicator_location(
    make_location: LocationFactory,
    offline_space: models.Space,
    offline_replica_staging_space: OfflineReplicaStaging,
    aip_storage_location: models.Location,
) -> models.Location:
    """The location of the offline space replicating the AIP storage location."""
    result = make_location(
        offline_space,
        models.Location.REPLICATOR,
        relative_path="replicas",
        description="Replicas",
    )
    pathlib.Path(result.full_path).mkdir()
    aip_storage_location.replicators.add(result)

    return result


@pytest.fixture
def compressed_package_with_dotted_name(
    make_package: PackageFactory, aip_storage_location: models.Location
) -> models.Package:
    """A compressed AIP whose name has dots before its UUID."""
    package_uuid = uuid.uuid4()
    result = make_package(
        aip_storage_location,
        f"small.compressed.bag-{package_uuid}.7z",
        uuid=package_uuid,
    )
    (pathlib.Path(aip_storage_location.full_path) / result.current_path).touch()
    assert result.is_compressed

    return result


@pytest.fixture
def uncompressed_package_with_dotted_name(
    make_package: PackageFactory, aip_storage_location: models.Location
) -> models.Package:
    """An uncompressed AIP whose name has dots before its UUID."""
    package_uuid = uuid.uuid4()
    result = make_package(
        aip_storage_location,
        f"small.uncompressed.bag-{package_uuid}",
        uuid=package_uuid,
    )
    package_dir = pathlib.Path(aip_storage_location.full_path) / result.current_path
    package_dir.mkdir()
    # Add tag manifest to fake a valid bag.
    (package_dir / "tagmanifest-sha256.txt").touch()
    assert not result.is_compressed

    return result


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
