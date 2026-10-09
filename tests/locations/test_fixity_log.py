import pathlib

import pytest
from django.core.management import call_command

from archivematica.storage_service.locations import models

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture
def fixity_log_fixtures(db: None) -> None:
    call_command(
        "loaddata",
        *[
            str(FIXTURES_DIR / name)
            for name in ["base.json", "package.json", "fixity_log.json"]
        ],
        verbosity=0,
    )


@pytest.fixture
def fixity_log(fixity_log_fixtures: None) -> models.FixityLog:
    return models.FixityLog.objects.all()[0]


def test_has_required_attributes(fixity_log: models.FixityLog) -> None:
    assert fixity_log.package
    assert not fixity_log.success
    assert fixity_log.error_details
    assert fixity_log.datetime_reported
