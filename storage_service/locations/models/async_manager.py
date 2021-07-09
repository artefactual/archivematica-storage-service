# Provides a mechanism for running background tasks (as threads) and keeping
# track of what's running, finished and failed.
#
# Information about each task is captured in an Async model, stored in the
# database.  It's assumed that whoever submitted each task will poll for
# completion in some fashion and consume results once the task completes.
#
# When running under gunicorn there may be multiple processes each with their
# own copy of AsyncManager, and that's OK: where it matters, we'll only interact
# with the tasks we're responsible for.  And when expiring old entries from the
# database, it doesn't matter if another AsyncManager does our job for us.

from __future__ import absolute_import
import datetime
import logging
import threading
import time
import traceback

from django.utils import timezone

from .asynchronous import Async  # noqa
from .. import metrics

LOGGER = logging.getLogger(__name__)

# How long we should wait for the watchdog thread to update a task before giving
# up on it.  This value determines how long a client will take to notice that
# their task has died.
TASK_TIMEOUT_SECONDS = datetime.timedelta(seconds=120)

# How long a task's results should persist (in the DB) after it finishes.
# Results will generally be consumed right away, so this number doesn't have to
# be huge.
MAX_TASK_AGE_SECONDS = datetime.timedelta(seconds=86400)

# Must be less than TASK_TIMEOUT_SECONDS!  Controls how often we wake up to
# check the status of our tasks.
WATCHDOG_POLL_SECONDS = 5


class RunningTask(object):
    def __init__(self):
        self.async_id = None
        self.thread = None
        self.was_error = False
        self.result = None
        self.error = None


class AsyncManager(object):
    running_tasks = []
    lock = threading.Lock()

    @staticmethod
    def _watchdog():
        while True:
            try:
                with metrics.watchdog_loop_timer():
                    AsyncManager._watchdog_loop()
            except Exception as e:
                LOGGER.warning("Failure in watchdog thread: %s", e, exc_info=True)

            time.sleep(WATCHDOG_POLL_SECONDS)

    @staticmethod
    def _watchdog_loop():
        """Wake up, expire old tasks, report completed tasks and give a sign of
        life for everything that's still running"""
        with AsyncManager.lock:
            # Delete any tasks that have expired before finishing
            # (i.e. interrupted due to a server restart)
            Async.objects.filter(
                completed=False,
                updated_time__lte=(timezone.now() - TASK_TIMEOUT_SECONDS),
            ).delete()

            # Delete any tasks whose results have expired
            Async.objects.filter(
                completed=True,
                completed_time__lte=(timezone.now() - MAX_TASK_AGE_SECONDS),
            ).delete()

            # Touch the update time of any running task.  If we crash/restart then these will expire.
            running_task_ids = [
                task.async_id
                for task in AsyncManager.running_tasks
                if task.thread.is_alive()
            ]
            Async.objects.filter(id__in=running_task_ids).update(
                updated_time=timezone.now()
            )

            # Find any tasks that have completed since we last looked
            completed_tasks = [
                task
                for task in AsyncManager.running_tasks
                if not task.thread.is_alive()
            ]

            for task in completed_tasks:
                AsyncManager.running_tasks.remove(task)
                metrics.async_manager_running_tasks.dec()

                try:
                    async_task = Async.objects.get(id=task.async_id)
                    async_task.completed = True
                    async_task.completed_time = timezone.now()
                    async_task.was_error = task.was_error

                    if task.was_error:
                        async_task.error = task.error
                    else:
                        async_task.result = task.result

                    async_task.save()
                except Async.DoesNotExist:
                    # This generally shouldn't happen, but if it does that
                    # would suggest that the watchdog had failed to update
                    # the running task for quite a long time.
                    LOGGER.debug(
                        "Watchdog attempted to update Async object %d but couldn't find it!"
                        % (task.async_id)
                    )

    @staticmethod
    def _wrap_task(task, task_fn):
        """Run a function, capturing its output/errors in `task`"""

        # Share stack of the caller with the task thread, excluding this func.
        stack = traceback.extract_stack()[:-2]
        message = "Caller's traceback (most recent call last):\n"
        message += "".join(traceback.format_list(stack))

        def wrapper(*args, **kwargs):
            value = error = None

            try:
                value = task_fn(*args, **kwargs)
            except Exception as e:
                error = e
                LOGGER.exception("Task threw an error: " + str(e) + "\n" + message)

            if error:
                task.was_error = True
                task.error = error
            else:
                task.result = value

        return wrapper

    # Run a task.  Return an async object to track it.
    @staticmethod
    def run_task(task_fn, *args, **kwargs):
        """Run `task_fn` in a separate thread.  Return an Async model that will
        hold its result upon completion."""
        async_task = Async()
        async_task.save()

        task = RunningTask()
        task.async_id = async_task.id
        task.thread = threading.Thread(
            target=AsyncManager._wrap_task(task, task_fn), args=args, kwargs=kwargs
        )

        # Note: Important to start the thread prior to adding it to our list of
        # running tasks.  Otherwise the is_alive check might fire before the
        # thread is started and mark it as completed prematurely.
        task.thread.start()

        with AsyncManager.lock:
            AsyncManager.running_tasks.append(task)
            metrics.async_manager_running_tasks.inc()

        return async_task


def start_async_manager():
    """Start our watchdog thread."""
    AsyncManager.watchdog = threading.Thread(target=AsyncManager._watchdog)
    AsyncManager.watchdog.daemon = True
    AsyncManager.watchdog.start()
