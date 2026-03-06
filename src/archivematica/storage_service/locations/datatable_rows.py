from typing import TypedDict
from urllib.parse import urlencode

from django.template.defaultfilters import filesizeformat
from django.urls import reverse
from django.utils import formats
from django.utils.translation import gettext as _

from archivematica.storage_service.locations.models import FixityLog
from archivematica.storage_service.locations.models import Package


class LinkCell(TypedDict):
    text: str
    href: str | None


class StatusCell(TypedDict):
    text: str
    update_href: str | None


class FixityStatusCell(TypedDict):
    text: str
    href: str


class RequestDeleteAction(TypedDict):
    package_type: str
    package_uuid: str
    pipeline_uuid: str


class DirectDeleteAction(TypedDict):
    action_url: str
    csrf_token: str
    modal_id: str
    modal_label_id: str
    modal_title: str
    prompt_text: str
    close_label: str
    confirm_label: str


class ActionsCell(TypedDict):
    pointer_file_href: str | None
    download_href: str | None
    reingest_href: str | None
    request_delete: RequestDeleteAction | None
    direct_delete: DirectDeleteAction | None


class PackageRowPayload(TypedDict):
    uuid: str
    origin_pipeline: LinkCell
    current_location: LinkCell
    size: str
    package_type: str
    replica_of: str
    status: StatusCell
    stored: str
    fixity_date: str
    fixity_status: FixityStatusCell
    actions: ActionsCell


class FixityLogRowPayload(TypedDict):
    date: str
    error: str


def _localize_value(value: object | None) -> str:
    if value is None:
        return ""
    return str(formats.localize(value))


def _build_next_url(base_url: str, next_path: str) -> str:
    return f"{base_url}?{urlencode({'next': next_path})}"


def _fixity_status_label(success: bool | None) -> str:
    if success is True:
        return _("Success")
    if success is False:
        return _("Failed")
    return ""


def build_package_row_payload(
    package: Package,
    *,
    redirect_path: str,
    csrf_token: str,
    can_change_package: bool,
    can_delete_package: bool,
) -> PackageRowPayload:
    package_uuid = str(package.uuid)
    origin_pipeline_cell: LinkCell = {"text": _("None"), "href": None}
    origin_pipeline_uuid = ""

    if package.origin_pipeline is not None:
        origin_pipeline_uuid = str(package.origin_pipeline.uuid)
        origin_pipeline_cell = {
            "text": str(package.origin_pipeline),
            "href": reverse(
                "locations:pipeline_detail", args=[package.origin_pipeline.uuid]
            ),
        }

    download_href = None
    if package.status != package.DELETED:
        download_href = reverse("download_request", args=["v2", "file", package.uuid])

    status_update_href = None
    if can_change_package and package.status not in (package.DELETED, package.FAIL):
        status_update_href = _build_next_url(
            reverse("locations:package_update_status", args=[package.uuid]),
            redirect_path,
        )

    reingest_href = None
    if (
        can_change_package
        and package.package_type in package.PACKAGE_TYPE_CAN_REINGEST
        and not package.replicated_package
    ):
        reingest_href = _build_next_url(
            reverse("locations:aip_reingest", args=[package.uuid]),
            redirect_path,
        )

    request_delete_action = None
    if package.package_type in package.PACKAGE_TYPE_CAN_DELETE:
        request_delete_action = {
            "package_type": package.package_type,
            "package_uuid": package_uuid,
            "pipeline_uuid": origin_pipeline_uuid,
        }

    direct_delete_action = None
    if (
        can_delete_package
        and package.package_type in package.PACKAGE_TYPE_CAN_DELETE_DIRECTLY
        and package.status != package.DELETED
    ):
        modal_id = f"confirm-delete-{package_uuid}"
        direct_delete_action = {
            "action_url": reverse("locations:package_delete", args=[package.uuid]),
            "csrf_token": csrf_token,
            "modal_id": modal_id,
            "modal_label_id": f"confirm-delete-title-{package_uuid}",
            "modal_title": _("Delete package"),
            "prompt_text": _("Are you sure you want to delete {item}?").format(
                item=f"{package.package_type} {package_uuid}"
            ),
            "close_label": _("Close"),
            "confirm_label": _("Delete"),
        }

    pointer_file_href = None
    if package.pointer_file_location is not None:
        pointer_file_href = reverse(
            "pointer_file_request",
            args=["v2", "file", package.uuid],
        )

    return {
        "uuid": package_uuid,
        "origin_pipeline": origin_pipeline_cell,
        "current_location": {"text": package.full_path, "href": download_href},
        "size": filesizeformat(package.size),
        "package_type": package.get_package_type_display(),
        "replica_of": (
            str(package.replicated_package.uuid) if package.replicated_package else ""
        ),
        "status": {
            "text": package.get_status_display(),
            "update_href": status_update_href,
        },
        "stored": _localize_value(package.stored_date),
        "fixity_date": _localize_value(package.latest_fixity_check_datetime),
        "fixity_status": {
            "text": _fixity_status_label(package.latest_fixity_check_result),
            "href": reverse("locations:package_fixity", args=[package.uuid]),
        },
        "actions": {
            "pointer_file_href": pointer_file_href,
            "download_href": download_href,
            "reingest_href": reingest_href,
            "request_delete": request_delete_action,
            "direct_delete": direct_delete_action,
        },
    }


def build_fixity_log_row_payload(fixity_log: FixityLog) -> FixityLogRowPayload:
    return {
        "date": _localize_value(fixity_log.datetime_reported),
        "error": fixity_log.error_details or "",
    }
