import json
from unittest import mock

import pytest
from django.contrib.auth.models import AnonymousUser
from django.test import Client
from django.test import RequestFactory
from django.urls import reverse

from archivematica.storage_service.locations import models
from archivematica.storage_service.locations import package_request
from archivematica.storage_service.locations import table_payloads
from archivematica.storage_service.locations import views
from tests.factories import EventFactory


@pytest.fixture
def delete_request_event(
    make_event: EventFactory, package: models.Package, pipeline: models.Pipeline
) -> models.Event:
    """A pending request to delete the package."""
    return make_event(package, pipeline)


@pytest.mark.django_db
def test_package_delete_request_renders_vue_payloads(
    admin_client: Client,
    make_event: EventFactory,
    package: models.Package,
    pipeline: models.Pipeline,
    delete_request_event: models.Event,
) -> None:
    closed_delete_event = make_event(
        package, pipeline, status=models.Event.APPROVED, event_reason="closed delete"
    )
    assert closed_delete_event.status == models.Event.APPROVED

    response = admin_client.get(reverse("locations:package_delete_request"))

    assert response.status_code == 200
    pending_payload = response.context["pending_requests_table_payload"]
    closed_payload = response.context["closed_requests_table_payload"]

    assert pending_payload["kind"] == "package-requests-pending"
    assert closed_payload["kind"] == "package-requests-closed"
    pending_row = next(
        row
        for row in pending_payload["rows"]
        if row["reason"] == delete_request_event.event_reason
    )
    assert pending_row["actions"]["kind"] == "decision-form"
    assert pending_row["actions"]["eventId"] == delete_request_event.id
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
    delete_request_event: models.Event,
) -> None:
    response = admin_client.post(
        reverse("locations:package_delete_request"),
        {
            table_payloads.EVENT_ID_FIELD_NAME: str(delete_request_event.id),
            table_payloads.STATUS_REASON_FIELD_NAME: "",
            table_payloads.DECISION_FIELD_NAME: (
                package_request.PackageRequestDecision.APPROVE.value
            ),
        },
    )

    assert response.status_code == 200
    delete_request_event.refresh_from_db()
    assert delete_request_event.status == models.Event.SUBMITTED
    pending_payload = response.context["pending_requests_table_payload"]
    pending_row = next(
        row
        for row in pending_payload["rows"]
        if row["reason"] == delete_request_event.event_reason
    )
    reason_errors = pending_row["actions"]["reasonErrors"]
    assert reason_errors
    assert "required" in reason_errors[0].lower()


@pytest.fixture
def pipeline_package(
    package: models.Package, pipeline: models.Pipeline
) -> models.Package:
    """The package, which originates in the pipeline."""
    package.origin_pipeline = pipeline
    package.save(update_fields=["origin_pipeline"])

    return package


@mock.patch(
    "archivematica.storage_service.locations.views.signals.deletion_request.send"
)
@pytest.mark.django_db
def test_package_request_deletion_creates_event_from_request_user(
    deletion_request_send: mock.Mock,
    admin_client: Client,
    pipeline_package: models.Package,
    pipeline: models.Pipeline,
) -> None:
    package = pipeline_package

    response = admin_client.post(
        reverse("locations:package_request_deletion", args=[package.uuid])
    )

    assert response.status_code == 202
    assert "created successfully" in response.json()["message"].lower()

    request_event = models.Event.objects.get(
        package=package,
        event_type=models.Event.DELETE,
    )
    request_user = response.wsgi_request.user
    assert request_event.status == models.Event.SUBMITTED
    assert request_event.pipeline == pipeline
    assert request_event.user_id == request_user.id
    assert request_event.user_email == request_user.email
    assert (
        models.Package.objects.get(uuid=package.uuid).status == models.Package.DEL_REQ
    )
    deletion_request_send.assert_called_once()


@pytest.mark.django_db
def test_package_request_deletion_requires_authentication(
    rf: RequestFactory,
    pipeline_package: models.Package,
) -> None:
    request = rf.post(
        reverse("locations:package_request_deletion", args=[pipeline_package.uuid])
    )
    request.user = AnonymousUser()

    response = views.package_request_deletion(
        request=request,
        uuid=str(pipeline_package.uuid),
    )

    assert response.status_code == 403
    assert json.loads(response.content)["message"] == "Authentication is required."


@pytest.mark.django_db
def test_package_request_deletion_requires_change_package_permission(
    logged_in_client: Client,
    pipeline_package: models.Package,
) -> None:
    response = logged_in_client.post(
        reverse("locations:package_request_deletion", args=[pipeline_package.uuid])
    )

    assert response.status_code == 403
    assert (
        response.json()["message"]
        == "You do not have permission to request package deletion."
    )
    assert not models.Event.objects.filter(
        package=pipeline_package,
        event_type=models.Event.DELETE,
    ).exists()


@pytest.mark.django_db
def test_package_request_deletion_requires_origin_pipeline(
    admin_client: Client,
    package: models.Package,
) -> None:
    response = admin_client.post(
        reverse("locations:package_request_deletion", args=[package.uuid])
    )

    assert response.status_code == 400
    assert response.json()["message"] == "Package deletion request failed."
    assert not models.Event.objects.filter(
        package=package,
        event_type=models.Event.DELETE,
    ).exists()


@pytest.mark.django_db
def test_package_request_deletion_rejects_unsupported_package_type(
    admin_client: Client,
    pipeline_package: models.Package,
) -> None:
    pipeline_package.package_type = models.Package.DIP
    pipeline_package.save(update_fields=["package_type"])

    response = admin_client.post(
        reverse("locations:package_request_deletion", args=[pipeline_package.uuid])
    )

    assert response.status_code == 405
    assert response.json()["message"] == "Deletes not allowed on this package type."
    assert not models.Event.objects.filter(
        package=pipeline_package,
        event_type=models.Event.DELETE,
    ).exists()


@mock.patch(
    "archivematica.storage_service.locations.views.signals.deletion_request.send"
)
@pytest.mark.django_db
def test_package_request_deletion_returns_existing_request_message(
    deletion_request_send: mock.Mock,
    admin_client: Client,
    pipeline_package: models.Package,
) -> None:
    first_response = admin_client.post(
        reverse("locations:package_request_deletion", args=[pipeline_package.uuid])
    )
    second_response = admin_client.post(
        reverse("locations:package_request_deletion", args=[pipeline_package.uuid])
    )

    assert first_response.status_code == 202
    assert second_response.status_code == 200
    assert (
        second_response.json()["message"]
        == "A deletion request already exists for this AIP."
    )
    assert (
        models.Event.objects.filter(
            package=pipeline_package,
            event_type=models.Event.DELETE,
        ).count()
        == 1
    )
    deletion_request_send.assert_called_once()
