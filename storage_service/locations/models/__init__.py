# flake8: noqa
# Required by other files
class StorageException(Exception):
    """Exceptions specific to the service."""

    pass


# Common
# May have multiple models, so import * and use __all__ in file.
from .asynchronous import *
from .event import *
from .location import *
from .package import *
from .pipeline import *
from .space import *
from .fixity_log import *

# not importing managers as that is internal

# Protocol Spaces
# Will only have one model, so import that directly
from .archipelago import Archipelago
from .arkivum import Arkivum
from .dataverse import Dataverse
from .duracloud import Duracloud
from .dspace import DSpace
from .dspace_rest import DSpaceREST
from .fedora import Fedora, PackageDownloadTask, PackageDownloadTaskFile
from .gpg import GPG
from .local_filesystem import LocalFilesystem
from .lockssomatic import Lockssomatic
from .nfs import NFS
from .pipeline_local import PipelineLocalFS
from .replica_staging import OfflineReplicaStaging
from .rclone import RClone
from .swift import Swift
from .s3 import S3
