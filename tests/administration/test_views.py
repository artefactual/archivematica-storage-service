import subprocess

import pytest
from administration.views import get_git_commit


@pytest.mark.parametrize(
    "check_output,expected_result",
    [
        (
            b"d9c93f388a770287cf6337d4f9bcbbe60c25fdb8\n",
            "d9c93f388a770287cf6337d4f9bcbbe60c25fdb8",
        ),
        (subprocess.CalledProcessError(128, "git", "error"), None),
    ],
    ids=["success", "error"],
)
def test_get_git_commit(check_output, expected_result, mocker):
    mocker.patch("subprocess.check_output", side_effect=[check_output])

    assert get_git_commit() == expected_result
