import datetime
import logging
import pickle
import threading
from collections.abc import Callable
from collections.abc import Iterator
from unittest import mock

import pytest
from django.db import close_old_connections
from django.db import connection
from django.db import transaction
from django.db.backends.utils import CursorWrapper
from django.db.models.query import QuerySet
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from archivematica.storage_service.locations import metrics
from archivematica.storage_service.locations.models.async_manager import (
    INTERRUPTED_TASK_ERROR,
)
from archivematica.storage_service.locations.models.async_manager import (
    INTERRUPTED_TASK_ERROR_CODE,
)
from archivematica.storage_service.locations.models.async_manager import (
    MAX_TASK_AGE_SECONDS,
)
from archivematica.storage_service.locations.models.async_manager import (
    TASK_TIMEOUT_SECONDS,
)
from archivematica.storage_service.locations.models.async_manager import AsyncManager
from archivematica.storage_service.locations.models.async_manager import RunningTask
from archivematica.storage_service.locations.models.async_manager import (
    get_async_error_code,
)
from archivematica.storage_service.locations.models.asynchronous import Async
from archivematica.storage_service.locations.models.asynchronous import serialize_error


@pytest.fixture(autouse=True)
def reset_running_tasks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(AsyncManager, "running_tasks", [])


def _run_database_thread(
    function: Callable[[], None],
    errors: list[BaseException],
    done: threading.Event,
) -> None:
    close_old_connections()
    try:
        function()
    except BaseException as error:
        errors.append(error)
    finally:
        close_old_connections()
        done.set()


def _run_database_operation(function: Callable[[], None]) -> None:
    errors: list[BaseException] = []
    done = threading.Event()
    thread = threading.Thread(
        target=_run_database_thread,
        args=(function, errors, done),
    )

    thread.start()
    assert done.wait(timeout=10)
    thread.join(timeout=10)
    assert not thread.is_alive()
    if errors:
        raise errors[0]


@pytest.fixture
def committed_expired_async_task() -> Iterator[tuple[int, datetime.datetime]]:
    """Create committed state visible to independent database connections.

    Avoid ``transaction=True`` so these tests do not flush data migrations when
    pytest reuses its test database.
    """
    if not connection.features.has_select_for_update:
        pytest.skip("The database backend does not support row-level locks")

    expired_time = timezone.now() - TASK_TIMEOUT_SECONDS - datetime.timedelta(seconds=1)
    async_task_ids: list[int] = []

    def create_task() -> None:
        async_task = Async.objects.create()
        Async.objects.filter(pk=async_task.pk).update(updated_time=expired_time)
        async_task_ids.append(async_task.pk)

    _run_database_operation(create_task)
    async_task_id = async_task_ids[0]

    yield async_task_id, expired_time

    def delete_task() -> None:
        Async.objects.filter(pk=async_task_id).delete()

    _run_database_operation(delete_task)


def test_serialize_error_preserves_async_error_format() -> None:
    error = RuntimeError("Something went wrong")

    serialized = serialize_error(error)

    assert pickle.loads(serialized) == "<class 'RuntimeError'>: Something went wrong"

    async_task = Async()
    async_task.error = error
    assert async_task._error == serialized
    assert async_task.error == "<class 'RuntimeError'>: Something went wrong"


@pytest.mark.parametrize(
    "error",
    [INTERRUPTED_TASK_ERROR, memoryview(INTERRUPTED_TASK_ERROR)],
    ids=["bytes", "memoryview"],
)
def test_get_async_error_code_recognizes_interrupted_task(
    error: bytes | memoryview,
) -> None:
    assert get_async_error_code(error) == INTERRUPTED_TASK_ERROR_CODE


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
def test_watchdog_records_local_error_before_expiring() -> None:
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
    running_task.was_error = True
    running_task.error = RuntimeError("Task failed")
    AsyncManager.running_tasks = [running_task]

    with mock.patch.object(metrics.async_manager_running_tasks, "dec"):
        AsyncManager._watchdog_loop()

    async_task.refresh_from_db()
    assert async_task.completed is True
    assert async_task.was_error is True
    assert async_task.error == "<class 'RuntimeError'>: Task failed"
    assert async_task._result is None


@pytest.mark.django_db
def test_watchdog_heartbeats_local_task_before_expiring() -> None:
    async_task = Async.objects.create()
    expired_time = timezone.now() - TASK_TIMEOUT_SECONDS - datetime.timedelta(seconds=1)
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
def test_watchdog_does_not_interrupt_task_heartbeated_after_candidate_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async_task = Async.objects.create()
    expired_time = timezone.now() - TASK_TIMEOUT_SECONDS - datetime.timedelta(seconds=1)
    Async.objects.filter(pk=async_task.pk).update(updated_time=expired_time)
    original_update = QuerySet.update
    interruption_attempted = False

    def heartbeat_before_interruption(
        queryset: QuerySet[Async], **kwargs: object
    ) -> int:
        nonlocal interruption_attempted
        if kwargs.get("_error") == INTERRUPTED_TASK_ERROR:
            interruption_attempted = True
            original_update(
                Async.objects.filter(pk=async_task.pk), updated_time=timezone.now()
            )
        return original_update(queryset, **kwargs)

    monkeypatch.setattr(QuerySet, "update", heartbeat_before_interruption)

    with mock.patch.object(
        metrics.async_manager_interrupted_tasks_counter, "inc"
    ) as increment:
        AsyncManager._watchdog_loop()

    async_task.refresh_from_db()
    assert interruption_attempted is True
    assert async_task.completed is False
    assert async_task.updated_time > expired_time
    increment.assert_not_called()


@pytest.mark.django_db
def test_watchdog_does_not_overwrite_terminal_result() -> None:
    async_task = Async.objects.create(
        completed=True,
        was_error=True,
        completed_time=timezone.now(),
    )
    async_task.error = RuntimeError("Interrupted")
    async_task.save()
    Async.objects.filter(pk=async_task.pk).update(
        updated_time=timezone.now()
        - TASK_TIMEOUT_SECONDS
        - datetime.timedelta(seconds=1)
    )
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


@pytest.mark.django_db
def test_watchdog_reports_interrupted_tasks(
    caplog: pytest.LogCaptureFixture,
) -> None:
    expired_time = timezone.now() - TASK_TIMEOUT_SECONDS - datetime.timedelta(seconds=1)
    async_tasks = [Async.objects.create(), Async.objects.create()]
    Async.objects.filter(pk__in=[task.pk for task in async_tasks]).update(
        updated_time=expired_time
    )

    with (
        mock.patch.object(
            metrics.async_manager_interrupted_tasks_counter, "inc"
        ) as increment,
        caplog.at_level(logging.WARNING),
    ):
        AsyncManager._watchdog_loop()
        AsyncManager._watchdog_loop()

    increment.assert_called_once_with(2)
    assert caplog.text.count("Marked 2 asynchronous task(s) as interrupted") == 1
    for async_task in async_tasks:
        assert str(async_task.pk) in caplog.text


@pytest.mark.django_db
def test_concurrent_interruption_is_not_replaced_by_late_completion(
    monkeypatch: pytest.MonkeyPatch,
    committed_expired_async_task: tuple[int, datetime.datetime],
) -> None:
    """An interruption committed first remains the terminal state."""
    async_task_id, expired_time = committed_expired_async_task
    running_task = RunningTask()
    running_task.async_id = async_task_id
    running_task.thread = mock.Mock()
    running_task.thread.is_alive.return_value = False
    running_task.result = "Late result"
    AsyncManager.running_tasks = [running_task]

    interruption_ready = threading.Event()
    allow_interruption_commit = threading.Event()
    completion_select_started = threading.Event()
    interruption_done = threading.Event()
    completion_done = threading.Event()
    errors: list[BaseException] = []

    def interrupt_task() -> None:
        with transaction.atomic():
            interrupted_count = Async.objects.filter(
                pk=async_task_id,
                completed=False,
                updated_time__lte=expired_time,
            ).update(
                completed=True,
                was_error=True,
                completed_time=timezone.now(),
                updated_time=timezone.now(),
                _error=INTERRUPTED_TASK_ERROR,
            )
            assert interrupted_count == 1
            interruption_ready.set()
            assert allow_interruption_commit.wait(timeout=10)

    def complete_task() -> None:
        AsyncManager._watchdog_loop()

    interruption_thread = threading.Thread(
        target=_run_database_thread,
        args=(interrupt_task, errors, interruption_done),
    )
    completion_thread = threading.Thread(
        target=_run_database_thread,
        args=(complete_task, errors, completion_done),
    )
    original_execute = CursorWrapper.execute

    def observe_completion_select(
        cursor: CursorWrapper, sql: str, params: object = None
    ) -> object:
        if (
            threading.current_thread() is completion_thread
            and "FOR UPDATE" in sql.upper()
        ):
            completion_select_started.set()
        return original_execute(cursor, sql, params)

    monkeypatch.setattr(CursorWrapper, "execute", observe_completion_select)

    interruption_thread.start()
    assert interruption_ready.wait(timeout=10)
    with mock.patch.object(metrics.async_manager_running_tasks, "dec"):
        completion_thread.start()
        try:
            # The completion read must wait for the interruption's row lock.
            assert completion_select_started.wait(timeout=10)
            assert not completion_done.wait(timeout=0.1)
        finally:
            allow_interruption_commit.set()
        interruption_thread.join(timeout=10)
        completion_thread.join(timeout=10)

    assert not interruption_thread.is_alive()
    assert not completion_thread.is_alive()
    assert errors == []
    async_task = Async.objects.get(pk=async_task_id)
    assert async_task.completed is True
    assert async_task.was_error is True
    assert async_task.error == pickle.loads(INTERRUPTED_TASK_ERROR)
    assert async_task._result is None


@pytest.mark.django_db
def test_concurrent_completion_is_not_replaced_by_interruption(
    monkeypatch: pytest.MonkeyPatch,
    committed_expired_async_task: tuple[int, datetime.datetime],
) -> None:
    """A completion committed first remains the terminal state."""
    async_task_id, expired_time = committed_expired_async_task
    running_task = RunningTask()
    running_task.async_id = async_task_id
    running_task.thread = mock.Mock()
    running_task.thread.is_alive.return_value = False
    running_task.result = "Completed result"
    AsyncManager.running_tasks = [running_task]

    completion_saved = threading.Event()
    allow_completion_commit = threading.Event()
    interruption_update_started = threading.Event()
    completion_done = threading.Event()
    interruption_done = threading.Event()
    errors: list[BaseException] = []
    interrupted_counts: list[int] = []
    original_save = Async.save

    def save_completion_before_commit(
        instance: Async, *args: object, **kwargs: object
    ) -> None:
        original_save(instance, *args, **kwargs)
        if (
            threading.current_thread() is completion_thread
            and instance.pk == async_task_id
            and instance.completed
        ):
            assert connection.in_atomic_block
            completion_saved.set()
            assert allow_completion_commit.wait(timeout=10)

    monkeypatch.setattr(Async, "save", save_completion_before_commit)

    def complete_task() -> None:
        AsyncManager._watchdog_loop()

    def interrupt_task() -> None:
        interrupted_counts.append(
            Async.objects.filter(
                pk=async_task_id,
                completed=False,
                updated_time__lte=expired_time,
            ).update(
                completed=True,
                was_error=True,
                completed_time=timezone.now(),
                updated_time=timezone.now(),
                _error=INTERRUPTED_TASK_ERROR,
            )
        )

    completion_thread = threading.Thread(
        target=_run_database_thread,
        args=(complete_task, errors, completion_done),
    )
    interruption_thread = threading.Thread(
        target=_run_database_thread,
        args=(interrupt_task, errors, interruption_done),
    )
    original_execute = CursorWrapper.execute

    def observe_interruption_update(
        cursor: CursorWrapper, sql: str, params: object = None
    ) -> object:
        if (
            threading.current_thread() is interruption_thread
            and sql.lstrip().upper().startswith("UPDATE")
        ):
            interruption_update_started.set()
        return original_execute(cursor, sql, params)

    monkeypatch.setattr(CursorWrapper, "execute", observe_interruption_update)

    with mock.patch.object(metrics.async_manager_running_tasks, "dec"):
        completion_thread.start()
        assert completion_saved.wait(timeout=10)
        interruption_thread.start()
        try:
            # The interruption update must wait for the completion's row lock.
            assert interruption_update_started.wait(timeout=10)
            assert not interruption_done.wait(timeout=0.1)
        finally:
            allow_completion_commit.set()
        completion_thread.join(timeout=10)
        interruption_thread.join(timeout=10)

    assert not completion_thread.is_alive()
    assert not interruption_thread.is_alive()
    assert errors == []
    assert interrupted_counts == [0]
    async_task = Async.objects.get(pk=async_task_id)
    assert async_task.completed is True
    assert async_task.was_error is False
    assert async_task.result == "Completed result"
    assert async_task._error is None
