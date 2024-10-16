import subprocess
from unittest import mock

import pytest
from administration.views import get_git_commit
from django.urls import reverse


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


@mock.patch("gnupg.GPG.list_keys")
def test_deleting_key_from_detail_view_redirects_to_key_list(list_keys, admin_client):
    key_fingerprint = "3173C7395C551A6647656A5065C0718327F7B2C7"
    list_keys.return_value = mock.Mock(
        key_map={
            key_fingerprint: {
                "type": "sec",
                "trust": "",
                "length": "4096",
                "algo": "1",
                "keyid": "65C0718327F7B2C7",
                "date": "1729098435",
                "expires": "",
                "dummy": "",
                "ownertrust": "",
                "sig": "",
                "cap": "",
                "issuer": "",
                "flag": "",
                "token": "",
                "hash": "",
                "curve": "unavailable",
                "compliance": "unavailable",
                "updated": "unavailable",
                "origin": "unavailable",
                "keygrip": "unavailable",
                "uids": [
                    "Archivematica Storage Service GPG Key <unspecified@fcaf73663319>"
                ],
                "sigs": [],
                "subkeys": [],
                "fingerprint": key_fingerprint,
            },
        }
    )
    kwargs = {"key_fingerprint": key_fingerprint}
    delete_url = reverse("administration:key_delete", kwargs=kwargs)
    next_url = reverse("administration:key_list")

    response = admin_client.get(
        reverse(
            "administration:key_detail",
            kwargs=kwargs,
        )
    )
    assert response.status_code == 200

    assert (
        f'<a href="{delete_url}?next={next_url}">Delete</a>'
        in response.content.decode()
    )
