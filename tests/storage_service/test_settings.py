import os
import subprocess
import sys

import pytest

AUTHENTICATION_SWITCHES = (
    "SS_CAS_AUTHENTICATION",
    "SS_LDAP_AUTHENTICATION",
    "SS_OIDC_AUTHENTICATION",
    "SS_SHIBBOLETH_AUTHENTICATION",
)


def test_cas_and_shibboleth_cannot_be_enabled_together() -> None:
    """The settings refuse CAS together with another single sign-on method."""
    env = {
        **os.environ,
        "SS_SHIBBOLETH_AUTHENTICATION": "true",
        "SS_CAS_AUTHENTICATION": "true",
    }

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import archivematica.storage_service.storage_service.settings.base",
        ],
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "CAS authentication is not supported in tandem" in result.stderr


@pytest.mark.parametrize(
    "variable,setting",
    [
        ("AUTH_CAS_CHECK_ADMIN_ATTRIBUTES", "CAS_CHECK_ADMIN_ATTRIBUTES"),
        ("AUTH_CAS_AUTOCONFIGURE_EMAIL", "CAS_AUTOCONFIGURE_EMAIL"),
    ],
)
@pytest.mark.parametrize(
    "value,expected",
    [
        ("true", True),
        ("1", True),
        ("false", False),
        ("0", False),
        (None, False),
    ],
)
def test_cas_switches_are_parsed_as_booleans(
    variable: str, setting: str, value: str | None, expected: bool
) -> None:
    """The CAS switches are booleans, so "false" does not turn them on."""
    # Start from the process environment without any single sign-on switch,
    # so the test does not depend on the method the test run itself uses.
    env = {
        name: val
        for name, val in os.environ.items()
        if name != variable and name not in AUTHENTICATION_SWITCHES
    }
    env["SS_CAS_AUTHENTICATION"] = "true"
    if value is not None:
        env[variable] = value

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from archivematica.storage_service.storage_service.settings import base;"
            f" print(base.{setting})",
        ],
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(expected)
