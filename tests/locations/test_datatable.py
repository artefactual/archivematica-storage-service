"""Tests for the datatable utilities."""

import pytest

from archivematica.storage_service.locations import datatable_utils
from archivematica.storage_service.locations import models

# The package rows hold this many packages.
TOTAL_FIXTURE_PACKAGES = 13

# The fixity log rows hold this many fixity logs.
TOTAL_FIXTURE_FIXITY_LOGS = 4


@pytest.mark.django_db
@pytest.mark.usefixtures("package_rows")
def test_initialization() -> None:
    DISPLAY_LEN = 10
    datatable = datatable_utils.PackageDataTable({})
    expected_params = {
        "search": "",
        "display_start": 0,
        "display_length": DISPLAY_LEN,
        "sorting_column": {},
        "echo": -1,
    }
    assert datatable.params == expected_params
    assert datatable.total_records == TOTAL_FIXTURE_PACKAGES
    assert datatable.total_display_records == TOTAL_FIXTURE_PACKAGES
    assert len(datatable.records) == DISPLAY_LEN


@pytest.mark.django_db
@pytest.mark.usefixtures("package_rows")
def test_search_description() -> None:
    datatable = datatable_utils.PackageDataTable(
        {
            "sSearch": "Small bagged package",
            "iDisplayStart": 0,
            "iDisplayLength": 20,
            "sEcho": "1",
        }
    )
    expected_params = {
        "search": "Small bagged package",
        "display_start": 0,
        "display_length": 20,
        "sorting_column": {},
        "echo": 1,
    }
    assert datatable.params == expected_params
    assert datatable.total_records == TOTAL_FIXTURE_PACKAGES
    assert datatable.total_display_records == 1
    assert len(datatable.records) == 1


@pytest.mark.django_db
@pytest.mark.usefixtures("package_rows")
def test_search_current_path() -> None:
    datatable = datatable_utils.PackageDataTable(
        {
            "sSearch": "working_bag",
            "iDisplayStart": 0,
            "iDisplayLength": 10,
            "sEcho": "1",
        }
    )
    expected_params = {
        "search": "working_bag",
        "display_start": 0,
        "display_length": 10,
        "sorting_column": {},
        "echo": 1,
    }
    assert datatable.params == expected_params
    assert datatable.total_records == TOTAL_FIXTURE_PACKAGES
    assert datatable.total_display_records == 3
    assert len(datatable.records) == 3


@pytest.mark.django_db
@pytest.mark.usefixtures("package_rows")
def test_search_type() -> None:
    datatable = datatable_utils.PackageDataTable(
        {
            "sSearch": "Transfer",
            "iDisplayStart": 0,
            "iDisplayLength": 10,
            "sEcho": "1",
        }
    )
    expected_params = {
        "search": "Transfer",
        "display_start": 0,
        "display_length": 10,
        "sorting_column": {},
        "echo": 1,
    }
    assert datatable.params == expected_params
    assert datatable.total_records == TOTAL_FIXTURE_PACKAGES
    assert datatable.total_display_records == 3
    assert len(datatable.records) == 3


@pytest.mark.django_db
@pytest.mark.usefixtures("package_rows")
def test_search_status() -> None:
    DISPLAY_LEN = 10
    datatable = datatable_utils.PackageDataTable(
        {
            "sSearch": "Uploaded",
            "iDisplayStart": 0,
            "iDisplayLength": DISPLAY_LEN,
            "sEcho": "1",
        }
    )
    expected_params = {
        "search": "Uploaded",
        "display_start": 0,
        "display_length": DISPLAY_LEN,
        "sorting_column": {},
        "echo": 1,
    }
    assert datatable.params == expected_params
    assert datatable.total_records == TOTAL_FIXTURE_PACKAGES
    assert datatable.total_display_records == TOTAL_FIXTURE_PACKAGES
    assert len(datatable.records) == DISPLAY_LEN


@pytest.mark.django_db
@pytest.mark.usefixtures("package_rows")
def test_search_replica_of(
    replicated_package: models.Package, replicas: list[models.Package]
) -> None:
    package_uuid = replicated_package.uuid
    replicas_uuids = [replica.uuid for replica in replicas]
    datatable = datatable_utils.PackageDataTable(
        {
            "sSearch": str(package_uuid),
            "iDisplayStart": 0,
            "iDisplayLength": 10,
            "sEcho": "1",
        }
    )
    expected_params = {
        "search": str(package_uuid),
        "display_start": 0,
        "display_length": 10,
        "sorting_column": {},
        "echo": 1,
    }
    # searching for the original package uuid should return its replicas too
    expected_packages_uuids = sorted([package_uuid] + replicas_uuids)
    assert datatable.params == expected_params
    assert datatable.total_records == TOTAL_FIXTURE_PACKAGES
    assert datatable.total_display_records == len(expected_packages_uuids)
    assert len(datatable.records) == len(expected_packages_uuids)
    assert sorted(p.uuid for p in datatable.records) == expected_packages_uuids


@pytest.mark.django_db
@pytest.mark.usefixtures("package_rows")
def test_reverse_search_replica_of(
    replicated_package: models.Package, replicas: list[models.Package]
) -> None:
    package_uuid = replicated_package.uuid
    replicas_uuids = [replica.uuid for replica in replicas]
    datatable = datatable_utils.PackageDataTable(
        {
            "sSearch": str(replicas_uuids[0]),
            "iDisplayStart": 0,
            "iDisplayLength": 10,
            "sEcho": "1",
        }
    )
    expected_params = {
        "search": str(replicas_uuids[0]),
        "display_start": 0,
        "display_length": 10,
        "sorting_column": {},
        "echo": 1,
    }
    # searching for the replica uuid should return its original package too
    expected_packages_uuids = sorted([package_uuid, replicas_uuids[0]])
    assert datatable.params == expected_params
    assert datatable.total_records == TOTAL_FIXTURE_PACKAGES
    assert datatable.total_display_records == len(expected_packages_uuids)
    assert len(datatable.records) == len(expected_packages_uuids)
    assert sorted(p.uuid for p in datatable.records) == expected_packages_uuids


@pytest.mark.django_db
def test_sorting_uuid_ascending(package_rows: list[models.Package]) -> None:
    datatable = datatable_utils.PackageDataTable(
        {
            "iSortingCols": 1,
            "iSortCol_0": 0,
            "bSortable_0": "true",
            "sSortDir_0": "asc",
            "iDisplayStart": 0,
            "iDisplayLength": 10,
            "sEcho": "1",
        }
    )
    expected_params = {
        "search": "",
        "display_start": 0,
        "display_length": 10,
        "sorting_column": {"index": 0, "direction": "asc"},
        "echo": 1,
    }
    assert datatable.params == expected_params
    expected_uuids = sorted(package.uuid for package in package_rows)[:10]
    assert [package.uuid for package in datatable.records] == expected_uuids


@pytest.mark.django_db
def test_sorting_uuid_descending(package_rows: list[models.Package]) -> None:
    datatable = datatable_utils.PackageDataTable(
        {
            "iSortingCols": 1,
            "iSortCol_0": 0,
            "bSortable_0": "true",
            "sSortDir_0": "desc",
            "iDisplayStart": 0,
            "iDisplayLength": 10,
            "sEcho": "1",
        }
    )
    expected_params = {
        "search": "",
        "display_start": 0,
        "display_length": 10,
        "sorting_column": {"index": 0, "direction": "desc"},
        "echo": 1,
    }
    assert datatable.params == expected_params
    uuids_descending = sorted((package.uuid for package in package_rows), reverse=True)
    assert [package.uuid for package in datatable.records] == uuids_descending[:10]


@pytest.mark.django_db
def test_sorting_by_full_path_helper(package_rows: list[models.Package]) -> None:
    datatable = datatable_utils.PackageDataTable(
        {
            "iSortingCols": 1,
            "iSortCol_0": 2,
            "bSortable_2": "true",
            "iDisplayStart": 0,
            "iDisplayLength": 10,
            "sEcho": "1",
        }
    )
    expected_params = {
        "search": "",
        "display_start": 0,
        "display_length": 10,
        "sorting_column": {"index": 2, "direction": "asc"},
        "echo": 1,
    }
    assert datatable.params == expected_params
    expected_paths = sorted(package.full_path for package in package_rows)[:10]
    assert [package.full_path for package in datatable.records] == expected_paths


@pytest.mark.django_db
@pytest.mark.usefixtures("package_rows")
def test_packages_are_filtered_by_location(
    testing_aip_storage: models.Location,
) -> None:
    # count all packages with no filtering
    datatable = datatable_utils.PackageDataTable(
        {"iDisplayStart": 0, "iDisplayLength": 10, "sEcho": "1"}
    )
    assert datatable.total_records == TOTAL_FIXTURE_PACKAGES
    TOTAL_RECORDS_IN_LOCATION = 10
    # count packages only from that location
    datatable = datatable_utils.PackageDataTable(
        {
            "iDisplayStart": 0,
            "iDisplayLength": 10,
            "sEcho": "1",
            "location-uuid": testing_aip_storage.uuid,
        }
    )
    assert datatable.total_records == TOTAL_RECORDS_IN_LOCATION


@pytest.mark.django_db
@pytest.mark.usefixtures("package_rows")
def test_packages_are_filtered_by_location_and_description(
    testing_aip_storage: models.Location,
) -> None:
    # count packages only from that location
    datatable = datatable_utils.PackageDataTable(
        {
            "sSearch": "broken bag",
            "iDisplayStart": 0,
            "iDisplayLength": 10,
            "sEcho": "1",
            "location-uuid": testing_aip_storage.uuid,
        }
    )
    assert len(datatable.records) == 1
    package = datatable.records[0]
    assert package.current_path == "broken_bag"
    assert package.description == "Broken bag"


@pytest.mark.django_db
@pytest.mark.usefixtures("fixity_log_rows")
def test_fixity_logs_are_filtered_by_package(
    images_transfer: models.Package,
) -> None:
    # count all fixity logs with no filtering
    datatable = datatable_utils.FixityLogDataTable(
        {"iDisplayStart": 0, "iDisplayLength": 10, "sEcho": "1"}
    )
    assert datatable.total_records == TOTAL_FIXTURE_FIXITY_LOGS
    TOTAL_RECORDS_IN_PACKAGE = 3
    # count fixity logs only from that package
    datatable = datatable_utils.FixityLogDataTable(
        {
            "iDisplayStart": 0,
            "iDisplayLength": 10,
            "sEcho": "1",
            "package-uuid": images_transfer.uuid,
        }
    )
    assert datatable.total_records == TOTAL_RECORDS_IN_PACKAGE


@pytest.mark.django_db
@pytest.mark.usefixtures("fixity_log_rows")
def test_fixity_logs_are_filtered_by_package_and_error_details(
    images_transfer: models.Package,
) -> None:
    # count fixity logs only from that package
    datatable = datatable_utils.FixityLogDataTable(
        {
            "sSearch": "FAILED",
            "iDisplayStart": 0,
            "iDisplayLength": 10,
            "sEcho": "1",
            "package-uuid": images_transfer.uuid,
        }
    )
    assert len(datatable.records) == 2
    expected_errors = [
        "Checksum failed.",
        "Other thing failed.",
    ]
    assert [log.error_details for log in datatable.records] == expected_errors


@pytest.mark.django_db
@pytest.mark.usefixtures("fixity_log_rows")
def test_search_error_details() -> None:
    datatable = datatable_utils.FixityLogDataTable(
        {
            "sSearch": "failed",
            "iDisplayStart": 0,
            "iDisplayLength": 20,
            "sEcho": "1",
        }
    )
    expected_params = {
        "search": "failed",
        "display_start": 0,
        "display_length": 20,
        "sorting_column": {},
        "echo": 1,
    }
    assert datatable.params == expected_params
    assert datatable.total_records == TOTAL_FIXTURE_FIXITY_LOGS
    assert datatable.total_display_records == 2
    assert len(datatable.records) == 2


@pytest.mark.django_db
@pytest.mark.usefixtures("fixity_log_rows")
def test_sorting_datetime_reported_ascending() -> None:
    datatable = datatable_utils.FixityLogDataTable(
        {
            "iSortingCols": 1,
            "iSortCol_0": 0,
            "bSortable_0": "true",
            "sSortDir_0": "asc",
            "iDisplayStart": 0,
            "iDisplayLength": 10,
            "sEcho": "1",
        }
    )
    expected_params = {
        "search": "",
        "display_start": 0,
        "display_length": 10,
        "sorting_column": {"index": 0, "direction": "asc"},
        "echo": 1,
    }
    assert datatable.params == expected_params
    expected_datetimes = [
        "2015-12-15T03:00:05",
        "2016-12-15T03:00:05",
        "2017-12-15T03:00:05",
        "2018-12-15T03:00:05",
    ]
    assert [
        log.datetime_reported.strftime("%Y-%m-%dT%H:%M:%S") for log in datatable.records
    ] == expected_datetimes


@pytest.mark.django_db
@pytest.mark.usefixtures("fixity_log_rows")
def test_sorting_datetime_reported_descending() -> None:
    datatable = datatable_utils.FixityLogDataTable(
        {
            "iSortingCols": 1,
            "iSortCol_0": 0,
            "bSortable_0": "true",
            "sSortDir_0": "desc",
            "iDisplayStart": 0,
            "iDisplayLength": 10,
            "sEcho": "1",
        }
    )
    expected_params = {
        "search": "",
        "display_start": 0,
        "display_length": 10,
        "sorting_column": {"index": 0, "direction": "desc"},
        "echo": 1,
    }
    assert datatable.params == expected_params
    expected_datetimes = [
        "2018-12-15T03:00:05",
        "2017-12-15T03:00:05",
        "2016-12-15T03:00:05",
        "2015-12-15T03:00:05",
    ]
    assert [
        log.datetime_reported.strftime("%Y-%m-%dT%H:%M:%S") for log in datatable.records
    ] == expected_datetimes
