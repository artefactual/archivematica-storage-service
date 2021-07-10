from django.test import TestCase
import os
import vcr

from locations import models
from . import TempDirMixin

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
FIXTURES_DIR = os.path.abspath(os.path.join(THIS_DIR, "..", "fixtures"))


class TestDataverse(TempDirMixin, TestCase):

    fixtures = ["base.json", "dataverse.json", "dataverse2.json"]

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

    @vcr.use_cassette(
        os.path.join(FIXTURES_DIR, "vcr_cassettes", "dataverse_browse_all.yaml")
    )
    def test_browse_all(self):
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

    @vcr.use_cassette(
        os.path.join(FIXTURES_DIR, "vcr_cassettes", "dataverse_browse_filter.yaml")
    )
    def test_browse_datasets(self):
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
        assert len(resp["entries"]) == 55
        ivy_lea_sample = [
            "IvyLea_003.txt",
            "IvyLea_004.txt",
            "IvyLea_005.txt",
            "IvyLea_006.txt",
        ]
        ivy_lea_sizes = [47448936, 46736074, 47463997, 47723143]
        for idx, obj in enumerate(ivy_lea_sample):
            assert resp["properties"][obj]["size"] == ivy_lea_sizes[idx]

    @vcr.use_cassette(
        os.path.join(FIXTURES_DIR, "vcr_cassettes", "dataverse_move_to.yaml")
    )
    def test_move_to(self):
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
