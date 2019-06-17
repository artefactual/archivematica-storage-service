# -*- coding: utf-8 -*-
"""Tests for the datatable utilities."""

from django.test import TestCase

from locations import datatable_utils


class TestDataTable(TestCase):

    fixtures = ["base.json", "package.json"]

    def test_initialization(self):
        datatable = datatable_utils.DataTable({})
        expected_params = {
            "search": "",
            "display_start": 0,
            "display_length": 10,
            "sorting_column": {},
            "echo": -1,
        }
        assert datatable.params == expected_params
        assert datatable.total_records == 7
        assert datatable.total_display_records == 7
        assert len(datatable.packages) == 7

    def test_search_description(self):
        datatable = datatable_utils.DataTable(
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
        assert datatable.total_records == 7
        assert datatable.total_display_records == 1
        assert len(datatable.packages) == 1

    def test_search_current_path(self):
        datatable = datatable_utils.DataTable(
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
        assert datatable.total_records == 7
        assert datatable.total_display_records == 3
        assert len(datatable.packages) == 3

    def test_search_type(self):
        datatable = datatable_utils.DataTable(
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
        assert datatable.total_records == 7
        assert datatable.total_display_records == 3
        assert len(datatable.packages) == 3

    def test_search_status(self):
        datatable = datatable_utils.DataTable(
            {
                "sSearch": "Uploaded",
                "iDisplayStart": 0,
                "iDisplayLength": 10,
                "sEcho": "1",
            }
        )
        expected_params = {
            "search": "Uploaded",
            "display_start": 0,
            "display_length": 10,
            "sorting_column": {},
            "echo": 1,
        }
        assert datatable.params == expected_params
        assert datatable.total_records == 7
        assert datatable.total_display_records == 7
        assert len(datatable.packages) == 7

    def test_sorting_uuid(self):
        datatable = datatable_utils.DataTable(
            {
                "iSortingCols": 1,
                "iSortCol_0": 0,
                "bSortable_0": "true",
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
            "0d4e739b-bf60-4b87-bc20-67a379b28cea",
            "6aebdb24-1b6b-41ab-b4a3-df9a73726a34",
            "79245866-ca80-4f84-b904-a02b3e0ab621",
            "88deec53-c7dc-4828-865c-7356386e9399",
            "9f260047-a9b7-4a75-bb6a-e8d94c83edd2",
            "a59033c2-7fa7-41e2-9209-136f07174692",
            "e0a41934-c1d7-45ba-9a95-a7531c063ed1",
        ]
        assert [package.uuid for package in datatable.packages] == expected_uuids
