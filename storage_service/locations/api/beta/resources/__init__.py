"""Resources for Version Beta of the Storage Service API.

Defines sub-classes of ``remple.Resources`` and ``remple.ReadonlyResources`` in
order to define CRUD class methods for resources including:

- ``Packages``
- ``Locations``
- ``Pipelines``
- ``Spaces`` (and space sub-types)
- ``Files``

.. note:: The simple (model-based) resources are defined here. More complex
          resources are defined in their own modules, e.g.,
          resources/locations.py.

TODO:

- package custom endpoints (cf.
  https://wiki.archivematica.org/Storage_Service_API#Package)
"""

from __future__ import absolute_import
import logging

from django.contrib.auth.models import User, Group, Permission
from django.contrib.contenttypes.models import ContentType

from locations.api.beta.remple import (
    Resources,
    ReadonlyResources,
)
from locations.api.beta.schemata import (
    ArkivumSpaceSchema,
    DataverseSpaceSchema,
    DSpaceSpaceSchema,
    DuracloudSpaceSchema,
    FedoraSpaceSchema,
    LockssomaticSpaceSchema,
    NFSSpaceSchema,
    S3SpaceSchema,
    SwiftSpaceSchema,
    GPGSpaceSchema,
    LocalFilesystemSpaceSchema,
    PipelineSchema,
    PipelineLocalSpaceSchema,
    SpaceCreateSchema,
    SpaceUpdateSchema,
    UserSchema,
)
from locations.models import (
    Arkivum,
    Async,
    Callback,
    Dataverse,
    DSpace,
    Duracloud,
    Event,
    Fedora,
    FixityLog,
    Lockssomatic,
    NFS,
    S3,
    Swift,
    File,
    GPG,
    LocalFilesystem,
    Package,
    Space,
    Pipeline,
    PipelineLocalFS,
)
from .locations import Locations


logger = logging.getLogger(__name__)


class Files(ReadonlyResources):
    model_cls = File


class Packages(ReadonlyResources):
    """TODO: Packages have a lot of special behaviour that should be exposed
    via the beta API, but this is being left for later work.
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


class ArkivumSpaces(Resources):
    primary_key = 'id'
    model_cls = Arkivum
    schema_cls = ArkivumSpaceSchema


class DataverseSpaces(Resources):
    primary_key = 'id'
    model_cls = Dataverse
    schema_cls = DataverseSpaceSchema


class DSpaceSpaces(Resources):
    primary_key = 'id'
    model_cls = DSpace
    schema_cls = DSpaceSpaceSchema


class DuracloudSpaces(Resources):
    primary_key = 'id'
    model_cls = Duracloud
    schema_cls = DuracloudSpaceSchema


class FedoraSpaces(Resources):
    primary_key = 'id'
    model_cls = Fedora
    schema_cls = FedoraSpaceSchema


class LockssomaticSpaces(Resources):
    primary_key = 'id'
    model_cls = Lockssomatic
    schema_cls = LockssomaticSpaceSchema


class NFSSpaces(Resources):
    primary_key = 'id'
    model_cls = NFS
    schema_cls = NFSSpaceSchema


class S3Spaces(Resources):
    primary_key = 'id'
    model_cls = S3
    schema_cls = S3SpaceSchema


class SwiftSpaces(Resources):
    primary_key = 'id'
    model_cls = Swift
    schema_cls = SwiftSpaceSchema


class PipelineLocalSpaces(Resources):
    primary_key = 'id'
    model_cls = PipelineLocalFS
    schema_cls = PipelineLocalSpaceSchema


class Asyncs(ReadonlyResources):
    primary_key = 'id'
    model_cls = Async


class Events(ReadonlyResources):
    primary_key = 'id'
    model_cls = Event


class Callbacks(ReadonlyResources):
    primary_key = 'id'
    model_cls = Callback


class FixityLogs(ReadonlyResources):
    primary_key = 'id'
    model_cls = FixityLog


class Users(Resources):
    primary_key = 'id'
    model_cls = User
    schema_cls = UserSchema

    def _get_show_dict(self, resource_model):
        ret = super(Users, self)._get_show_dict(resource_model)
        del ret['password']
        return ret


class Groups(ReadonlyResources):
    primary_key = 'id'
    model_cls = Group


class Permissions(ReadonlyResources):
    primary_key = 'id'
    model_cls = Permission


class ContentTypes(ReadonlyResources):
    primary_key = 'id'
    model_cls = ContentType


__all__ = (
    'Locations',
    'Files',
    'Packages',
    'Pipelines',
    'Spaces',
    'LocalFilesystemSpaces',
    'GPGSpaces',
    'ArkivumSpaces',
    'DataverseSpaces',
    'DSpaceSpaces',
    'DuracloudSpaces',
    'FedoraSpaces',
    'LockssomaticSpaces',
    'NFSSpaces',
    'S3Spaces',
    'SwiftSpaces',
    'PipelineLocalSpaces',
    'Asyncs',
    'Events',
    'Callbacks',
    'FixityLogs',
    'Users',
    'Groups',
    'Permissions',
    'ContentTypes',
)
