from collections.abc import Callable
from unittest import mock

import pytest
from django.test import Client
from django.urls import reverse

from archivematica.storage_service.locations import models
from archivematica.storage_service.locations import package_request
from archivematica.storage_service.locations import table_payloads

EventFactory = Callable[..., models.Event]


@pytest.fixture
def space() -> models.Space:
    return models.Space.objects.create(
        access_protocol=models.Space.LOCAL_FILESYSTEM,
        path="/var/archivematica",
        staging_path="/var/archivematica/staging",
    )


@pytest.fixture
def location(space: models.Space) -> models.Location:
    return models.Location.objects.create(
        space=space,
        purpose=models.Location.AIP_STORAGE,
        relative_path="aips",
    )


@pytest.fixture
def package(location: models.Location) -> models.Package:
    return models.Package.objects.create(
        current_location=location,
        current_path="example-aip.7z",
        package_type=models.Package.AIP,
        status=models.Package.UPLOADED,
    )


@pytest.fixture
def pipeline() -> models.Pipeline:
    return models.Pipeline.objects.create(description="Test pipeline")


@pytest.fixture
def event_factory(
    package: models.Package,
    pipeline: models.Pipeline,
) -> EventFactory:
    def _create_request_event(
        *,
        event_type: str = models.Event.DELETE,
        status: str = models.Event.SUBMITTED,
        event_reason: str = "delete requested",
    ) -> models.Event:
        return models.Event.objects.create(
            package=package,
            event_type=event_type,
            event_reason=event_reason,
            pipeline=pipeline,
            user_id=1,
            user_email="demo@example.com",
            status=status,
            status_reason="",
        )

    return _create_request_event


@pytest.fixture
def delete_request_event(event_factory: EventFactory) -> models.Event:
    return event_factory()


@pytest.fixture
def pending_delete_event(event_factory: EventFactory) -> models.Event:
    return event_factory(event_reason="pending delete")


@pytest.fixture
def closed_delete_event(event_factory: EventFactory) -> models.Event:
    return event_factory(
        status=models.Event.APPROVED,
        event_reason="closed delete",
    )


@pytest.fixture
def needs_reason_delete_event(event_factory: EventFactory) -> models.Event:
    return event_factory(event_reason="needs reason")


@pytest.mark.django_db
def test_package_delete_request_renders_vue_payloads(
    admin_client: Client,
    pending_delete_event: models.Event,
    closed_delete_event: models.Event,
) -> None:
    assert closed_delete_event.status == models.Event.APPROVED

    response = admin_client.get(reverse("locations:package_delete_request"))

    assert response.status_code == 200
    pending_payload = response.context["pending_requests_table_payload"]
    closed_payload = response.context["closed_requests_table_payload"]

    assert pending_payload["kind"] == "package-requests-pending"
    assert closed_payload["kind"] == "package-requests-closed"
    pending_row = next(
        row for row in pending_payload["rows"] if row["reason"] == "pending delete"
    )
    assert pending_row["actions"]["kind"] == "decision-form"
    assert pending_row["actions"]["eventId"] == pending_delete_event.id
    assert 'id="tables-package-requests-pending-payload"' in response.text
    assert 'id="tables-package-requests-closed-payload"' in response.text


@mock.patch(
    "archivematica.storage_service.locations.views.package_request.process_package_request_decision"
)
@pytest.mark.django_db
def test_package_delete_request_processes_targeted_event(
    process_package_request_decision: mock.Mock,
    admin_client: Client,
    delete_request_event: models.Event,
) -> None:
    process_package_request_decision.return_value = (
        package_request.PackageRequestProcessingResult(
            event=delete_request_event,
            decision=package_request.PackageRequestDecision.APPROVE,
            message=package_request.PackageRequestMessage(
                level="success",
                content="Request approved",
            ),
        )
    )

    response = admin_client.post(
        reverse("locations:package_delete_request"),
        {
            table_payloads.EVENT_ID_FIELD_NAME: str(delete_request_event.id),
            table_payloads.STATUS_REASON_FIELD_NAME: "Looks good",
            table_payloads.DECISION_FIELD_NAME: (
                package_request.PackageRequestDecision.APPROVE.value
            ),
        },
    )

    assert response.status_code == 302
    assert response["Location"] == reverse("locations:package_delete_request")
    process_package_request_decision.assert_called_once()
    args = process_package_request_decision.call_args.args
    kwargs = process_package_request_decision.call_args.kwargs
    assert args[1].id == delete_request_event.id
    assert args[2] == package_request.PackageRequestDecision.APPROVE
    assert kwargs["reason"] == "Looks good"


@pytest.mark.django_db
def test_package_delete_request_keeps_form_errors_on_targeted_row(
    admin_client: Client,
    needs_reason_delete_event: models.Event,
) -> None:
    response = admin_client.post(
        reverse("locations:package_delete_request"),
        {
            table_payloads.EVENT_ID_FIELD_NAME: str(needs_reason_delete_event.id),
            table_payloads.STATUS_REASON_FIELD_NAME: "",
            table_payloads.DECISION_FIELD_NAME: (
                package_request.PackageRequestDecision.APPROVE.value
            ),
        },
    )

    assert response.status_code == 200
    needs_reason_delete_event.refresh_from_db()
    assert needs_reason_delete_event.status == models.Event.SUBMITTED
    pending_payload = response.context["pending_requests_table_payload"]
    pending_row = next(
        row for row in pending_payload["rows"] if row["reason"] == "needs reason"
    )
    reason_errors = pending_row["actions"]["reasonErrors"]
    assert reason_errors
    assert "required" in reason_errors[0].lower()
