"""Resources for Version 3 of the Storage Service API.

Defines the following sub-classes of ``remple.Resources``:

- ``Packages``
- ``Locations``
- ``Pipelines``
- ``Spaces``
"""

import logging

from formencode.validators import UnicodeString

from locations.api.v3.remple import utils, Resources, ReadonlyResources
from locations.api.v3.schemata import (
    LocationSchema,
    PackageSchema,
    SpaceCreateSchema,
    SpaceUpdateSchema,
    PipelineSchema,
)
from locations.models import (
    Location,
    Package,
    Space,
    Pipeline,
)

logger = logging.getLogger(__name__)


class Packages(ReadonlyResources):
    """TODO: Packages should not be creatable or editable via the REST API.
    However, the user should be able to delete them via the API or at least
    request their deletion.
    """
    model_cls = Package
    # schema_cls = PackageSchema


class Locations(Resources):
    model_cls = Location
    schema_cls = LocationSchema


class Pipelines(Resources):
    model_cls = Pipeline
    schema_cls = PipelineSchema


class Spaces(Resources):
    model_cls = Space
    schema_create_cls = SpaceCreateSchema
    schema_update_cls = SpaceUpdateSchema
