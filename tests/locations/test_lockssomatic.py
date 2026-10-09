import pathlib
from unittest import mock

import pytest
from django.core.management import call_command

from archivematica.storage_service.locations.models.lockssomatic import Lockssomatic

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture
def lockssomatic_fixtures(db: None) -> None:
    call_command(
        "loaddata",
        *[str(FIXTURES_DIR / name) for name in ["base.json", "lockssomatic.json"]],
        verbosity=0,
    )


@pytest.fixture
def lockssomatic(lockssomatic_fixtures: None) -> Lockssomatic:
    return Lockssomatic.objects.all()[0]


@mock.patch("httplib2.Http.request", side_effect=[(mock.Mock(status=200), "")])
def test_service_doc_bad_url(
    _connection: mock.MagicMock, lockssomatic: Lockssomatic
) -> None:
    lockssomatic.sd_iri = "http://does-not-exist.com"
    assert lockssomatic.update_service_document() is False
    assert lockssomatic.au_size == 0
    assert lockssomatic.collection_iri is None
    assert lockssomatic.checksum_type is None
