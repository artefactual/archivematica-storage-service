from typing import Any
from typing import TypedDict

PayloadRow = dict[str, Any]

DECISION_FORM_KIND = "decision-form"
DECISION_FORM_METHOD_POST = "post"
DECISION_FORM_EVENT_ID_NAME = "event_id"
DECISION_FORM_REASON_NAME = "status_reason"
DECISION_FORM_DECISION_NAME = "decision"
DECISION_FORM_APPROVE_VALUE = "approve"
DECISION_FORM_REJECT_VALUE = "reject"


class LinkPayload(TypedDict):
    kind: str
    text: str
    href: str


class LinkItemPayload(TypedDict):
    text: str
    href: str


class LinkListPayload(TypedDict, total=False):
    kind: str
    items: list[LinkItemPayload]
    emptyText: str
    separator: str


class TextWithLinksPayload(TypedDict, total=False):
    kind: str
    text: str
    connector: str
    items: list[LinkItemPayload]


class ActionPayload(TypedDict):
    label: str
    href: str
    style: str


class DecisionFormPayload(TypedDict, total=False):
    kind: str
    action: str
    method: str
    csrfToken: str
    eventIdName: str
    eventId: int
    reasonName: str
    reasonLabel: str
    reasonValue: str
    reasonErrors: list[str]
    decisionName: str
    approveValue: str
    rejectValue: str
    approveLabel: str
    rejectLabel: str


class ColumnPayload(TypedDict, total=False):
    key: str
    label: str
    sortable: bool


class TablePayload(TypedDict):
    version: int
    kind: str
    columns: list[ColumnPayload]
    rows: list[PayloadRow]
    ui: dict[str, Any]


def link(text: str, href: str) -> LinkPayload:
    return {"kind": "link", "text": text, "href": href}


def link_item(text: str, href: str) -> LinkItemPayload:
    return {"text": text, "href": href}


def link_list(
    items: list[LinkItemPayload],
    *,
    empty_text: str | None = None,
    separator: str = ", ",
) -> LinkListPayload:
    payload: LinkListPayload = {
        "kind": "link-list",
        "items": items,
        "separator": separator,
    }
    if empty_text is not None:
        payload["emptyText"] = empty_text
    return payload


def text_with_links(
    text: str,
    items: list[LinkItemPayload],
    *,
    connector: str = "",
) -> TextWithLinksPayload:
    payload: TextWithLinksPayload = {
        "kind": "text-with-links",
        "text": text,
        "items": items,
    }
    if connector:
        payload["connector"] = connector
    return payload


def action(label: str, href: str, *, style: str = "default") -> ActionPayload:
    return {"label": label, "href": href, "style": style}


def decision_form(
    *,
    action: str,
    csrf_token: str,
    event_id: int,
    reason_label: str,
    approve_label: str,
    reject_label: str,
    kind: str = DECISION_FORM_KIND,
    method: str = DECISION_FORM_METHOD_POST,
    event_id_name: str = DECISION_FORM_EVENT_ID_NAME,
    reason_name: str = DECISION_FORM_REASON_NAME,
    decision_name: str = DECISION_FORM_DECISION_NAME,
    approve_value: str = DECISION_FORM_APPROVE_VALUE,
    reject_value: str = DECISION_FORM_REJECT_VALUE,
    reason_value: str = "",
    reason_errors: list[str] | None = None,
) -> DecisionFormPayload:
    payload: DecisionFormPayload = {
        "kind": kind,
        "action": action,
        "method": method,
        "csrfToken": csrf_token,
        "eventIdName": event_id_name,
        "eventId": event_id,
        "reasonName": reason_name,
        "reasonLabel": reason_label,
        "reasonValue": reason_value,
        "decisionName": decision_name,
        "approveValue": approve_value,
        "rejectValue": reject_value,
        "approveLabel": approve_label,
        "rejectLabel": reject_label,
    }
    if reason_errors:
        payload["reasonErrors"] = reason_errors
    return payload


def table_payload(
    kind: str,
    *,
    columns: list[ColumnPayload],
    rows: list[PayloadRow],
    ui: dict[str, Any] | None = None,
) -> TablePayload:
    return {
        "version": 1,
        "kind": kind,
        "columns": columns,
        "rows": rows,
        "ui": ui or {},
    }
