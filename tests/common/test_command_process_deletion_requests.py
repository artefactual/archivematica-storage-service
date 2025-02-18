from pathlib import Path
from typing import Any
from unittest import mock
from uuid import uuid4

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from archivematica.storage_service.common.management.commands import (
    process_deletion_requests,
)
from archivematica.storage_service.locations import models
from archivematica.storage_service.locations.models.local_filesystem import (
    LocalFilesystem,
)


@pytest.fixture
def aip_storage_location(tmp_path: Path) -> models.Location:
    space_dir = tmp_path / "space"
    space_dir.mkdir()
    staging_dir = tmp_path / "staging"
    staging_dir.mkdir()

    space = models.Space.objects.create(
        access_protocol=models.Space.LOCAL_FILESYSTEM,
        path=str(space_dir),
        staging_path=str(staging_dir),
    )
    LocalFilesystem.objects.create(space=space)

    return models.Location.objects.create(
        space=space,
        purpose=models.Location.AIP_STORAGE,
        relative_path="aips",
    )


@pytest.fixture
def pipeline(db: Any) -> models.Pipeline:
    return models.Pipeline.objects.create(description="Pipeline")


def _create_deletion_event(
    *,
    package: models.Package,
    pipeline: models.Pipeline,
) -> models.Event:
    return models.Event.objects.create(
        package=package,
        event_type=models.Event.DELETE,
        event_reason="Requested via tests",
        pipeline=pipeline,
        user_id=1,
        user_email="requester@example.com",
        status=models.Event.SUBMITTED,
        store_data=package.status,
    )


@pytest.fixture
def package(aip_storage_location: models.Location) -> models.Package:
    return models.Package.objects.create(
        current_location=aip_storage_location,
        current_path="package.7z",
        package_type=models.Package.AIP,
        status=models.Package.DEL_REQ,
    )


@pytest.fixture
def deletion_event(package: models.Package, pipeline: models.Pipeline) -> models.Event:
    return _create_deletion_event(package=package, pipeline=pipeline)


@pytest.mark.django_db
def test_process_deletion_requests_lists_pending_requests(
    capsys: pytest.CaptureFixture[str],
    deletion_event: models.Event,
) -> None:
    call_command("process_deletion_requests")

    captured = capsys.readouterr()
    lines = captured.out.splitlines()

    assert lines == [str(deletion_event), "Total deletion requests: 1"]


@pytest.mark.django_db
def test_process_deletion_requests_approve(
    capsys: pytest.CaptureFixture[str],
    deletion_event: models.Event,
    django_user_model: Any,
) -> None:
    admin_user = django_user_model.objects.create_user(
        username="admin", password="password"
    )

    call_command(
        "process_deletion_requests",
        "--approve",
        str(deletion_event.package.uuid),
        "--admin-id",
        str(admin_user.pk),
    )

    lines = capsys.readouterr().out.splitlines()

    assert set(lines) == {
        f"Processing package {deletion_event.package.uuid}",
        "Request approved: Package deleted successfully.",
    }


@pytest.mark.django_db
def test_process_deletion_requests_approve_all(
    capsys: pytest.CaptureFixture[str],
    deletion_event: models.Event,
    django_user_model: Any,
) -> None:
    admin_user = django_user_model.objects.create_user(
        username="admin", password="password"
    )

    second_package = models.Package.objects.create(
        current_location=deletion_event.package.current_location,
        current_path="second-package.7z",
        package_type=models.Package.AIP,
        status=models.Package.DEL_REQ,
    )
    second_event = _create_deletion_event(
        package=second_package, pipeline=deletion_event.pipeline
    )

    with mock.patch.object(
        models.Package, "delete_from_storage", return_value=(True, None)
    ) as delete_from_storage:
        call_command(
            "process_deletion_requests",
            "--approve-all",
            "--admin-id",
            str(admin_user.pk),
        )

    captured = capsys.readouterr()
    lines = captured.out.splitlines()

    assert set(lines) == {
        f"Processing package {deletion_event.package.uuid}",
        "Request approved: Package deleted successfully.",
        f"Processing package {second_package.uuid}",
    }

    assert delete_from_storage.call_count == 2

    deletion_event.refresh_from_db()
    deletion_event.package.refresh_from_db()
    second_event.refresh_from_db()
    second_package.refresh_from_db()

    assert deletion_event.status == models.Event.APPROVED
    assert deletion_event.status_reason == process_deletion_requests.APPROVAL_REASON
    assert deletion_event.admin_id_id == admin_user.pk
    assert deletion_event.package.status == models.Package.DELETED

    assert second_event.status == models.Event.APPROVED
    assert second_event.status_reason == process_deletion_requests.APPROVAL_REASON
    assert second_event.admin_id_id == admin_user.pk
    assert second_package.status == models.Package.DELETED


@pytest.mark.django_db
def test_process_deletion_requests_reports_missing_event(
    capsys: pytest.CaptureFixture[str],
    deletion_event: models.Event,
    django_user_model: Any,
) -> None:
    admin_user = django_user_model.objects.create_user(
        username="admin", password="password"
    )
    nonexistent_uuid = uuid4()

    call_command(
        "process_deletion_requests",
        "--approve",
        str(nonexistent_uuid),
        "--admin-id",
        str(admin_user.pk),
    )

    lines = capsys.readouterr().out.splitlines()

    assert lines[-1] == (
        f"Error: There is no pending deletion request for package UUID "
        f"{nonexistent_uuid}"
    )


@pytest.mark.django_db
def test_process_deletion_requests_requires_valid_admin(
    deletion_event: models.Event,
) -> None:
    with pytest.raises(CommandError, match="Admin user with id 999 does not exist."):
        call_command(
            "process_deletion_requests",
            "--approve-all",
            "--admin-id",
            "999",
        )
