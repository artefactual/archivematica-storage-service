import pathlib
import uuid

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from archivematica.storage_service.locations import models


@pytest.fixture
def fs_space(tmp_path: pathlib.Path) -> models.Space:
    space_dir = tmp_path / "space"
    space_dir.mkdir()
    staging_dir = tmp_path / "staging"
    staging_dir.mkdir()

    result = models.Space.objects.create(
        access_protocol=models.Space.LOCAL_FILESYSTEM,
        path=str(space_dir),
        staging_path=str(staging_dir),
        used=30,
    )
    models.LocalFilesystem.objects.create(space=result)
    return result


@pytest.fixture
def aip_storage_location(fs_space: models.Space) -> models.Location:
    return models.Location.objects.create(
        space=fs_space,
        purpose=models.Location.AIP_STORAGE,
        relative_path="aips",
        used=10,
    )


@pytest.fixture
def dip_storage_location(fs_space: models.Space) -> models.Location:
    return models.Location.objects.create(
        space=fs_space,
        purpose=models.Location.DIP_STORAGE,
        relative_path="dips",
        used=5,
    )


@pytest.fixture
def replicator_location(fs_space: models.Space) -> models.Location:
    return models.Location.objects.create(
        space=fs_space,
        purpose=models.Location.REPLICATOR,
        relative_path="replicas",
        used=15,
    )


@pytest.mark.django_db
def test_command_reconciles_aip_dip_and_replica_location_and_space_sizes(
    aip_storage_location: models.Location,
    dip_storage_location: models.Location,
    replicator_location: models.Location,
    fs_space: models.Space,
) -> None:
    models.Package.objects.create(
        uuid=uuid.uuid4(),
        package_type=models.Package.AIP,
        status=models.Package.UPLOADED,
        current_location=aip_storage_location,
        current_path="aip.7z",
        size=100,
    )
    models.Package.objects.create(
        uuid=uuid.uuid4(),
        package_type=models.Package.DIP,
        status=models.Package.UPLOADED,
        current_location=dip_storage_location,
        current_path="dip",
        size=25,
    )
    models.Package.objects.create(
        uuid=uuid.uuid4(),
        package_type=models.Package.AIP,
        status=models.Package.STAGING,
        current_location=aip_storage_location,
        current_path="staging.7z",
        size=50,
    )
    models.Package.objects.create(
        uuid=uuid.uuid4(),
        package_type=models.Package.AIP,
        status=models.Package.DELETED,
        current_location=aip_storage_location,
        current_path="deleted.7z",
        size=300,
    )
    models.Package.objects.create(
        uuid=uuid.uuid4(),
        package_type=models.Package.DIP,
        status=models.Package.FINALIZED,
        current_location=dip_storage_location,
        current_path="finalized",
        size=75,
    )
    models.Package.objects.create(
        uuid=uuid.uuid4(),
        package_type=models.Package.AIP,
        status=models.Package.UPLOADED,
        current_location=replicator_location,
        current_path="replica.7z",
        size=200,
    )

    call_command("reconcile_location_sizes")

    aip_storage_location.refresh_from_db()
    dip_storage_location.refresh_from_db()
    replicator_location.refresh_from_db()
    fs_space.refresh_from_db()
    assert aip_storage_location.used == 150
    assert dip_storage_location.used == 25
    assert replicator_location.used == 200
    assert fs_space.used == 375


@pytest.mark.django_db
def test_command_dry_run_does_not_update_size_counters(
    aip_storage_location: models.Location,
    fs_space: models.Space,
) -> None:
    models.Package.objects.create(
        uuid=uuid.uuid4(),
        package_type=models.Package.AIP,
        status=models.Package.UPLOADED,
        current_location=aip_storage_location,
        current_path="aip.7z",
        size=100,
    )

    call_command("reconcile_location_sizes", "--dry-run")

    aip_storage_location.refresh_from_db()
    fs_space.refresh_from_db()
    assert aip_storage_location.used == 10
    assert fs_space.used == 30


@pytest.mark.django_db
def test_command_does_not_adjust_space_when_selected_location_already_matches(
    dip_storage_location: models.Location,
    fs_space: models.Space,
) -> None:
    dip_storage_location.used = 0
    dip_storage_location.save()
    fs_space.used = 210
    fs_space.save()

    call_command(
        "reconcile_location_sizes",
        "--location-uuid",
        dip_storage_location.uuid,
    )

    dip_storage_location.refresh_from_db()
    fs_space.refresh_from_db()
    assert dip_storage_location.used == 0
    assert fs_space.used == 210


@pytest.mark.django_db
def test_command_can_reconcile_a_specific_replicator_location(
    replicator_location: models.Location,
    fs_space: models.Space,
) -> None:
    models.Package.objects.create(
        uuid=uuid.uuid4(),
        package_type=models.Package.AIP,
        status=models.Package.UPLOADED,
        current_location=replicator_location,
        current_path="replica.7z",
        size=200,
    )

    call_command(
        "reconcile_location_sizes",
        "--location-uuid",
        replicator_location.uuid,
    )

    replicator_location.refresh_from_db()
    fs_space.refresh_from_db()
    assert replicator_location.used == 200
    assert fs_space.used == 215


@pytest.mark.django_db
def test_command_fails_when_no_locations_match() -> None:
    with pytest.raises(
        CommandError,
        match="No AIP Storage, DIP Storage, or Replicator locations",
    ):
        call_command("reconcile_location_sizes")
