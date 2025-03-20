# flake8: noqa
# Required by other files
class StorageException(Exception):
    """Exceptions specific to the service."""

    pass


# Common
# May have multiple models, so import * and use __all__ in file.
from archivematica.storage_service.locations.models.asynchronous import *
from archivematica.storage_service.locations.models.event import *
from archivematica.storage_service.locations.models.location import *
from archivematica.storage_service.locations.models.package import *
from archivematica.storage_service.locations.models.pipeline import *
from archivematica.storage_service.locations.models.space import *
from archivematica.storage_service.locations.models.fixity_log import *

# not importing managers as that is internal

# Protocol Spaces
# Will only have one model, so import that directly
from archivematica.storage_service.locations.models.archipelago import Archipelago
from archivematica.storage_service.locations.models.arkivum import Arkivum
from archivematica.storage_service.locations.models.dataverse import Dataverse
from archivematica.storage_service.locations.models.duracloud import Duracloud
from archivematica.storage_service.locations.models.dspace import DSpace
from archivematica.storage_service.locations.models.dspace_rest import DSpaceREST
from archivematica.storage_service.locations.models.fedora import (
    Fedora,
    PackageDownloadTask,
    PackageDownloadTaskFile,
)
from archivematica.storage_service.locations.models.gpg import GPG
from archivematica.storage_service.locations.models.local_filesystem import (
    LocalFilesystem,
)
from archivematica.storage_service.locations.models.lockssomatic import Lockssomatic
from archivematica.storage_service.locations.models.nfs import NFS
from archivematica.storage_service.locations.models.pipeline_local import (
    PipelineLocalFS,
)
from archivematica.storage_service.locations.models.replica_staging import (
    OfflineReplicaStaging,
)
from archivematica.storage_service.locations.models.rclone import RClone
from archivematica.storage_service.locations.models.swift import Swift
from archivematica.storage_service.locations.models.s3 import S3
