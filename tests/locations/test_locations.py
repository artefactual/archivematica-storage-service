import pathlib

from django.test import TestCase

from archivematica.storage_service.administration.models import Settings
from archivematica.storage_service.locations import forms
from archivematica.storage_service.locations import models

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"


class TestLocations(TestCase):
    fixture_files = ["base.json", "pipelines.json"]
    fixtures = [FIXTURES_DIR / f for f in fixture_files]

    def test_clean_works(self):
        pipelines = models.Pipeline.objects.all()
        form_data = {
            "purpose": "TS",
            "pipeline": [p.id for p in pipelines],
            "relative_path": "transfer_source",
            "description": None,
            "quota": None,
            "enabled": True,
        }
        form = forms.LocationForm(data=form_data, space_protocol="FS")
        assert form.is_valid()

    def test_clean_aip_recovery_fine(self):
        pipeline_without_ar = models.Pipeline.objects.filter(
            uuid="d2df89dc-9443-48dd-8983-55e9d1f92bcb"
        )
        form_data = {
            "purpose": "AR",
            "pipeline": [p.id for p in pipeline_without_ar],
            "relative_path": "var/archivematica/storage_service/recover2",
            "description": None,
            "quota": None,
            "enabled": True,
        }
        form = forms.LocationForm(data=form_data, space_protocol="FS")
        assert form.is_valid()

    def test_clean_aip_recovery_error(self):
        pipeline_with_ar = models.Pipeline.objects.filter(
            uuid="b25f6b71-3ebf-4fcc-823c-1feb0a2553dd"
        )
        form_data = {
            "purpose": "AR",
            "pipeline": [p.id for p in pipeline_with_ar],
            "relative_path": "var/archivematica/storage_service/recover",
            "description": None,
            "quota": None,
            "enabled": True,
        }
        form = forms.LocationForm(data=form_data, space_protocol="FS")
        assert form.is_valid() is False
        assert "already have an AIP recovery location" in form.errors["__all__"][0]

    def test_clean_fail_replication_requires_replicator_location(self):
        pipelines = models.Pipeline.objects.all()
        form_data = {
            "purpose": "TS",
            "pipeline": [p.id for p in pipelines],
            "relative_path": "transfer_source",
            "description": None,
            "quota": None,
            "enabled": True,
            "fail_replication": True,
        }
        form = forms.LocationForm(data=form_data, space_protocol="FS")
        assert form.is_valid() is False
        assert "Only replicator locations can be configured to fail replication" in (
            form.errors["__all__"][0]
        )

    def test_location_fail_replication_setting_round_trip(self):
        location = models.Location.objects.create(
            space=models.Space.objects.create(
                access_protocol=models.Space.LOCAL_FILESYSTEM, path="/tmp"
            ),
            purpose=models.Location.REPLICATOR,
            relative_path="replicator",
        )

        assert location.fail_replication is False

        location.fail_replication = True
        assert location.fail_replication is True
        assert Settings.objects.filter(
            name=location.replication_failure_setting_name, value="True"
        ).exists()

        location.fail_replication = False
        assert location.fail_replication is False
        assert not Settings.objects.filter(
            name=location.replication_failure_setting_name
        ).exists()
