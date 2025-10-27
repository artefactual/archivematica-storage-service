"""Helpers that encapsulate the package request workflow.

This module defines configuration classes and helper functions that manage
package request events (such as delete and recover operations) in the Storage
Service. Views and API endpoints rely on these helpers to validate requests,
persist workflow state, execute package operations, and send remote
notifications to external systems.
"""

import json
import logging
import os
import pprint
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any
from typing import Literal
from typing import Optional
from typing import Union

import requests
from django.utils.translation import gettext as _
from django_stubs_ext import StrOrPromise

from archivematica.storage_service.common import utils
from archivematica.storage_service.locations.models import Event
from archivematica.storage_service.locations.models import Package
from archivematica.storage_service.locations.models import Pipeline
from archivematica.storage_service.locations.models import StorageException
from archivematica.storage_service.locations.models.location import Location
from archivematica.storage_service.locations.models.location import LocationPipeline

LOGGER = logging.getLogger(__name__)


class PackageRequestHandlerConfig:
    event_type: Optional[str] = None  # Event type being handled.
    pending_status: Optional[str] = (
        None  # Package status while request is pending review.
    )
    approved_status: Optional[str] = None  # Package status after approval.
    reject_message: Union[StrOrPromise, str] = ""  # Message returned if not approved.
    execution_success_message: Union[StrOrPromise, str] = (
        ""  # Message returned if execution succeeds.
    )
    execution_fail_message: Union[StrOrPromise, str] = (
        ""  # Message returned if execution fails.
    )

    def execution_logic(self, package: Package) -> tuple[bool, StrOrPromise]:
        raise NotImplementedError("Implement in subclasses")

    @property
    def request_description(self) -> str:
        """Human-readable description of the configured event type."""

        if self.event_type is None:
            raise ValueError("Package request event type is not configured.")
        return self.event_type.replace("_", " ").lower()


class PackageDeletionRequestHandlerConfig(PackageRequestHandlerConfig):
    event_type = Event.DELETE
    pending_status = Package.DEL_REQ
    approved_status = Package.DELETED
    reject_message = _("Request rejected, package still stored.")
    execution_success_message = _("Package deleted successfully.")
    execution_fail_message = _("Package was not deleted from disk correctly")

    def execution_logic(self, package: Package) -> tuple[bool, StrOrPromise]:
        success, error = package.delete_from_storage()

        return success, str(error) if error is not None else ""


class PackageRecoveryRequestHandlerConfig(PackageRequestHandlerConfig):
    event_type = Event.RECOVER
    pending_status = Package.RECOVER_REQ
    approved_status = Package.UPLOADED
    reject_message = _("AIP restore rejected.")
    execution_success_message = _("AIP restored.")
    execution_fail_message = _("AIP restore failed")

    def execution_logic(self, aip: Package) -> tuple[bool, StrOrPromise]:
        recover_location = LocationPipeline.objects.get(
            pipeline=aip.origin_pipeline, location__purpose=Location.AIP_RECOVERY
        ).location

        try:
            (success, failures, message) = aip.recover_aip(
                recover_location, os.path.basename(aip.current_path)
            )
        except StorageException:
            recover_path = os.path.join(
                recover_location.full_path, os.path.basename(aip.full_path)
            )
            message = _("error accessing restore files at %(path)s") % {
                "path": recover_path
            }
            success = False

        return (bool(success), message)


class PackageRequestDecision(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"

    @classmethod
    def from_value(cls, value: Any) -> "PackageRequestDecision":
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            try:
                return cls(value.strip().lower())
            except ValueError as error:
                raise ValueError(f"Unsupported decision '{value}'.") from error
        raise ValueError(f"Unsupported decision '{value}'.")


# Level tags are used with Django's messages framework.
PackageRequestMessageLevel = Literal["success", "error"]


@dataclass
class PackageRequestMessage:
    level: PackageRequestMessageLevel
    content: StrOrPromise
    detail: Optional[StrOrPromise] = None


@dataclass
class PackageRequestProcessingResult:
    event: Event
    decision: PackageRequestDecision
    message: PackageRequestMessage


@dataclass
class PackageRequestSubmissionResult:
    event: Optional[Event]
    created: bool


class PackageRequestValidationError(ValueError):
    """Raised when package request input cannot be validated."""

    def __init__(self, message: StrOrPromise):
        super().__init__(str(message))
        self.message: StrOrPromise = message


def parse_decision_and_reason(
    decision_value: Any,
    reason_value: Any,
) -> tuple[PackageRequestDecision, str]:
    """Return a validated decision and non-empty reason string.

    The decision must be one of the supported values. The reason must be a
    non-empty string after trimming whitespace.
    """

    try:
        decision = PackageRequestDecision.from_value(decision_value)
    except ValueError as error:
        raise PackageRequestValidationError(
            _("Decision must be either '%(approve)s' or '%(reject)s'.")
            % {
                "approve": PackageRequestDecision.APPROVE.value,
                "reject": PackageRequestDecision.REJECT.value,
            }
        ) from error

    reason_required_message = _("A reason is required.")

    if not isinstance(reason_value, str) or not (reason := reason_value.strip()):
        raise PackageRequestValidationError(reason_required_message)

    return decision, reason


def submit_package_request_event(
    config: PackageRequestHandlerConfig,
    package: Package,
    *,
    request_info: Mapping[str, Any],
) -> PackageRequestSubmissionResult:
    """Create a pending package request event if one does not exist already."""

    LOGGER.info(
        "Package event: '%s' requested, with package status: '%s'",
        config.event_type,
        config.pending_status,
    )
    LOGGER.debug(pprint.pformat(dict(request_info)))

    if config.event_type is None:
        raise ValueError("Package request event type is not configured.")

    existing_request_exists = Event.objects.filter(
        package=package, event_type=config.event_type, status=Event.SUBMITTED
    ).exists()
    if existing_request_exists:
        return PackageRequestSubmissionResult(event=None, created=False)

    original_status = package.status if config.pending_status is not None else None

    pipeline_value = request_info["pipeline"]
    if isinstance(pipeline_value, Pipeline):
        pipeline = pipeline_value
    else:
        pipeline = Pipeline.objects.get(uuid=pipeline_value)

    request_event = Event(
        package=package,
        event_type=config.event_type,
        status=Event.SUBMITTED,
        event_reason=request_info["event_reason"],
        pipeline=pipeline,
        user_id=request_info["user_id"],
        user_email=request_info["user_email"],
        store_data=original_status,
    )

    if config.pending_status is not None:
        package.status = config.pending_status
        package.save(update_fields=["status"])

    request_event.save()

    return PackageRequestSubmissionResult(event=request_event, created=True)


def handle_remote_result_notification(
    config: PackageRequestHandlerConfig, event: Event, success: bool
) -> str:
    if config.event_type is None:
        raise ValueError("Package request event type is not configured.")

    response_message = ""

    # The setting name is determined using the event type.
    setting_prefix = f"{config.event_type.lower()}_request_notification"
    request_notification_url = utils.get_setting(f"{setting_prefix}_url")

    # If a notification is configured, attempt to send it.
    if request_notification_url is not None:
        headers = {"Content-type": "application/json"}

        # The reported status may be approved even if the execution failed.
        if success:
            status_to_report = event.status
        else:
            if event.status == Event.REJECTED:
                status_to_report = event.status
            else:
                # Report a failed approval as "APPROVE (failed)" so downstream
                # consumers see the same status text while the event remains in
                # SUBMIT.
                status_to_report = f"{Event.APPROVED} (failed)"

        # Serialize the payload.
        payload = json.dumps(
            {
                "event_id": event.id,
                "message": f"{status_to_report}: {event.status_reason}",
                "success": success,
            }
        )

        # Specify basic authentication if it is configured.
        request_notification_auth_username = utils.get_setting(
            f"{setting_prefix}_auth_username"
        )
        request_notification_auth_password = utils.get_setting(
            f"{setting_prefix}_auth_password"
        )

        if request_notification_auth_username is not None:
            auth = requests.auth.HTTPBasicAuth(
                request_notification_auth_username, request_notification_auth_password
            )
        else:
            auth = None

        # Make the request and capture any message returned by the notification
        # service.
        try:
            notification_response = requests.post(
                request_notification_url, auth=auth, data=payload, headers=headers
            )
        except requests.RequestException as exc:
            LOGGER.exception(
                "Notification request for event %s (%s) to %s failed.",
                event.id,
                config.event_type,
                request_notification_url,
            )
            return _("Notification request failed: %(error)s") % {"error": exc}

        try:
            response_data = json.loads(notification_response.content)
        except ValueError:
            return response_message

        message = response_data.get("message")
        if message:
            response_message = str(message)

    return response_message


def process_package_request_decision(
    config: PackageRequestHandlerConfig,
    event: Event,
    decision: PackageRequestDecision,
    *,
    reason: Optional[StrOrPromise] = None,
    admin: Optional[Any] = None,
) -> PackageRequestProcessingResult:
    """Apply an approval or rejection decision to a package request event.

    This helper centralizes the workflow previously embedded in the view so the
    same business logic can be leveraged programmatically outside of Django's
    request/response cycle.
    """

    decision_value = PackageRequestDecision.from_value(decision)

    result_message: Optional[PackageRequestMessage] = None
    execution_succeeded: Optional[bool] = None

    status_reason = str(reason) if reason is not None else None

    event.status_reason = status_reason
    if admin is not None:
        event.admin_id = admin

    if decision_value is PackageRequestDecision.REJECT:
        event.status = Event.REJECTED
        # The request is rejected, so the package status is reset to the stored
        # value.
        stored_status = event.store_data
        if stored_status is not None:
            event.package.status = stored_status
        notification_message = handle_remote_result_notification(config, event, False)
        reject_message = config.reject_message
        if notification_message:
            reject_message = f"{reject_message} {notification_message}"
        result_message = PackageRequestMessage(level="success", content=reject_message)
    else:
        execution_succeeded, err_msg = config.execution_logic(event.package)
        if not execution_succeeded:
            error_message = "{}: {}. {}".format(
                config.execution_fail_message,
                err_msg,
                _("Please contact an administrator or see logs for details."),
            )
            notification_message = handle_remote_result_notification(
                config, event, False
            )
            if notification_message:
                error_message = f"{error_message} {notification_message}"
            result_message = PackageRequestMessage(level="error", content=error_message)
        else:
            # The package execution succeeded, so update the status per the
            # event configuration.
            event.status = Event.APPROVED
            if config.approved_status is not None:
                event.package.status = config.approved_status
            approval_message = _("Request approved: %(message)s") % {
                "message": config.execution_success_message
            }
            detail_message: Optional[StrOrPromise] = None
            if err_msg:
                err_text = str(err_msg).strip()
                if err_text:
                    # The deletion succeeded, but the storage backend also
                    # returned a warning (for example from LOCKSS).
                    detail_message = err_text
            notification_message = handle_remote_result_notification(
                config, event, True
            )
            if notification_message:
                approval_message = f"{approval_message} {notification_message}"
            result_message = PackageRequestMessage(
                level="success", content=approval_message, detail=detail_message
            )

    event.save()
    event.package.save()

    if result_message is None:
        raise ValueError("Package request processing did not produce a message.")

    return PackageRequestProcessingResult(
        event=event, decision=decision_value, message=result_message
    )
