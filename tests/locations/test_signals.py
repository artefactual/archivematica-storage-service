import datetime
import json
from unittest import mock

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from locations import models
from locations import signals


@pytest.mark.django_db
@mock.patch("locations.signals._notify_users")
def test_report_failed_fixity_check(_notify_users: mock.Mock):
    package = models.Package.objects.create(
        current_location=models.Location.objects.create(
            space=models.Space.objects.create()
        )
    )
    sender = None
    kwargs = {
        "uuid": str(package.uuid),
        "report": json.dumps(
            {
                "success": False,
                "message": "Incorrect package checksum",
                "failures": {"files": {"missing": [], "changed": [], "untracked": []}},
                "timestamp": None,
            }
        ),
    }
    expected_time = timezone.make_aware(datetime.datetime(2024, 5, 17, 11, 00))

    with mock.patch.object(
        timezone,
        "now",
        return_value=expected_time,
    ):
        signals.report_failed_fixity_check(sender, **kwargs)

    _notify_users.assert_called_once_with(
        f"Fixity check failed for package {package.uuid}",
        f"\n[{expected_time.strftime('%Y-%m-%d %H:%M:%S')}] A fixity check failed for the package with UUID {package.uuid}.\n",
        mock.ANY,
    )

    assert (
        models.FixityLog.objects.filter(
            package=package.uuid, success=False, datetime_reported=expected_time
        ).count()
        == 1
    )


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username="demo", email="demo@example.com", password="Abc.Def.1234"
    )


@pytest.mark.django_db
def test_notify_users(mailoutbox, user):
    subject = "foo"
    message = "bar"

    signals._notify_users(subject, message, [user])

    result = mailoutbox[0]
    assert list(result.to) == [user.email]
    assert result.subject == subject
    assert result.body == message
