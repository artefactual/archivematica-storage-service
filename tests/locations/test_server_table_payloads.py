from django.urls import reverse

from archivematica.storage_service.locations import table_payloads


def test_packages_server_payload_includes_expected_ui_config() -> None:
    payload = table_payloads.packages_server_payload(
        endpoint=reverse("locations:package_list_ajax"),
        location_uuid="location-uuid",
    )

    assert payload["kind"] == "packages-server"
    assert payload["rows"] == []
    assert [column["key"] for column in payload["columns"]] == [
        "uuid",
        "origin_pipeline",
        "current_location",
        "size",
        "package_type",
        "replica_of",
        "status",
        "stored",
        "fixity_date",
        "fixity_status",
        "actions",
    ]
    assert payload["ui"]["server"] == {
        "mode": "server-datatables-v1",
        "endpoint": reverse("locations:package_list_ajax"),
        "defaultSort": {
            "columnKey": "origin_pipeline",
            "direction": "asc",
        },
        "filters": {"location-uuid": "location-uuid"},
    }


def test_fixity_logs_server_payload_includes_expected_ui_config() -> None:
    payload = table_payloads.fixity_logs_server_payload(
        endpoint=reverse("locations:fixity_logs_ajax"),
        package_uuid="package-uuid",
    )

    assert payload["kind"] == "fixity-logs-server"
    assert payload["rows"] == []
    assert [column["key"] for column in payload["columns"]] == [
        "date",
        "error",
    ]
    assert payload["ui"]["server"] == {
        "mode": "server-datatables-v1",
        "endpoint": reverse("locations:fixity_logs_ajax"),
        "defaultSort": {
            "columnKey": "date",
            "direction": "desc",
        },
        "filters": {"package-uuid": "package-uuid"},
    }
