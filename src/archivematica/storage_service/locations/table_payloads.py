from collections.abc import Iterable
from typing import Any
from typing import TypedDict
from urllib.parse import urlencode

from django.http import HttpRequest
from django.urls import reverse
from django.utils.formats import localize
from django.utils.text import Truncator
from django.utils.translation import gettext as _

from archivematica.storage_service.common import table_payloads
from archivematica.storage_service.locations import package_request
from archivematica.storage_service.locations.models import Callback
from archivematica.storage_service.locations.models import Event
from archivematica.storage_service.locations.models import Location
from archivematica.storage_service.locations.models import Pipeline

EVENT_ID_FIELD_NAME = table_payloads.DECISION_FORM_EVENT_ID_NAME
STATUS_REASON_FIELD_NAME = table_payloads.DECISION_FORM_REASON_NAME
DECISION_FIELD_NAME = table_payloads.DECISION_FORM_DECISION_NAME
APPROVE_DECISION_VALUE = package_request.PackageRequestDecision.APPROVE.value
REJECT_DECISION_VALUE = package_request.PackageRequestDecision.REJECT.value


class DecisionFormState(TypedDict, total=False):
    reason_value: str
    reason_errors: list[str]


def _server_table_ui(
    *,
    endpoint: str,
    default_sort_column_key: str,
    default_sort_direction: str = "asc",
    filters: dict[str, str] | None = None,
) -> dict[str, Any]:
    ui: dict[str, Any] = {
        "server": {
            "mode": "server-datatables-v1",
            "endpoint": endpoint,
            "defaultSort": {
                "columnKey": default_sort_column_key,
                "direction": default_sort_direction,
            },
        }
    }
    if filters:
        ui["server"]["filters"] = filters
    return ui


def _enabled_label(is_enabled: bool) -> str:
    return _("Enabled") if is_enabled else _("Disabled")


def _toggle_label(is_enabled: bool) -> str:
    return _("Disable") if is_enabled else _("Enable")


def _location_detail_link(location: Location) -> str:
    return reverse("locations:location_detail", args=[location.uuid])


def _event_user_label(event: Event) -> str:
    return _("%(email)s (ID: %(user_id)s)") % {
        "email": event.user_email,
        "user_id": event.user_id,
    }


def pipeline_list_payload(
    request: HttpRequest, pipelines: Iterable[Pipeline]
) -> table_payloads.TablePayload:
    can_change = request.user.has_perm("locations.change_pipeline")
    can_delete = request.user.has_perm("locations.delete_pipeline")
    include_actions = can_change or can_delete
    next_query = urlencode({"next": request.path})

    rows: list[table_payloads.PayloadRow] = []
    for pipeline in pipelines:
        actions: list[table_payloads.ActionPayload] = []
        if can_change:
            actions.append(
                table_payloads.action(
                    _("Edit"),
                    reverse("locations:pipeline_edit", args=[pipeline.uuid]),
                )
            )
            actions.append(
                table_payloads.action(
                    _toggle_label(pipeline.enabled),
                    f"{reverse('locations:pipeline_switch_enabled', args=[pipeline.uuid])}?{next_query}",
                )
            )
        if can_delete:
            actions.append(
                table_payloads.action(
                    _("Delete"),
                    f"{reverse('locations:pipeline_delete', args=[pipeline.uuid])}?{next_query}",
                )
            )

        row: table_payloads.PayloadRow = {
            "uuid": table_payloads.link(
                str(pipeline.uuid),
                reverse("locations:pipeline_detail", args=[pipeline.uuid]),
            ),
            "description": pipeline.description,
            "enabled": _enabled_label(pipeline.enabled),
        }
        if include_actions:
            row["actions"] = actions
        rows.append(row)

    columns: list[table_payloads.ColumnPayload] = [
        {"key": "uuid", "label": _("UUID")},
        {"key": "description", "label": _("Description")},
        {"key": "enabled", "label": _("Enabled")},
    ]
    if include_actions:
        columns.append({"key": "actions", "label": _("Edit"), "sortable": False})

    return table_payloads.table_payload(
        "pipelines-list",
        columns=columns,
        rows=rows,
    )


def locations_list_payload(
    request: HttpRequest,
    locations: Iterable[Location],
    *,
    include_pipeline: bool = True,
    include_space: bool = True,
) -> table_payloads.TablePayload:
    can_change = request.user.has_perm("locations.change_location")
    can_delete = request.user.has_perm("locations.delete_location")
    include_actions = can_change or can_delete
    next_query = urlencode({"next": request.path})

    rows: list[table_payloads.PayloadRow] = []
    for location in locations:
        purpose = location.get_purpose_display()
        if location.purpose == Location.REPLICATOR:
            masters = [
                table_payloads.link_item(
                    str(master.uuid), _location_detail_link(master)
                )
                for master in location.masters.all()
            ]
            purpose_cell: str | table_payloads.TextWithLinksPayload
            if masters:
                purpose_cell = table_payloads.text_with_links(
                    purpose,
                    masters,
                    connector=_("of"),
                )
            else:
                purpose_cell = purpose
        else:
            purpose_cell = purpose

        actions: list[table_payloads.ActionPayload] = []
        if can_change:
            actions.append(
                table_payloads.action(
                    _("Edit"),
                    reverse(
                        "locations:location_edit",
                        args=[location.space.uuid, location.uuid],
                    ),
                )
            )
            actions.append(
                table_payloads.action(
                    _toggle_label(location.enabled),
                    f"{reverse('locations:location_switch_enabled', args=[location.uuid])}?{next_query}",
                )
            )
        if can_delete:
            actions.append(
                table_payloads.action(
                    _("Delete"),
                    f"{reverse('locations:location_delete', args=[location.uuid])}?{next_query}",
                )
            )

        row: table_payloads.PayloadRow = {
            "purpose": purpose_cell,
            "path": location.full_path,
            "description": table_payloads.link(
                location.description or _("None"),
                _location_detail_link(location),
            ),
            "uuid": str(location.uuid),
            "usage": f"{location.used}B / {location.quota or _('unlimited')}",
            "enabled": _enabled_label(location.enabled),
            "default": _("Yes") if location.default else _("No"),
        }

        if include_pipeline:
            pipeline_links = [
                table_payloads.link_item(
                    pipeline.description,
                    reverse("locations:pipeline_detail", args=[pipeline.uuid]),
                )
                for pipeline in location.pipeline.all()
            ]
            row["pipeline"] = table_payloads.link_list(
                pipeline_links,
                empty_text=_("No pipelines"),
            )

        if include_space:
            space_uuid = str(location.space.uuid)
            row["space"] = table_payloads.link(
                Truncator(space_uuid).chars(11),
                reverse("locations:space_detail", args=[location.space.uuid]),
            )

        if include_actions:
            row["actions"] = actions
        rows.append(row)

    columns: list[table_payloads.ColumnPayload] = [
        {"key": "purpose", "label": _("Purpose")},
    ]
    if include_pipeline:
        columns.append({"key": "pipeline", "label": _("Pipeline")})
    columns.extend(
        [
            {"key": "path", "label": _("Path")},
            {"key": "description", "label": _("Description")},
        ]
    )
    if include_space:
        columns.append({"key": "space", "label": _("Space")})
    columns.extend(
        [
            {"key": "uuid", "label": _("UUID")},
            {"key": "usage", "label": _("Usage")},
            {"key": "enabled", "label": _("Enabled")},
            {"key": "default", "label": _("Default")},
        ]
    )
    if include_actions:
        columns.append({"key": "actions", "label": _("Actions"), "sortable": False})

    return table_payloads.table_payload(
        "locations-list",
        columns=columns,
        rows=rows,
    )


def callback_list_payload(
    request: HttpRequest, callbacks: Iterable[Callback]
) -> table_payloads.TablePayload:
    next_query = urlencode({"next": request.path})
    rows: list[table_payloads.PayloadRow] = []

    for callback in callbacks:
        rows.append(
            {
                "event": callback.get_event_display(),
                "uri": callback.uri,
                "method": callback.method,
                "expectedResponse": callback.expected_status,
                "uuid": str(callback.uuid),
                "enabled": _enabled_label(callback.enabled),
                "actions": [
                    table_payloads.action(
                        _("Edit"),
                        reverse("locations:callback_edit", args=[callback.uuid]),
                    ),
                    table_payloads.action(
                        _toggle_label(callback.enabled),
                        f"{reverse('locations:callback_switch_enabled', args=[callback.uuid])}?{next_query}",
                    ),
                    table_payloads.action(
                        _("Delete"),
                        f"{reverse('locations:callback_delete', args=[callback.uuid])}?{next_query}",
                    ),
                ],
            }
        )

    return table_payloads.table_payload(
        "callbacks-list",
        columns=[
            {"key": "event", "label": _("Event")},
            {"key": "uri", "label": _("URI")},
            {"key": "method", "label": _("Method")},
            {"key": "expectedResponse", "label": _("Expected response")},
            {"key": "uuid", "label": _("UUID")},
            {"key": "enabled", "label": _("Enabled")},
            {"key": "actions", "label": _("Actions"), "sortable": False},
        ],
        rows=rows,
    )


def packages_server_payload(
    *,
    endpoint: str,
    location_uuid: str | None = None,
) -> table_payloads.TablePayload:
    filters: dict[str, str] = {}
    if location_uuid:
        filters["location-uuid"] = location_uuid

    return table_payloads.table_payload(
        "packages-server",
        columns=[
            {"key": "uuid", "label": _("UUID"), "sortable": False},
            {"key": "origin_pipeline", "label": _("Originating Pipeline")},
            {"key": "current_location", "label": _("Current Location")},
            {"key": "size", "label": _("Size")},
            {"key": "package_type", "label": _("Type")},
            {"key": "replica_of", "label": _("Replica Of")},
            {"key": "status", "label": _("Status")},
            {"key": "stored", "label": _("Stored")},
            {"key": "fixity_date", "label": _("Fixity Date")},
            {"key": "fixity_status", "label": _("Fixity Status")},
            {"key": "actions", "label": _("Actions"), "sortable": False},
        ],
        rows=[],
        ui=_server_table_ui(
            endpoint=endpoint,
            default_sort_column_key="origin_pipeline",
            default_sort_direction="asc",
            filters=filters or None,
        ),
    )


def fixity_logs_server_payload(
    *,
    endpoint: str,
    package_uuid: str,
) -> table_payloads.TablePayload:
    return table_payloads.table_payload(
        "fixity-logs-server",
        columns=[
            {"key": "date", "label": _("Date")},
            {"key": "error", "label": _("Error")},
        ],
        rows=[],
        ui=_server_table_ui(
            endpoint=endpoint,
            default_sort_column_key="date",
            default_sort_direction="desc",
            filters={"package-uuid": package_uuid},
        ),
    )


def package_requests_pending_payload(
    request_events: Iterable[Event],
    *,
    include_decision: bool,
    form_action: str,
    csrf_token: str,
    reason_label: str,
    approve_label: str,
    reject_label: str,
    row_states: dict[int, DecisionFormState] | None = None,
) -> table_payloads.TablePayload:
    state_by_event_id = row_states or {}
    rows: list[table_payloads.PayloadRow] = []

    for request_event in request_events:
        row: table_payloads.PayloadRow = {
            "file": str(request_event.package),
            "type": request_event.package.get_package_type_display(),
            "reason": request_event.event_reason,
            "pipeline": str(request_event.pipeline),
            "user": _event_user_label(request_event),
            "submitted": localize(request_event.status_time),
        }
        if include_decision:
            state = state_by_event_id.get(request_event.id, {})
            row["actions"] = table_payloads.decision_form(
                action=form_action,
                csrf_token=csrf_token,
                event_id=request_event.id,
                reason_label=reason_label,
                approve_label=approve_label,
                reject_label=reject_label,
                event_id_name=EVENT_ID_FIELD_NAME,
                reason_name=STATUS_REASON_FIELD_NAME,
                decision_name=DECISION_FIELD_NAME,
                approve_value=APPROVE_DECISION_VALUE,
                reject_value=REJECT_DECISION_VALUE,
                reason_value=state.get("reason_value", ""),
                reason_errors=state.get("reason_errors"),
            )
        rows.append(row)

    columns: list[table_payloads.ColumnPayload] = [
        {"key": "file", "label": _("File")},
        {"key": "type", "label": _("Type")},
        {"key": "reason", "label": _("Reason")},
        {"key": "pipeline", "label": _("Pipeline")},
        {"key": "user", "label": _("User")},
        {"key": "submitted", "label": _("Submitted")},
    ]
    if include_decision:
        columns.append(
            {"key": "actions", "label": _("Approve/Reject"), "sortable": False}
        )

    return table_payloads.table_payload(
        "package-requests-pending",
        columns=columns,
        rows=rows,
    )


def package_requests_closed_payload(
    closed_requests: Iterable[Event],
) -> table_payloads.TablePayload:
    rows: list[table_payloads.PayloadRow] = []
    for request_event in closed_requests:
        rows.append(
            {
                "file": str(request_event.package),
                "type": request_event.package.get_package_type_display(),
                "reason": request_event.event_reason,
                "pipeline": str(request_event.pipeline),
                "user": _event_user_label(request_event),
                "decision": request_event.get_status_display(),
                "statusReason": request_event.status_reason or "",
                "storageAdmin": str(request_event.admin_id)
                if request_event.admin_id
                else "",
                "updated": localize(request_event.status_time),
            }
        )

    return table_payloads.table_payload(
        "package-requests-closed",
        columns=[
            {"key": "file", "label": _("File")},
            {"key": "type", "label": _("Type")},
            {"key": "reason", "label": _("Reason")},
            {"key": "pipeline", "label": _("Pipeline")},
            {"key": "user", "label": _("User")},
            {"key": "decision", "label": _("Decision")},
            {"key": "statusReason", "label": _("Reason")},
            {"key": "storageAdmin", "label": _("Storage Admin")},
            {"key": "updated", "label": _("Updated")},
        ],
        rows=rows,
    )
