import os
from unittest import mock

import pytest
import rsync as rsync_module
from locations.models import StorageException


class FakeProcess:
    def __init__(self, stdout, returncode=None):
        self.stdout = stdout
        self.returncode = returncode
        self.pid = 999999

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.returncode = -15
        return self.returncode


def _pipe_with_output(output=b"", keep_writer_open=False):
    read_fd, write_fd = os.pipe()
    if output:
        os.write(write_fd, output)
    if not keep_writer_open:
        os.close(write_fd)
        write_fd = None
    return os.fdopen(read_fd, "rb", buffering=0), write_fd


@mock.patch("subprocess.Popen")
def test_run_rsync_raises_storage_exception_on_nonzero_exit(popen):
    stdout, _ = _pipe_with_output(b"rsync error")
    popen.return_value = FakeProcess(stdout, returncode=23)

    with pytest.raises(StorageException, match="Rsync failed with status 23"):
        rsync_module.run_rsync(["rsync"], source="source", destination="destination")


@mock.patch("subprocess.Popen")
def test_run_rsync_keeps_bounded_error_output(popen, monkeypatch):
    monkeypatch.setattr(rsync_module, "RSYNC_OUTPUT_LIMIT_BYTES", 10)
    stdout, _ = _pipe_with_output(b"0123456789abcdef")
    popen.return_value = FakeProcess(stdout, returncode=23)

    with pytest.raises(StorageException) as exc:
        rsync_module.run_rsync(["rsync"], source="source", destination="destination")

    message = str(exc.value)
    assert "output truncated to last 10 bytes" in message
    assert "6789abcdef" in message
    assert "012345" not in message


@mock.patch("rsync._kill_process_group")
@mock.patch("subprocess.Popen")
def test_run_rsync_times_out_and_kills_process(popen, kill_process_group, monkeypatch):
    monkeypatch.setattr(rsync_module, "RSYNC_PROCESS_TIMEOUT_SECONDS", 0.01)
    stdout, write_fd = _pipe_with_output(keep_writer_open=True)
    process = FakeProcess(stdout, returncode=None)
    popen.return_value = process

    with pytest.raises(StorageException, match="exceeded maximum runtime"):
        rsync_module.run_rsync(["rsync"], source="source", destination="destination")

    kill_process_group.assert_called_once_with(process)
    os.close(write_fd)
