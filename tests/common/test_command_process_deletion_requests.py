from unittest import mock
from uuid import uuid4

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError

from archivematica.storage_service.common.management.commands import (
    process_deletion_requests,
)
from archivematica.storage_service.locations import models
from tests.factories import EventFactory
from tests.factories import PackageFactory


@pytest.fixture
def package(package: models.Package) -> models.Package:
    """The AIP whose deletion was requested."""
    package.status = models.Package.DEL_REQ
    package.save()

    return package


@pytest.fixture
def deletion_event(
    make_event: EventFactory, package: models.Package, pipeline: models.Pipeline
) -> models.Event:
    return make_event(package, pipeline)


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
    admin_user: User,
) -> None:
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
    admin_user: User,
    make_package: PackageFactory,
    make_event: EventFactory,
) -> None:
    second_package = make_package(
        deletion_event.package.current_location,
        "second-package.7z",
        status=models.Package.DEL_REQ,
    )
    second_event = make_event(second_package, deletion_event.pipeline)

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
    admin_user: User,
) -> None:
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
