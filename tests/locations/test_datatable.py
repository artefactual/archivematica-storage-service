"""Tests for the datatable utilities."""

import pathlib
import uuid

from django.test import TestCase
from locations import datatable_utils
from locations import models

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"


# There are 12 total packages in package.json.
TOTAL_FIXTURE_PACKAGES = 13

# There are 4 total fixity logs in fixity_log.json
TOTAL_FIXTURE_FIXITY_LOGS = 4


class TestPackageDataTable(TestCase):
    fixture_files = ["base.json", "package.json"]
    fixtures = [FIXTURES_DIR / f for f in fixture_files]

    def test_initialization(self):
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

    def test_search_description(self):
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

    def test_search_current_path(self):
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

    def test_search_type(self):
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

    def test_search_status(self):
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

    def test_search_replica_of(self):
        package_uuid = uuid.UUID("f0dfdc4c-7ba1-4e3f-a972-f2c55d870d04")
        replicas_uuids = [
            uuid.UUID("2f62b030-c3f4-4ac1-950f-fe47d0ddcd14"),
            uuid.UUID("577f74bd-a283-49e0-b4e2-f8abb81d2566"),
        ]
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

    def test_reverse_search_replica_of(self):
        package_uuid = uuid.UUID("f0dfdc4c-7ba1-4e3f-a972-f2c55d870d04")
        replicas_uuids = [
            uuid.UUID("2f62b030-c3f4-4ac1-950f-fe47d0ddcd14"),
            uuid.UUID("577f74bd-a283-49e0-b4e2-f8abb81d2566"),
        ]
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

    def test_sorting_uuid_ascending(self):
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
        expected_uuids = [
            uuid.UUID("0d4e739b-bf60-4b87-bc20-67a379b28cea"),
            uuid.UUID("2f62b030-c3f4-4ac1-950f-fe47d0ddcd14"),
            uuid.UUID("473a9398-0024-4804-81da-38946040c8af"),
            uuid.UUID("4781e745-96bc-4b06-995c-ee59fddf856d"),
            uuid.UUID("577f74bd-a283-49e0-b4e2-f8abb81d2566"),
            uuid.UUID("6aebdb24-1b6b-41ab-b4a3-df9a73726a34"),
            uuid.UUID("708f7a1d-dda4-46c7-9b3e-99e188eeb04c"),
            uuid.UUID("79245866-ca80-4f84-b904-a02b3e0ab621"),
            uuid.UUID("88deec53-c7dc-4828-865c-7356386e9399"),
            uuid.UUID("9f260047-a9b7-4a75-bb6a-e8d94c83edd2"),
        ]
        assert [package.uuid for package in datatable.records] == expected_uuids

    def test_sorting_uuid_descending(self):
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
        expected_uuids = [
            uuid.UUID("f0dfdc4c-7ba1-4e3f-a972-f2c55d870d04"),
            uuid.UUID("e0a41934-c1d7-45ba-9a95-a7531c063ed1"),
            uuid.UUID("a59033c2-7fa7-41e2-9209-136f07174692"),
            uuid.UUID("9f260047-a9b7-4a75-bb6a-e8d94c83edd2"),
            uuid.UUID("88deec53-c7dc-4828-865c-7356386e9399"),
            uuid.UUID("79245866-ca80-4f84-b904-a02b3e0ab621"),
            uuid.UUID("708f7a1d-dda4-46c7-9b3e-99e188eeb04c"),
            uuid.UUID("6aebdb24-1b6b-41ab-b4a3-df9a73726a34"),
            uuid.UUID("577f74bd-a283-49e0-b4e2-f8abb81d2566"),
            uuid.UUID("4781e745-96bc-4b06-995c-ee59fddf856d"),
        ]
        assert [package.uuid for package in datatable.records] == expected_uuids

    def test_sorting_by_full_path_helper(self):
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
        expected_paths = [
            "/2f62/b030/c3f4/4ac1/950f/fe47/d0dd/cd14/0f-2f62b030-c3f4-4ac1-950f-fe47d0ddcd14.7z",
            "/577f/74bd/a283/49e0/b4e2/f8ab/b81d/2566/0f-577f74bd-a283-49e0-b4e2-f8abb81d2566.7z",
            "/aicsmall_aic-4781e745-96bc-4b06-995c-ee59fddf856d.7z",
            "/broken_bag",
            "/dev/null/a.bz2.tricky.7z.package-473a9398-0024-4804-81da-38946040c8af.7z",
            "/dev/null/empty-transfer-79245866-ca80-4f84-b904-a02b3e0ab621",
            "/dev/null/images-transfer-de1b31fa-97dd-48e0-8417-03be78359531",
            "/dev/null/tar_gz_package-473a9398-0024-4804-81da-38946040c8af.tar.gz",
            "/dev/null/transfer-with-one-file-a59033c2-7fa7-41e2-9209-136f07174692",
            "/f0df/dc4c/7ba1/4e3f/a972/f2c5/5d87/0d04/0f-f0dfdc4c-7ba1-4e3f-a972-f2c55d870d04.7z",
        ]
        assert [package.full_path for package in datatable.records] == expected_paths

    def test_packages_are_filtered_by_location(self):
        # count all packages with no filtering
        datatable = datatable_utils.PackageDataTable(
            {"iDisplayStart": 0, "iDisplayLength": 10, "sEcho": "1"}
        )
        assert datatable.total_records == TOTAL_FIXTURE_PACKAGES
        TOTAL_RECORDS_IN_LOCATION = 10
        aip_storage_location = models.Location.objects.get(
            uuid="615103f0-0ee0-4a12-ba17-43192d1143ea"
        )
        # count packages only from that location
        datatable = datatable_utils.PackageDataTable(
            {
                "iDisplayStart": 0,
                "iDisplayLength": 10,
                "sEcho": "1",
                "location-uuid": aip_storage_location.uuid,
            }
        )
        assert datatable.total_records == TOTAL_RECORDS_IN_LOCATION

    def test_packages_are_filtered_by_location_and_description(self):
        aip_storage_location = models.Location.objects.get(
            uuid="615103f0-0ee0-4a12-ba17-43192d1143ea"
        )
        # count packages only from that location
        datatable = datatable_utils.PackageDataTable(
            {
                "sSearch": "broken bag",
                "iDisplayStart": 0,
                "iDisplayLength": 10,
                "sEcho": "1",
                "location-uuid": aip_storage_location.uuid,
            }
        )
        assert len(datatable.records) == 1
        package = datatable.records[0]
        assert package.current_path == "broken_bag"
        assert package.description == "Broken bag"


class TestFixityLogDataTable(TestCase):
    fixture_files = ["base.json", "package.json", "fixity_log.json"]
    fixtures = [FIXTURES_DIR / f for f in fixture_files]

    def test_fixity_logs_are_filtered_by_package(self):
        # count all fixity logs with no filtering
        datatable = datatable_utils.FixityLogDataTable(
            {"iDisplayStart": 0, "iDisplayLength": 10, "sEcho": "1"}
        )
        assert datatable.total_records == TOTAL_FIXTURE_FIXITY_LOGS
        TOTAL_RECORDS_IN_PACKAGE = 3
        package = models.Package.objects.get(
            uuid="e0a41934-c1d7-45ba-9a95-a7531c063ed1"
        )
        # count fixity logs only from that package
        datatable = datatable_utils.FixityLogDataTable(
            {
                "iDisplayStart": 0,
                "iDisplayLength": 10,
                "sEcho": "1",
                "package-uuid": package.uuid,
            }
        )
        assert datatable.total_records == TOTAL_RECORDS_IN_PACKAGE

    def test_fixity_logs_are_filtered_by_package_and_error_details(self):
        package = models.Package.objects.get(
            uuid="e0a41934-c1d7-45ba-9a95-a7531c063ed1"
        )
        # count fixity logs only from that package
        datatable = datatable_utils.FixityLogDataTable(
            {
                "sSearch": "FAILED",
                "iDisplayStart": 0,
                "iDisplayLength": 10,
                "sEcho": "1",
                "package-uuid": package.uuid,
            }
        )
        assert len(datatable.records) == 2
        expected_errors = [
            "Checksum failed.",
            "Other thing failed.",
        ]
        assert [log.error_details for log in datatable.records] == expected_errors

    def test_search_error_details(self):
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

    def test_sorting_datetime_reported_ascending(self):
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
            log.datetime_reported.strftime("%Y-%m-%dT%H:%M:%S")
            for log in datatable.records
        ] == expected_datetimes

    def test_sorting_datetime_reported_descending(self):
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
            log.datetime_reported.strftime("%Y-%m-%dT%H:%M:%S")
            for log in datatable.records
        ] == expected_datetimes
