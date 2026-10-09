"""Test startup code that creates default Space & Locations."""

import pytest

from archivematica.storage_service.common.startup import startup
from archivematica.storage_service.locations import models


@pytest.mark.django_db
def test_create_default_locations() -> None:
    # Assert no Space or Location exists
    assert not models.Space.objects.all().exists()
    assert not models.Location.objects.all().exists()
    # Run test
    startup(start_async=False)
    # Assert Space & Locations created
    assert models.Space.objects.get(access_protocol="FS")
    assert models.Location.objects.get(purpose="TS")
    assert models.Location.objects.get(purpose="AS")
    assert models.Location.objects.get(purpose="DS")
    assert models.Location.objects.get(purpose="BL")
    assert models.Location.objects.get(purpose="SS")
    assert models.Location.objects.get(purpose="AR")
    # Assert no other Spaces or Locations were created
    assert len(models.Space.objects.all()) == 1
    assert len(models.Location.objects.all()) == 6


@pytest.mark.django_db
def test_handle_multiple_identical_spaces() -> None:
    # Create Spaces with the same path
    models.Space.objects.create(path="/", access_protocol="FS")
    models.Space.objects.create(path="/", access_protocol="FS")
    assert len(models.Space.objects.filter(access_protocol="FS")) == 2
    # Run test
    startup(start_async=False)
    # Verify no locations exist - space errored gracefully
    assert len(models.Space.objects.filter(access_protocol="FS")) == 2
    assert not models.Location.objects.all().exists()


@pytest.mark.django_db
def test_handle_multiple_identical_locations() -> None:
    # Create existing Location
    s = models.Space.objects.create(path="/", access_protocol="FS")
    models.Location.objects.create(
        space=s,
        purpose="SS",
        relative_path="var/archivematica/storage_service",
        description="For storage service internal usage.",
    )
    models.Location.objects.create(
        space=s,
        purpose="SS",
        relative_path="var/archivematica/storage_service",
        description="For storage service internal usage.",
    )
    assert len(models.Space.objects.filter(access_protocol="FS")) == 1
    assert len(models.Location.objects.filter(purpose="SS")) == 2
    # Run test
    startup(start_async=False)
    # Verify no new Location was created
    assert len(models.Space.objects.filter(access_protocol="FS")) == 1
    assert len(models.Location.objects.filter(purpose="SS")) == 2


@pytest.mark.django_db
def test_dont_create_if_same_purpose_already_exist() -> None:
    # Create existing Locations
    s = models.Space.objects.create(path="/", access_protocol="FS")
    models.Location.objects.create(space=s, purpose="TS", relative_path="mnt/transfers")
    models.Location.objects.create(space=s, purpose="AS", relative_path="mnt/aips")
    models.Location.objects.create(space=s, purpose="DS", relative_path="mnt/dips")
    models.Location.objects.create(space=s, purpose="BL", relative_path="mnt/backlog")
    models.Location.objects.create(
        space=s, purpose="SS", relative_path="mnt/storage_service"
    )
    models.Location.objects.create(
        space=s, purpose="AR", relative_path="mnt/aips/recovery"
    )
    assert len(models.Location.objects.all()) == 6
    # Run test
    startup(start_async=False)
    # Verify no new Locations created
    assert len(models.Location.objects.all()) == 6
