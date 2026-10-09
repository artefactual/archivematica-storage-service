from archivematica.storage_service.locations import forms
from archivematica.storage_service.locations import models


def test_clean_works(pipeline_rows: list[models.Pipeline]) -> None:
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


def test_clean_aip_recovery_fine(pipeline_rows: list[models.Pipeline]) -> None:
    _, pipeline_without_ar, _ = pipeline_rows
    form_data = {
        "purpose": "AR",
        "pipeline": [pipeline_without_ar.id],
        "relative_path": "var/archivematica/storage_service/recover2",
        "description": None,
        "quota": None,
        "enabled": True,
    }
    form = forms.LocationForm(data=form_data, space_protocol="FS")
    assert form.is_valid()


def test_clean_aip_recovery_error(pipeline_rows: list[models.Pipeline]) -> None:
    pipeline_with_ar, _, _ = pipeline_rows
    form_data = {
        "purpose": "AR",
        "pipeline": [pipeline_with_ar.id],
        "relative_path": "var/archivematica/storage_service/recover",
        "description": None,
        "quota": None,
        "enabled": True,
    }
    form = forms.LocationForm(data=form_data, space_protocol="FS")
    assert form.is_valid() is False
    assert "already have an AIP recovery location" in form.errors["__all__"][0]
