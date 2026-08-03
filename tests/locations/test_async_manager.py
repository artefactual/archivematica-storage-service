import datetime
import pickle
from unittest import mock

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from archivematica.storage_service.locations import metrics
from archivematica.storage_service.locations.models.asynchronous import Async
from archivematica.storage_service.locations.models.asynchronous import serialize_error
from archivematica.storage_service.locations.models.async_manager import AsyncManager
from archivematica.storage_service.locations.models.async_manager import (
    INTERRUPTED_TASK_ERROR_CODE,
)
from archivematica.storage_service.locations.models.async_manager import (
    MAX_TASK_AGE_SECONDS,
)
from archivematica.storage_service.locations.models.async_manager import (
    TASK_TIMEOUT_SECONDS,
)
from archivematica.storage_service.locations.models.async_manager import RunningTask


@pytest.fixture(autouse=True)
def reset_running_tasks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(AsyncManager, "running_tasks", [])


def test_serialize_error_preserves_async_error_format() -> None:
    error = RuntimeError("Something went wrong")

    serialized = serialize_error(error)

    assert pickle.loads(serialized) == "<class 'RuntimeError'>: Something went wrong"

    async_task = Async()
    async_task.error = error
    assert async_task._error == serialized
    assert async_task.error == "<class 'RuntimeError'>: Something went wrong"


@pytest.mark.django_db
def test_watchdog_marks_expired_task_as_interrupted(admin_client: Client) -> None:
    async_task = Async.objects.create()
    Async.objects.filter(pk=async_task.pk).update(
        updated_time=timezone.now()
        - TASK_TIMEOUT_SECONDS
        - datetime.timedelta(seconds=1)
    )

    AsyncManager._watchdog_loop()

    async_task.refresh_from_db()
    assert async_task.completed is True
    assert async_task.was_error is True
    assert async_task.completed_time is not None
    assert "heartbeat expired" in async_task.error
    assert "final outcome is unknown" in async_task.error

    response = admin_client.get(
        reverse(
            "api_dispatch_detail",
            kwargs={"api_name": "v2", "resource_name": "async", "id": async_task.pk},
        )
    )
    assert response.status_code == 200
    assert response.json()["completed"] is True
    assert response.json()["was_error"] is True
    assert response.json()["error_code"] == INTERRUPTED_TASK_ERROR_CODE
    assert response.json()["error"] == async_task.error


@pytest.mark.django_db
def test_async_resource_does_not_classify_task_error(admin_client: Client) -> None:
    async_task = Async.objects.create(
        completed=True,
        was_error=True,
        completed_time=timezone.now(),
    )
    async_task.error = RuntimeError("Something went wrong")
    async_task.save()

    response = admin_client.get(
        reverse(
            "api_dispatch_detail",
            kwargs={"api_name": "v2", "resource_name": "async", "id": async_task.pk},
        )
    )

    assert response.status_code == 200
    assert response.json()["error_code"] is None
    assert response.json()["error"] == async_task.error


@pytest.mark.django_db
def test_watchdog_leaves_fresh_incomplete_task_running() -> None:
    async_task = Async.objects.create()

    AsyncManager._watchdog_loop()

    async_task.refresh_from_db()
    assert async_task.completed is False
    assert async_task.was_error is False
    assert async_task.completed_time is None


@pytest.mark.django_db
def test_watchdog_deletes_expired_terminal_result() -> None:
    async_task = Async.objects.create(
        completed=True,
        completed_time=timezone.now(),
    )
    async_task.result = "Done"
    async_task.save()
    Async.objects.filter(pk=async_task.pk).update(
        completed_time=timezone.now()
        - MAX_TASK_AGE_SECONDS
        - datetime.timedelta(seconds=1)
    )

    AsyncManager._watchdog_loop()

    assert not Async.objects.filter(pk=async_task.pk).exists()


@pytest.mark.django_db
def test_watchdog_records_local_completion_before_expiring() -> None:
    async_task = Async.objects.create()
    Async.objects.filter(pk=async_task.pk).update(
        updated_time=timezone.now()
        - TASK_TIMEOUT_SECONDS
        - datetime.timedelta(seconds=1)
    )
    running_task = RunningTask()
    running_task.async_id = async_task.pk
    running_task.thread = mock.Mock()
    running_task.thread.is_alive.return_value = False
    running_task.result = "Done"
    AsyncManager.running_tasks = [running_task]

    with mock.patch.object(metrics.async_manager_running_tasks, "dec"):
        AsyncManager._watchdog_loop()

    async_task.refresh_from_db()
    assert async_task.completed is True
    assert async_task.was_error is False
    assert async_task.result == "Done"


@pytest.mark.django_db
def test_watchdog_heartbeats_local_task_before_expiring() -> None:
    async_task = Async.objects.create()
    expired_time = (
        timezone.now()
        - TASK_TIMEOUT_SECONDS
        - datetime.timedelta(seconds=1)
    )
    Async.objects.filter(pk=async_task.pk).update(updated_time=expired_time)
    running_task = RunningTask()
    running_task.async_id = async_task.pk
    running_task.thread = mock.Mock()
    running_task.thread.is_alive.return_value = True
    AsyncManager.running_tasks = [running_task]

    AsyncManager._watchdog_loop()

    async_task.refresh_from_db()
    assert async_task.completed is False
    assert async_task.updated_time > expired_time


@pytest.mark.django_db
def test_watchdog_heartbeats_task_that_finishes_after_liveness_check() -> None:
    async_task = Async.objects.create()
    expired_time = timezone.now() - TASK_TIMEOUT_SECONDS - datetime.timedelta(seconds=1)
    Async.objects.filter(pk=async_task.pk).update(updated_time=expired_time)
    running_task = RunningTask()
    running_task.async_id = async_task.pk
    running_task.thread = mock.Mock()
    running_task.thread.is_alive.side_effect = [True, False]
    running_task.result = "Done"
    AsyncManager.running_tasks = [running_task]

    AsyncManager._watchdog_loop()

    async_task.refresh_from_db()
    assert running_task.thread.is_alive.call_count == 1
    assert async_task.completed is False
    assert async_task.updated_time > expired_time

    with mock.patch.object(metrics.async_manager_running_tasks, "dec"):
        AsyncManager._watchdog_loop()

    async_task.refresh_from_db()
    assert async_task.completed is True
    assert async_task.was_error is False
    assert async_task.result == "Done"


@pytest.mark.django_db
def test_watchdog_does_not_overwrite_terminal_result() -> None:
    async_task = Async.objects.create(
        completed=True,
        was_error=True,
        completed_time=timezone.now(),
    )
    async_task.error = RuntimeError("Interrupted")
    async_task.save()
    running_task = RunningTask()
    running_task.async_id = async_task.pk
    running_task.thread = mock.Mock()
    running_task.thread.is_alive.return_value = False
    running_task.result = "Late result"
    AsyncManager.running_tasks = [running_task]

    with mock.patch.object(metrics.async_manager_running_tasks, "dec"):
        AsyncManager._watchdog_loop()

    async_task.refresh_from_db()
    assert async_task.completed is True
    assert async_task.was_error is True
    assert async_task.error == "<class 'RuntimeError'>: Interrupted"
    assert async_task._result is None
