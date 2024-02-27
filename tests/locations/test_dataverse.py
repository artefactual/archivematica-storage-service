import os
import pathlib
from unittest import mock

from django.test import TestCase
from locations import models

from . import TempDirMixin


FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"


class TestDataverse(TempDirMixin, TestCase):
    fixture_files = ["base.json", "dataverse.json", "dataverse2.json"]
    fixtures = [FIXTURES_DIR / f for f in fixture_files]

    def setUp(self):
        super().setUp()
        self.dataverse = models.Dataverse.objects.all()[0]
        self.dataverse_location = models.Location.objects.get(
            space=self.dataverse.space
        )

        self.space = models.Space.objects.get(access_protocol="FS")
        self.space.staging_path = str(self.tmpdir)
        self.dest_path = str(self.tmpdir / "dataverse") + os.sep

    def test_has_required_attributes(self):
        assert self.dataverse.host
        assert self.dataverse.api_key

    @mock.patch(
        "requests.get",
        side_effect=[
            mock.Mock(
                **{
                    "status_code": 200,
                    "json.return_value": {
                        "data": {
                            "total_count": 15,
                            "items": [
                                {
                                    "name": "Ad hoc observational study of the trees outside my window",
                                    "entity_id": 82,
                                },
                                {"name": "Constitive leaf ORAC", "entity_id": 25},
                                {"name": "Leaf Anatomy C4", "entity_id": 27},
                                {
                                    "name": "Massachusetts Archives Collection. v.188-Revolution Petitions, 1782-1783. SC1/series 45X, Petition of John Holmes",
                                    "entity_id": 41,
                                },
                                {
                                    "name": "Metadata mapping test study",
                                    "entity_id": 90,
                                },
                                {"name": "Nature Sounds", "entity_id": 74},
                                {"name": "new title", "entity_id": 38},
                                {"name": "new title", "entity_id": 39},
                                {"name": "new title", "entity_id": 40},
                                {"name": "ORAC COLD STRESS", "entity_id": 43},
                            ],
                            "count_in_response": 10,
                        },
                    },
                }
            ),
            mock.Mock(
                **{
                    "status_code": 200,
                    "json.return_value": {
                        "data": {
                            "total_count": 15,
                            "items": [
                                {
                                    "name": "Phenotyping for root water extraction potential, IRRI 2013",
                                    "entity_id": 49,
                                },
                                {"name": "Restricted Studies Test", "entity_id": 93},
                                {"name": "Spruce Goose", "entity_id": 10},
                                {"name": "testdocx", "entity_id": 16},
                                {"name": "testjpg", "entity_id": 14},
                            ],
                            "count_in_response": 5,
                        },
                    },
                }
            ),
        ],
    )
    def test_browse_all(self, _requests_get):
        """
        It should fetch a list of datasets.
        It should handle iteration.
        """
        resp = self.dataverse.browse("Query: *")
        assert len(resp["directories"]) == 15
        assert len(resp["entries"]) == 15
        assert resp["entries"] == resp["directories"]
        assert len(resp["properties"]) == 15
        assert (
            resp["properties"]["82"]["verbose name"]
            == "Ad hoc observational study of the trees outside my window"
        )
        assert resp["properties"]["25"]["verbose name"] == "Constitive leaf ORAC"
        assert resp["properties"]["14"]["verbose name"] == "testjpg"

    @mock.patch(
        "requests.get",
        side_effect=[
            mock.Mock(
                **{
                    "status_code": 200,
                    "json.return_value": {
                        "data": {
                            "total_count": 59,
                            "items": [
                                {
                                    "name": "3D Laser Images of a road cut at Ivy Lea, Ontario (2007), underground in Sudbury, Ontario (2007), underground in Thompson, Manitoba (2009) [test]",
                                    "entity_id": 1016,
                                },
                                {
                                    "name": "A study of my afternoon drinks ",
                                    "entity_id": 574,
                                },
                                {
                                    "name": "A study with restricted data",
                                    "entity_id": 577,
                                },
                                {"name": "A sub-dataverse dataset", "entity_id": 581},
                                {
                                    "name": "A/V and large size files [test]",
                                    "entity_id": 1059,
                                },
                                {
                                    "name": "Bala Parental Alienation Study: Canada, United Kingdom, and Australia 1984-2012 [test]",
                                    "entity_id": 784,
                                },
                                {"name": "Botanical Test", "entity_id": 34},
                                {
                                    "name": "Canadian Relocation Cases: Heading Towards Guidelines, 2011 [test]",
                                    "entity_id": 880,
                                },
                                {"name": "Concert Take 007", "entity_id": 595},
                                {"name": "dataset1", "entity_id": 783},
                            ],
                            "count_in_response": 10,
                        },
                    },
                }
            ),
            mock.Mock(
                **{
                    "status_code": 200,
                    "json.return_value": {
                        "data": {
                            "total_count": 59,
                            "items": [
                                {"name": "Depress", "entity_id": 115},
                                {"name": "ECM Dataset", "entity_id": 1128},
                                {"name": "Field data ", "entity_id": 313},
                                {"name": "Food Company Research", "entity_id": 126},
                                {"name": "Forward Sortation Area", "entity_id": 152},
                                {"name": "french testing", "entity_id": 65},
                                {"name": "GIS Data", "entity_id": 124},
                                {"name": "ICS Dataset", "entity_id": 1123},
                                {"name": "Images [test]", "entity_id": 1056},
                                {"name": "IT WAS ONLY A FISH", "entity_id": 296},
                            ],
                            "count_in_response": 10,
                        },
                    },
                }
            ),
            mock.Mock(
                **{
                    "status_code": 200,
                    "json.return_value": {
                        "data": {
                            "total_count": 59,
                            "items": [
                                {"name": "Lidar", "entity_id": 1187},
                                {
                                    "name": "Lévesque and Trudeau in the US -- translation corpus",
                                    "entity_id": 25,
                                },
                                {
                                    "name": "Lévesque and Trudeau in the US -- translation corpus",
                                    "entity_id": 24,
                                },
                                {"name": "Metadata only [test]", "entity_id": 1110},
                                {"name": "My test data", "entity_id": 122},
                                {
                                    "name": "Number of oysters in my backyard",
                                    "entity_id": 331,
                                },
                                {
                                    "name": "Other Microsoft Office Documents [test]",
                                    "entity_id": 1038,
                                },
                                {"name": "Panoramas", "entity_id": 1185},
                                {"name": "Photogrammetry", "entity_id": 1183},
                                {"name": "Sample Dataset", "entity_id": 605},
                            ],
                            "count_in_response": 10,
                        },
                    },
                }
            ),
            mock.Mock(
                **{
                    "status_code": 200,
                    "json.return_value": {
                        "data": {
                            "total_count": 59,
                            "items": [
                                {"name": "Shabooyah 1", "entity_id": 290},
                                {
                                    "name": "Social Media Use Among Teens [Canada]",
                                    "entity_id": 383,
                                },
                                {"name": "some testing", "entity_id": 374},
                                {
                                    "name": "Spatial Temporal Distortion [test]",
                                    "entity_id": 1030,
                                },
                                {
                                    "name": "Statistical software [test]",
                                    "description": 'Test data for statistical software and code. Sample data and data from Sand7 space: "Interesting data" and "Unlikely suspects"',
                                    "entity_id": 1041,
                                },
                                {"name": "tab test", "entity_id": 108},
                                {"name": "Tabular data test", "entity_id": 133},
                                {"name": "test", "entity_id": 485},
                                {"name": "test", "entity_id": 1139},
                                {"name": "test 24", "entity_id": 54},
                            ],
                            "count_in_response": 10,
                        },
                    },
                }
            ),
            mock.Mock(
                **{
                    "status_code": 200,
                    "json.return_value": {
                        "data": {
                            "total_count": 59,
                            "items": [
                                {"name": "Test Data at X Site", "entity_id": 244},
                                {"name": "test dataset", "entity_id": 23},
                                {"name": "test dataset", "entity_id": 142},
                                {"name": "Test Dataset - v2", "entity_id": 80},
                                {"name": "Test Dataset danielt", "entity_id": 300},
                                {"name": "Test dataset for DOI", "entity_id": 26},
                                {"name": "test file", "entity_id": 340},
                                {"name": "Test IP Group Permissions", "entity_id": 546},
                                {"name": "test permissions", "entity_id": 377},
                                {"name": "Test problem", "entity_id": 238},
                            ],
                            "count_in_response": 10,
                        },
                    },
                }
            ),
            mock.Mock(
                **{
                    "status_code": 200,
                    "json.return_value": {
                        "data": {
                            "total_count": 59,
                            "items": [
                                {"name": "test02", "entity_id": 346},
                                {"name": "test2", "entity_id": 259},
                                {"name": "testing for ingest ", "entity_id": 73},
                                {
                                    "name": "testing for IP group permissions",
                                    "entity_id": 67,
                                },
                                {
                                    "name": "TESTING for IP Groups - again",
                                    "entity_id": 77,
                                },
                                {"name": "testing for IP Groups 2", "entity_id": 69},
                                {"name": "The Best Dataset", "entity_id": 130},
                                {"name": "The Truth about Magnets", "entity_id": 315},
                                {
                                    "name": "WNV prevalence in Ontario regions",
                                    "entity_id": 317,
                                },
                            ],
                            "count_in_response": 9,
                        },
                    },
                }
            ),
            mock.Mock(
                **{
                    "status_code": 200,
                    "json.return_value": {
                        "data": {
                            "files": [
                                {
                                    "dataFile": {
                                        "filename": "IvyLea_003.txt",
                                        "filesize": 47448936,
                                    },
                                },
                                {
                                    "dataFile": {
                                        "filename": "IvyLea_004.txt",
                                        "filesize": 46736074,
                                    },
                                },
                                {
                                    "dataFile": {
                                        "filename": "IvyLea_005.txt",
                                        "filesize": 47463997,
                                    },
                                },
                                {
                                    "dataFile": {
                                        "filename": "IvyLea_006.txt",
                                        "filesize": 47723143,
                                    },
                                },
                            ],
                        },
                    },
                }
            ),
        ],
    )
    def test_browse_datasets(self, _requests_get):
        """
        It should fetch a list of datasets.
        It should fetch a list of objects within a dataset.
        """
        dataverse = models.Dataverse.objects.get(
            agent_name="Archivematica Test Dataverse"
        )
        location = dataverse.space.location_set.get(purpose="TS")

        # Get all datasets in a location
        resp = dataverse.browse(location.relative_path)
        assert len(resp["directories"]) == 59
        assert len(resp["entries"]) == 59
        assert resp["entries"] == resp["directories"]
        assert len(resp["properties"]) == 59
        assert resp["properties"]["1016"]["verbose name"] == (
            "3D Laser Images of a road cut at Ivy Lea, Ontario (2007),"
            " underground in Sudbury, Ontario (2007), underground in Thompson,"
            " Manitoba (2009) [test]"
        )
        assert resp["properties"]["574"]["verbose name"] == (
            "A study of my afternoon drinks "
        )
        assert resp["properties"]["577"]["verbose name"] == (
            "A study with restricted data"
        )
        assert resp["properties"]["581"]["verbose name"] == ("A sub-dataverse dataset")

        # Get all objects in dataset 1016
        resp = dataverse.browse(f"{location.relative_path}/1016")
        assert resp["directories"] == []
        assert len(resp["entries"]) == 4
        ivy_lea_sample = [
            "IvyLea_003.txt",
            "IvyLea_004.txt",
            "IvyLea_005.txt",
            "IvyLea_006.txt",
        ]
        ivy_lea_sizes = [47448936, 46736074, 47463997, 47723143]
        for idx, obj in enumerate(ivy_lea_sample):
            assert resp["properties"][obj]["size"] == ivy_lea_sizes[idx]

    @mock.patch(
        "requests.get",
        side_effect=[
            mock.Mock(
                **{
                    "status_code": 200,
                    "json.return_value": {
                        "data": {
                            "latestVersion": {
                                "files": [
                                    {
                                        "label": "chelan 052.jpg",
                                        "dataFile": {
                                            "id": 92,
                                            "filename": "chelan 052.jpg",
                                        },
                                    },
                                    {
                                        "label": "Weather_data.tab",
                                        "dataFile": {
                                            "id": 91,
                                            "filename": "Weather_data.tab",
                                        },
                                    },
                                ],
                            },
                        },
                    },
                }
            ),
            mock.Mock(**{"status_code": 200, "iter_content.return_value": []}),
            mock.Mock(**{"status_code": 200, "iter_content.return_value": []}),
        ],
    )
    def test_move_to(self, _requests_get):
        """
        It should fetch the files listed in the dataset.
        It should fetch the bundle for tha dataset.
        """
        assert os.path.exists(self.dest_path) is False
        self.dataverse.space.move_to_storage_service("90", "dataverse/", self.space)
        assert "chelan 052.jpg" in os.listdir(self.dest_path)
        assert "Weather_data.zip" in os.listdir(self.dest_path)
        assert "metadata" in os.listdir(self.dest_path)
        assert "agents.json" in os.listdir(os.path.join(self.dest_path, "metadata"))
        assert "dataset.json" in os.listdir(os.path.join(self.dest_path, "metadata"))

    def test_get_query_and_subtree(self):
        """Test the function that we're using to construct parts of the
        Dataverse query from the relative_path string stored in the Storage
        Service.
        """
        query_tests = [
            {
                "query": "query: drinks_1 subtree: archivematica_1/111",
                "result": ("111", "archivematica_1", "drinks_1"),
            },
            {
                "query": "Query: Drinks_2 Subtree: Archivematica_2/222",
                "result": ("222", "archivematica_2", "drinks_2"),
            },
            {
                "query": "query: drinks_3 subtree: archivematica_3",
                "result": (None, "archivematica_3", "drinks_3"),
            },
            {"query": "query: drinks_4", "result": (None, None, "drinks_4")},
            {"query": "query: drinks_5/555", "result": ("555", None, "drinks_5")},
            {"query": "", "result": (None, None, "*")},
            {
                "query": "Subtree: Archivematica_7",
                "result": (None, "archivematica_7", "*"),
            },
            {
                "query": "query: drinks_8 subtree: archivematica_8/8",
                "result": ("8", "archivematica_8", "drinks_8"),
            },
        ]

        for test in query_tests:
            assert test["result"] == self.dataverse.get_query_and_subtree(test["query"])
