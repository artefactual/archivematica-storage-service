from collections.abc import Iterable
from urllib.parse import urlencode

from django.contrib.auth.models import User
from django.http import HttpRequest
from django.urls import reverse
from django.utils.translation import gettext as _

from archivematica.storage_service.common import table_payloads


def _attr(value: object, name: str) -> str:
    if isinstance(value, dict):
        raw = value.get(name, "")
    else:
        raw = getattr(value, name, "")
    return str(raw)


def key_list_payload(
    request: HttpRequest, keys: Iterable[object]
) -> table_payloads.TablePayload:
    next_query = urlencode({"next": request.path})
    rows: list[table_payloads.PayloadRow] = []
    for key_display in keys:
        fingerprint = _attr(key_display, "fingerprint")
        keyid = _attr(key_display, "keyid")
        rows.append(
            {
                "keyid": table_payloads.link(
                    keyid,
                    reverse("administration:key_detail", args=[fingerprint]),
                ),
                "fingerprint": fingerprint,
                "actions": [
                    table_payloads.action(
                        _("Delete"),
                        f"{reverse('administration:key_delete', args=[fingerprint])}?{next_query}",
                    )
                ],
            }
        )

    return table_payloads.table_payload(
        "keys-list",
        columns=[
            {"key": "keyid", "label": _("Keyid")},
            {"key": "fingerprint", "label": _("Fingerprint")},
            {"key": "actions", "label": _("Actions"), "sortable": False},
        ],
        rows=rows,
    )


def user_list_payload(
    request: HttpRequest,
    users: Iterable[User],
    *,
    allow_user_edits: bool,
) -> table_payloads.TablePayload:
    rows: list[table_payloads.PayloadRow] = []
    for user_display in users:
        username = user_display.username
        if request.user == user_display:
            username = _("%(username)s (you)") % {"username": username}

        actions: list[table_payloads.ActionPayload] = []
        if request.user.is_superuser or request.user.id == user_display.id:
            if allow_user_edits:
                action_url = reverse("administration:user_edit", args=[user_display.id])
                action_label = _("Edit")
            else:
                action_url = reverse(
                    "administration:user_detail", args=[user_display.id]
                )
                action_label = _("View")
            actions.append(
                table_payloads.action(
                    action_label,
                    action_url,
                    style="primary",
                )
            )

        rows.append(
            {
                "username": username,
                "name": user_display.get_full_name(),
                "email": user_display.email,
                "role": user_display.get_role_label(),
                "active": _("True") if user_display.is_active else _("False"),
                "actions": actions,
            }
        )

    return table_payloads.table_payload(
        "users-list",
        columns=[
            {"key": "username", "label": _("Username")},
            {"key": "name", "label": _("Name")},
            {"key": "email", "label": _("E-mail")},
            {"key": "role", "label": _("Role")},
            {"key": "active", "label": _("Active")},
            {"key": "actions", "label": "", "sortable": False},
        ],
        rows=rows,
    )
