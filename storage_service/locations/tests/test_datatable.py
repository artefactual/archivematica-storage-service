# -*- coding: utf-8 -*-
"""Tests for the datatable utilities."""

from __future__ import absolute_import
import os
import tempfile

from django.test import TestCase

from locations import datatable_utils
from locations import models

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
FIXTURES_DIR = os.path.abspath(os.path.join(THIS_DIR, "..", "fixtures", ""))


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

    def _create_replicas(self, uuid):
        test_location = models.Location.objects.get(
            uuid="615103f0-0ee0-4a12-ba17-43192d1143ea"
        )
        test_location.relative_path = FIXTURES_DIR[1:]
        test_location.save()
        models.Location.objects.filter(purpose="SS").update(
            relative_path=FIXTURES_DIR[1:]
        )
        tmp_dir = tempfile.mkdtemp()
        space_dir = tempfile.mkdtemp(dir=tmp_dir, prefix="space")
        replication_dir = tempfile.mkdtemp(dir=tmp_dir, prefix="replication")
        replication_dir2 = tempfile.mkdtemp(dir=tmp_dir, prefix="replication")
        aip = models.Package.objects.get(uuid=uuid)
        aip.current_location.space.staging_path = space_dir
        aip.current_location.space.save()
        aip.current_location.replicators.create(
            space=aip.current_location.space,
            relative_path=replication_dir,
            purpose=models.Location.REPLICATOR,
        )
        aip.current_location.replicators.create(
            space=aip.current_location.space,
            relative_path=replication_dir2,
            purpose=models.Location.REPLICATOR,
        )
        aip.create_replicas()
        assert aip.replicas.count() == 2
        return [replica.uuid for replica in aip.replicas.all()]

    def test_search_replica_of(self):
        package_uuid = "0d4e739b-bf60-4b87-bc20-67a379b28cea"
        replicas_uuids = self._create_replicas(package_uuid)
        datatable = datatable_utils.DataTable(
            {
                "sSearch": package_uuid,
                "iDisplayStart": 0,
                "iDisplayLength": 10,
                "sEcho": "1",
            }
        )
        expected_params = {
            "search": package_uuid,
            "display_start": 0,
            "display_length": 10,
            "sorting_column": {},
            "echo": 1,
        }
        # searching for the original package uuid should return its replicas too
        expected_packages_uuids = sorted([package_uuid] + replicas_uuids)
        assert datatable.params == expected_params
        assert datatable.total_records == 9
        assert datatable.total_display_records == 3
        assert len(datatable.packages) == 3
        assert sorted([p.uuid for p in datatable.packages]) == expected_packages_uuids

    def test_reverse_search_replica_of(self):
        package_uuid = "0d4e739b-bf60-4b87-bc20-67a379b28cea"
        replicas_uuids = self._create_replicas(package_uuid)
        datatable = datatable_utils.DataTable(
            {
                "sSearch": replicas_uuids[0],
                "iDisplayStart": 0,
                "iDisplayLength": 10,
                "sEcho": "1",
            }
        )
        expected_params = {
            "search": replicas_uuids[0],
            "display_start": 0,
            "display_length": 10,
            "sorting_column": {},
            "echo": 1,
        }
        # searching for the replica uuid should return its original package too
        expected_packages_uuids = sorted([package_uuid, replicas_uuids[0]])
        assert datatable.params == expected_params
        assert datatable.total_records == 9
        assert datatable.total_display_records == 2
        assert len(datatable.packages) == 2
        assert sorted([p.uuid for p in datatable.packages]) == expected_packages_uuids

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
