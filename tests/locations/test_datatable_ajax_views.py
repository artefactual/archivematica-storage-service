from collections.abc import Callable
from urllib.parse import parse_qs
from urllib.parse import urlparse

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from archivematica.storage_service.locations import models

PackageFactory = Callable[..., models.Package]


@pytest.fixture
def space() -> models.Space:
    return models.Space.objects.create(
        access_protocol=models.Space.LOCAL_FILESYSTEM,
        path="/var/archivematica/storage",
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
def pipeline() -> models.Pipeline:
    return models.Pipeline.objects.create(description="Primary pipeline")


@pytest.fixture
def package_factory(
    location: models.Location,
    pipeline: models.Pipeline,
) -> PackageFactory:
    def _create(
        *,
        package_type: str = models.Package.AIP,
        status: str = models.Package.UPLOADED,
        current_path: str = "example-aip.7z",
        pointer_file: bool = False,
    ) -> models.Package:
        return models.Package.objects.create(
            current_location=location,
            current_path=current_path,
            package_type=package_type,
            status=status,
            origin_pipeline=pipeline,
            pointer_file_location=location if pointer_file else None,
            pointer_file_path="pointer.example.xml" if pointer_file else "",
            size=1024,
        )

    return _create


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
    package_factory: PackageFactory,
) -> None:
    package = package_factory(pointer_file=True)
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
    assert row["origin_pipeline"]["text"] == str(package.origin_pipeline)
    assert row["origin_pipeline"]["href"] == reverse(
        "locations:pipeline_detail",
        args=[package.origin_pipeline.uuid],
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
    package_factory: PackageFactory,
) -> None:
    dip_package = package_factory(
        package_type=models.Package.DIP,
        current_path="example-dip.tar",
    )

    response = admin_client.get(
        reverse("locations:package_list_ajax"),
        data=package_datatable_params(search=str(dip_package.uuid)),
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
        args=[dip_package.uuid],
    )
    assert direct_delete["csrf_token"]
    assert direct_delete["modal_id"] == f"confirm-delete-{dip_package.uuid}"
    assert direct_delete["modal_label_id"] == f"confirm-delete-title-{dip_package.uuid}"


@pytest.mark.django_db
def test_package_list_ajax_hides_privileged_actions_for_non_privileged_users(
    client: Client,
    django_user_model: type[User],
    package_factory: PackageFactory,
) -> None:
    package = package_factory(current_path="viewer-aip.7z")
    viewer = django_user_model.objects.create_user(
        username="viewer",
        email="viewer@example.com",
        password="Abc.Def.1234",
    )
    client.force_login(viewer)

    response = client.get(
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
    package_factory: PackageFactory,
) -> None:
    package = package_factory(current_path="no-origin-pipeline.7z")
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
    package_factory: PackageFactory,
) -> None:
    package = package_factory(current_path="fixity-aip.7z")
    other_package = package_factory(current_path="other-fixity-aip.7z")
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

    errors = set()
    for row in payload["aaData"]:
        assert set(row) == {"date", "error"}
        assert row["date"]
        errors.add(row["error"])
    assert errors == {"Checksum failed", "Digest mismatch"}
