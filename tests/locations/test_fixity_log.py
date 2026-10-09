import pytest

from archivematica.storage_service.locations import models


@pytest.fixture
def fixity_log(fixity_log_rows: list[models.FixityLog]) -> models.FixityLog:
    """The first fixity check of the transfer, a failed one."""
    return fixity_log_rows[0]


def test_has_required_attributes(fixity_log: models.FixityLog) -> None:
    assert fixity_log.package
    assert not fixity_log.success
    assert fixity_log.error_details
    assert fixity_log.datetime_reported
