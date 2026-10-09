from unittest import mock

import pytest

from archivematica.storage_service.locations import models
from archivematica.storage_service.locations.models.lockssomatic import Lockssomatic
from tests.factories import SpaceFactory


@pytest.fixture
def lockssomatic(make_space: SpaceFactory) -> Lockssomatic:
    """A LOCKSS-O-Matic space keeping its packages locally."""
    space = make_space(
        access_protocol=models.Space.LOM,
        path="/tmp/",
    )

    return Lockssomatic.objects.create(
        space=space, sd_iri="http://localhost:9000/sd-uri", keep_local=True
    )


@mock.patch("httplib2.Http.request", side_effect=[(mock.Mock(status=200), "")])
def test_service_doc_bad_url(
    _connection: mock.MagicMock, lockssomatic: Lockssomatic
) -> None:
    lockssomatic.sd_iri = "http://does-not-exist.com"
    assert lockssomatic.update_service_document() is False
    assert lockssomatic.au_size == 0
    assert lockssomatic.collection_iri is None
    assert lockssomatic.checksum_type is None
