from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from archivematica.storage_service.administration.models import Settings
from archivematica.storage_service.locations import models


@pytest.fixture
def fs_space(tmp_path: Path) -> models.Space:
    space_dir = tmp_path / "space"
    space_dir.mkdir()

    staging_dir = tmp_path / "staging"
    staging_dir.mkdir()

    space = models.Space.objects.create(
        access_protocol=models.Space.LOCAL_FILESYSTEM,
        path=str(space_dir),
        staging_path=str(staging_dir),
    )
    models.LocalFilesystem.objects.create(space=space)
    return space


@pytest.fixture
def replicator(fs_space: models.Space) -> models.Location:
    return models.Location.objects.create(
        space=fs_space,
        purpose=models.Location.REPLICATOR,
        relative_path="replicator",
    )


@pytest.mark.django_db
def test_command_sets_lone_replicator_to_fail(
    capsys: pytest.CaptureFixture[str],
    replicator: models.Location,
) -> None:
    call_command("set_replica_to_fail", "true")

    replicator.refresh_from_db()

    assert replicator.fail_replication is True
    assert Settings.objects.filter(
        name=replicator.replication_failure_setting_name, value="True"
    ).exists()
    assert (
        capsys.readouterr().out.strip()
        == f"Replicator {replicator.uuid} fail_replication set to True."
    )


@pytest.mark.django_db
def test_command_can_clear_replicator_failure_flag(
    capsys: pytest.CaptureFixture[str],
    replicator: models.Location,
) -> None:
    replicator.fail_replication = True

    call_command("set_replica_to_fail", "false")

    replicator.refresh_from_db()

    assert replicator.fail_replication is False
    assert not Settings.objects.filter(
        name=replicator.replication_failure_setting_name
    ).exists()
    assert (
        capsys.readouterr().out.strip()
        == f"Replicator {replicator.uuid} fail_replication set to False."
    )


@pytest.mark.django_db
def test_command_raises_when_multiple_replicators_exist_without_id(
    capsys: pytest.CaptureFixture[str],
    fs_space: models.Space,
    replicator: models.Location,
) -> None:
    second_replicator = models.Location.objects.create(
        space=fs_space,
        purpose=models.Location.REPLICATOR,
        relative_path="replicator-2",
    )

    with pytest.raises(
        CommandError,
        match="can't choose a replicator, pass --id=<uuid> to indicate which",
    ):
        call_command("set_replica_to_fail", "true")

    lines = capsys.readouterr().out.splitlines()
    expected_replicators = sorted(
        [replicator, second_replicator], key=lambda location: str(location.uuid)
    )
    assert lines == [
        "Replicators found:",
        *(f"  {location}" for location in expected_replicators),
    ]
    assert replicator.fail_replication is False
    assert second_replicator.fail_replication is False


@pytest.mark.django_db
def test_command_uses_explicit_id_when_multiple_replicators_exist(
    capsys: pytest.CaptureFixture[str],
    fs_space: models.Space,
    replicator: models.Location,
) -> None:
    second_replicator = models.Location.objects.create(
        space=fs_space,
        purpose=models.Location.REPLICATOR,
        relative_path="replicator-2",
    )

    call_command("set_replica_to_fail", "true", "--id", str(second_replicator.uuid))

    replicator.refresh_from_db()
    second_replicator.refresh_from_db()

    assert replicator.fail_replication is False
    assert second_replicator.fail_replication is True
    assert (
        capsys.readouterr().out.strip()
        == f"Replicator {second_replicator.uuid} fail_replication set to True."
    )


@pytest.mark.django_db
def test_command_rejects_unknown_replicator_id(db) -> None:
    with pytest.raises(CommandError, match="No Replicator location found with id"):
        call_command(
            "set_replica_to_fail",
            "true",
            "--id",
            "00000000-0000-0000-0000-000000000000",
        )


@pytest.mark.django_db
def test_command_rejects_missing_replicators(db) -> None:
    with pytest.raises(CommandError, match="No Replicator locations found."):
        call_command("set_replica_to_fail", "true")


@pytest.mark.django_db
def test_command_rejects_invalid_boolean_value(replicator: models.Location) -> None:
    with pytest.raises(CommandError, match="Invalid value 'maybe'"):
        call_command("set_replica_to_fail", "maybe")
