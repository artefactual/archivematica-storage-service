from urllib.parse import parse_qs
from urllib.parse import urlparse

import pytest
from django.test import Client
from django.urls import reverse

from archivematica.storage_service.locations import models
from tests.factories import PackageFactory


@pytest.fixture
def package(package: models.Package, pipeline: models.Pipeline) -> models.Package:
    """The compressed AIP, which originates in the pipeline."""
    package.origin_pipeline = pipeline
    package.size = 1024
    package.save()

    return package


def package_datatable_params(search: str = "") -> dict[str, str]:
    return {
        "sEcho": "1",
        "iDisplayStart": "0",
        "iDisplayLength": "10",
        "iSortingCols": "1",
        "iSortCol_0": "0",
        "sSortDir_0": "asc",
        "bSortable_0": "true",
        "sSearch": search,
    }


def fixity_datatable_params(package_uuid: str) -> dict[str, str]:
    return {
        "sEcho": "1",
        "iDisplayStart": "0",
        "iDisplayLength": "10",
        "iSortingCols": "1",
        "iSortCol_0": "0",
        "sSortDir_0": "desc",
        "bSortable_0": "true",
        "sSearch": "",
        "package-uuid": package_uuid,
    }


@pytest.mark.django_db
def test_package_list_ajax_returns_structured_rows(
    admin_client: Client,
    package: models.Package,
    aip_storage_location: models.Location,
    pipeline: models.Pipeline,
) -> None:
    package.pointer_file_location = aip_storage_location
    package.pointer_file_path = "pointer.example.xml"
    package.save()
    models.FixityLog.objects.create(
        package=package,
        success=False,
        error_details="Checksum failed",
    )

    response = admin_client.get(
        reverse("locations:package_list_ajax"),
        data=package_datatable_params(search=str(package.uuid)),
        HTTP_REFERER="/packages/",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["iTotalRecords"] == 1
    assert payload["iTotalDisplayRecords"] == 1
    assert len(payload["aaData"]) == 1

    row = payload["aaData"][0]
    assert set(row) == {
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
    }
    assert row["uuid"] == str(package.uuid)
    assert row["origin_pipeline"]["text"] == str(pipeline)
    assert row["origin_pipeline"]["href"] == reverse(
        "locations:pipeline_detail",
        args=[pipeline.uuid],
    )
    assert row["current_location"]["text"] == package.full_path
    assert row["current_location"]["href"] == reverse(
        "download_request",
        args=["v2", "file", package.uuid],
    )
    assert row["status"]["text"] == package.get_status_display()

    update_status_url = row["status"]["update_href"]
    assert update_status_url is not None
    parsed_update_status_url = urlparse(update_status_url)
    assert parsed_update_status_url.path == reverse(
        "locations:package_update_status",
        args=[package.uuid],
    )
    assert parse_qs(parsed_update_status_url.query)["next"] == ["/packages/"]

    assert row["fixity_status"]["text"] == "Failed"
    assert row["fixity_status"]["href"] == reverse(
        "locations:package_fixity",
        args=[package.uuid],
    )

    actions = row["actions"]
    assert actions["pointer_file_href"] == reverse(
        "pointer_file_request",
        args=["v2", "file", package.uuid],
    )
    assert actions["download_href"] == reverse(
        "download_request",
        args=["v2", "file", package.uuid],
    )
    request_delete_action = actions["request_delete"]
    assert request_delete_action is not None
    assert request_delete_action["action_url"] == reverse(
        "locations:package_request_deletion",
        args=[package.uuid],
    )
    assert request_delete_action["csrf_token"]
    assert actions["reingest_href"] is not None
    parsed_reingest_url = urlparse(actions["reingest_href"])
    assert parsed_reingest_url.path == reverse(
        "locations:aip_reingest", args=[package.uuid]
    )
    assert parse_qs(parsed_reingest_url.query)["next"] == ["/packages/"]
    assert actions["direct_delete"] is None


@pytest.mark.django_db
def test_package_list_ajax_returns_direct_delete_payload_for_dips(
    admin_client: Client,
    package: models.Package,
) -> None:
    package.package_type = models.Package.DIP
    package.current_path = "example-dip.tar"
    package.save()

    response = admin_client.get(
        reverse("locations:package_list_ajax"),
        data=package_datatable_params(search=str(package.uuid)),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["iTotalDisplayRecords"] == 1

    row = payload["aaData"][0]
    actions = row["actions"]
    assert actions["request_delete"] is None
    assert actions["reingest_href"] is None
    direct_delete = actions["direct_delete"]
    assert direct_delete is not None
    assert direct_delete["action_url"] == reverse(
        "locations:package_delete",
        args=[package.uuid],
    )
    assert direct_delete["csrf_token"]
    assert direct_delete["modal_id"] == f"confirm-delete-{package.uuid}"
    assert direct_delete["modal_label_id"] == f"confirm-delete-title-{package.uuid}"


@pytest.mark.django_db
def test_package_list_ajax_hides_privileged_actions_for_non_privileged_users(
    logged_in_client: Client,
    package: models.Package,
) -> None:
    response = logged_in_client.get(
        reverse("locations:package_list_ajax"),
        data=package_datatable_params(search=str(package.uuid)),
    )

    assert response.status_code == 200
    payload = response.json()
    row = payload["aaData"][0]
    assert row["status"]["update_href"] is None
    assert row["actions"]["request_delete"] is None
    assert row["actions"]["reingest_href"] is None
    assert row["actions"]["direct_delete"] is None


@pytest.mark.django_db
def test_package_list_ajax_hides_request_delete_without_origin_pipeline(
    admin_client: Client,
    package: models.Package,
) -> None:
    package.origin_pipeline = None
    package.save(update_fields=["origin_pipeline"])

    response = admin_client.get(
        reverse("locations:package_list_ajax"),
        data=package_datatable_params(search=str(package.uuid)),
    )

    assert response.status_code == 200
    payload = response.json()
    row = payload["aaData"][0]
    assert row["actions"]["request_delete"] is None


@pytest.mark.django_db
def test_fixity_logs_ajax_returns_structured_rows(
    admin_client: Client,
    make_package: PackageFactory,
    package: models.Package,
    aip_storage_location: models.Location,
    pipeline: models.Pipeline,
) -> None:
    other_package = make_package(
        aip_storage_location, "other-fixity-aip.7z", origin_pipeline=pipeline
    )
    models.FixityLog.objects.create(
        package=package,
        success=False,
        error_details="Checksum failed",
    )
    models.FixityLog.objects.create(
        package=package,
        success=False,
        error_details="Digest mismatch",
    )
    models.FixityLog.objects.create(
        package=other_package,
        success=False,
        error_details="Different package error",
    )

    response = admin_client.get(
        reverse("locations:fixity_logs_ajax"),
        data=fixity_datatable_params(str(package.uuid)),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["iTotalRecords"] == 2
    assert payload["iTotalDisplayRecords"] == 2
    assert len(payload["aaData"]) == 2
    assert [set(row) for row in payload["aaData"]] == [{"date", "error"}] * 2
    assert [bool(row["date"]) for row in payload["aaData"]] == [True, True]
    assert {row["error"] for row in payload["aaData"]} == {
        "Checksum failed",
        "Digest mismatch",
    }
