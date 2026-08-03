import time
from contextlib import contextmanager

from prometheus_client import Counter
from prometheus_client import Gauge

async_manager_running_tasks = Gauge(
    "async_manager_running_tasks",
    "Number of tasks being executed",
)

async_manager_watchdog_time_counter = Counter(
    "async_manager_watchdog_loop_duration_seconds",
    ("Total time taken by a watchdog loop iteration in seconds"),
)

async_manager_interrupted_tasks_counter = Counter(
    "async_manager_interrupted_tasks",
    "Number of tasks marked as interrupted after their heartbeat expired",
)


@contextmanager
def watchdog_loop_timer():
    start_time = time.time()
    try:
        yield
    finally:
        duration = time.time() - start_time
        async_manager_watchdog_time_counter.inc(duration)
