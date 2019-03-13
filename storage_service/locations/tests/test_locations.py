from django.test import TestCase

from locations import forms, models


class TestLocations(TestCase):

    fixtures = ["base.json", "pipelines.json"]

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
