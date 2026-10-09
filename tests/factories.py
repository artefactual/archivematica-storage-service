"""Factories of the database rows that the tests create with their own data.

The defaults of each factory describe the plainest object of its model, and the
keyword arguments override any field, including the ones the factory derives.
Fixtures such as ``space`` and ``package`` build on the factories and add what
a complete object needs, for example the directory of a space on disk.
"""

from archivematica.storage_service.locations import models
from archivematica.storage_service.locations.models.local_filesystem import (
    LocalFilesystem,
)


class SpaceFactory:
    """Creates spaces, in the local filesystem unless told otherwise, with the
    row of that protocol because it needs no configuration.
    """

    def __call__(self, **fields: object) -> models.Space:
        defaults: dict[str, object] = {"access_protocol": models.Space.LOCAL_FILESYSTEM}
        result = models.Space.objects.create(**{**defaults, **fields})
        if result.access_protocol == models.Space.LOCAL_FILESYSTEM:
            LocalFilesystem.objects.create(space=result)

        return result


class LocationFactory:
    """Creates the locations of a space for a purpose, at its root unless
    given a relative path.
    """

    def __call__(
        self, space: models.Space, purpose: str, /, **fields: object
    ) -> models.Location:
        defaults: dict[str, object] = {"relative_path": ""}

        return models.Location.objects.create(
            space=space, purpose=purpose, **{**defaults, **fields}
        )


class PipelineFactory:
    """Creates pipelines."""

    def __call__(self, **fields: object) -> models.Pipeline:
        return models.Pipeline.objects.create(**fields)


class PackageFactory:
    """Creates the packages of a location from their paths relative to it,
    uploaded AIPs unless told otherwise.
    """

    def __call__(
        self, location: models.Location, current_path: str, /, **fields: object
    ) -> models.Package:
        defaults: dict[str, object] = {
            "package_type": models.Package.AIP,
            "status": models.Package.UPLOADED,
        }

        return models.Package.objects.create(
            current_location=location,
            current_path=current_path,
            **{**defaults, **fields},
        )


class EventFactory:
    """Creates the requests of a package, submitted through a pipeline by the
    first user: deletion requests unless told otherwise.
    """

    def __call__(
        self, package: models.Package, pipeline: models.Pipeline, /, **fields: object
    ) -> models.Event:
        defaults: dict[str, object] = {
            "event_type": models.Event.DELETE,
            "event_reason": "Deletion requested",
            "user_id": 1,
            "user_email": "requester@example.com",
            "status": models.Event.SUBMITTED,
            "store_data": package.status,
        }

        return models.Event.objects.create(
            package=package, pipeline=pipeline, **{**defaults, **fields}
        )
