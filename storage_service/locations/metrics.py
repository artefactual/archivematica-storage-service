import time
from contextlib import contextmanager

from prometheus_client import Counter, Gauge


async_manager_running_tasks = Gauge(
    "async_manager_running_tasks",
    "Number of tasks being executed",
)

async_manager_watchdog_time_counter = Counter(
    "async_manager_watchdog_loop_duration_seconds",
    ("Total time taken by a watchdog loop iteration in seconds"),
)


@contextmanager
def watchdog_loop_timer():
    start_time = time.time()
    try:
        yield
    finally:
        duration = time.time() - start_time
        async_manager_watchdog_time_counter.inc(duration)
