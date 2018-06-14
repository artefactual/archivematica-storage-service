"""Resources for Version 3 of the Storage Service API.

Defines the following sub-classes of ``remple.Resources``:

- ``Packages``
- ``Locations``
- ``Pipelines``
- ``Spaces``
"""

import logging

from locations.api.beta.remple import Resources, ReadonlyResources
from locations.api.beta.schemata import (
    GPGSpaceSchema,
    LocalFilesystemSpaceSchema,
    LocationSchema,
    PipelineSchema,
    SpaceCreateSchema,
    SpaceUpdateSchema,
)
from locations.models import (
    File,
    GPG,
    LocalFilesystem,
    Location,
    Package,
    Space,
    Pipeline,
)

logger = logging.getLogger(__name__)


class Files(ReadonlyResources):
    model_cls = File


class Locations(Resources):
    model_cls = Location
    schema_cls = LocationSchema


class Packages(ReadonlyResources):
    """TODO: Packages should not be creatable or editable via the REST API.
    However, the user should be able to delete them via the API or at least
    request their deletion.
    """
    model_cls = Package


class Pipelines(Resources):
    model_cls = Pipeline
    schema_cls = PipelineSchema


class Spaces(Resources):
    model_cls = Space
    schema_create_cls = SpaceCreateSchema
    schema_update_cls = SpaceUpdateSchema


class LocalFilesystemSpaces(Resources):
    primary_key = 'id'
    model_cls = LocalFilesystem
    schema_cls = LocalFilesystemSpaceSchema


class GPGSpaces(Resources):
    primary_key = 'id'
    model_cls = GPG
    schema_cls = GPGSpaceSchema
