from __future__ import absolute_import, unicode_literals

import pytest

from locations.models import Callback


@pytest.mark.django_db
def test_package_callback_with_file_uri(tmp_path):
    receipt_path = tmp_path / "12345.xml"
    callback = Callback.objects.create(
        uuid="702eeb47-4ce7-4745-89c0-b230f41b5d9a",
        event="post_store",
        method="get",
        uri=receipt_path.as_uri(),
    )

    assert not receipt_path.exists()

    callback.execute()

    assert receipt_path.exists()
