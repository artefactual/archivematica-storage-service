"""Run rsync commands with Storage Service failure boundaries.

The storage models build the rsync command line because they know the source,
destination, transport style, and permission flags needed for each move. This
module owns the process-running policy shared by those callers: bound captured
output, enforce a maximum wall-clock runtime, and clean up the whole process
group when rsync does not exit on its own.

Rsync also receives ``--timeout`` from callers using ``RSYNC_IO_TIMEOUT_SECONDS``.
That is rsync's idle I/O timeout, not a total runtime limit. The runner's
wall-clock timeout is a separate safety net so a transfer that keeps producing
some output cannot keep an API request or worker alive forever.
"""

from __future__ import annotations

import logging
import os
import selectors
import signal
import subprocess
import time
from collections.abc import Mapping
from collections.abc import Sequence
from typing import IO
from typing import TYPE_CHECKING
from typing import cast

if TYPE_CHECKING:
    from locations.models import StorageException

LOGGER = logging.getLogger(__name__)

__all__ = ("RSYNC_IO_TIMEOUT_SECONDS", "run_rsync")

# Fail rsync when it observes no I/O for this many seconds. This does not limit
# total transfer duration; large copies can run longer while making progress.
RSYNC_IO_TIMEOUT_SECONDS = 300

# Safety net for rsync processes that keep doing some I/O but never finish.
RSYNC_PROCESS_TIMEOUT_SECONDS = 86400

# Keep enough stderr/stdout for diagnosis without holding unbounded output.
RSYNC_OUTPUT_LIMIT_BYTES = 65536

# Give rsync a short window to handle SIGTERM before forcing SIGKILL.
RSYNC_TERMINATE_GRACE_SECONDS = 10


class _BoundedOutput:
    """Collect only the tail of process output for failure diagnostics."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.output = bytearray()
        self.truncated = False

    def append(self, chunk: bytes) -> None:
        """Append output while keeping the buffer within its byte limit."""
        self.output.extend(chunk)
        if len(self.output) > self.limit:
            del self.output[: len(self.output) - self.limit]
            self.truncated = True

    def text(self) -> str:
        """Return decoded buffered output, noting when earlier output was cut."""
        result = self.output.decode(errors="replace")
        if self.truncated:
            return f"[output truncated to last {self.limit} bytes]\n{result}"
        return result


def _storage_exception(message: str) -> StorageException:
    """Build StorageException lazily to avoid importing location models here."""
    from locations.models import StorageException

    return StorageException(message)


def _kill_process_group(process: subprocess.Popen[bytes]) -> None:
    """Terminate an rsync process group, escalating to SIGKILL if needed."""
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=RSYNC_TERMINATE_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            return
        process.wait()


def _drain_output(fileobj: IO[bytes], output: _BoundedOutput) -> bool:
    """Read currently available output and report whether EOF was reached."""
    while True:
        try:
            chunk = os.read(fileobj.fileno(), 8192)
        except BlockingIOError:
            return False
        if not chunk:
            return True
        output.append(chunk)


def _communicate_with_timeout(
    process: subprocess.Popen[bytes], timeout: float
) -> tuple[str, float]:
    """Collect process output while enforcing a wall-clock timeout."""
    output = _BoundedOutput(RSYNC_OUTPUT_LIMIT_BYTES)
    started = time.monotonic()

    if process.stdout is None:
        process.wait(timeout=timeout)
        return "", time.monotonic() - started

    os.set_blocking(process.stdout.fileno(), False)
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)

    try:
        while process.poll() is None:
            elapsed = time.monotonic() - started
            if elapsed >= timeout:
                _kill_process_group(process)
                _drain_output(process.stdout, output)
                raise TimeoutError(output.text())

            for key, _ in selector.select(timeout=min(1.0, timeout - elapsed)):
                fileobj = cast(IO[bytes], key.fileobj)
                if _drain_output(fileobj, output):
                    selector.unregister(fileobj)
                    remaining = timeout - (time.monotonic() - started)
                    try:
                        process.wait(timeout=max(0, remaining))
                    except subprocess.TimeoutExpired:
                        _kill_process_group(process)
                        raise TimeoutError(output.text())
                    return output.text(), time.monotonic() - started

        _drain_output(process.stdout, output)
        return output.text(), time.monotonic() - started
    finally:
        selector.close()


def run_rsync(
    command: Sequence[str],
    env: Mapping[str, str] | None = None,
    source: str | None = None,
    destination: str | None = None,
) -> None:
    """Run rsync with bounded output capture and process-group cleanup."""
    LOGGER.debug("rsync command: %s", command)
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        env=env,
    )

    try:
        stdout, _ = _communicate_with_timeout(process, RSYNC_PROCESS_TIMEOUT_SECONDS)
    except TimeoutError as err:
        message = (
            "Rsync exceeded maximum runtime of "
            f"{RSYNC_PROCESS_TIMEOUT_SECONDS} seconds while copying "
            f"{source or '<unknown source>'} to {destination or '<unknown destination>'}. "
            f"Last output: {err}"
        )
        LOGGER.warning(message)
        raise _storage_exception(message)

    if process.returncode != 0:
        message = (
            f"Rsync failed with status {process.returncode} while copying "
            f"{source or '<unknown source>'} to {destination or '<unknown destination>'}. "
            f"Last output: {stdout}"
        )
        LOGGER.warning(message)
        raise _storage_exception(message)
